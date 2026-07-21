# CP-SAT Matching Solution Specification

## Aqua Essence Swimmer-Instructor Matching System

> **Specification note:** This document preserves detailed algorithm rationale
> and illustrative pseudocode accumulated during development. Paths and small
> code fragments in older examples are not an implementation map. Use
> [architecture.md](architecture.md) and the current
> `solvers/python_cpsat/engine/` source for active component boundaries.

**Document Version**: 2.0
**Date**: February 2026  
**Purpose**: Complete technical specification for implementing the CP-SAT-based matching algorithm with explainability layer

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Overview](#problem-overview)
3. [Solution Architecture](#solution-architecture)
4. [Compatibility Scoring System](#compatibility-scoring-system)
5. [CP-SAT Model Specification](#cp-sat-model-specification)
6. [Explainability Layer](#explainability-layer)
7. [Implementation Guide](#implementation-guide)
8. [Testing Strategy](#testing-strategy)
9. [Tuning and Iteration](#tuning-and-iteration)

---

## Executive Summary

This document specifies a **three-phase CP-SAT solution** for matching swimmers to instructors at Aqua Essence swim center. The solution provides:

- ✅ **Provably optimal** compatibility-based assignments after continuity matching
- ✅ **Human-readable explanations** for every assignment decision
- ✅ **Confidence scores** (0-100%) to guide staff review
- ✅ **Scalability** from 8 instructors to 1800 swimmers without algorithmic changes

**Core Innovation**: CP-SAT finds the globally optimal solution, while an explainability layer translates that solution into language stakeholders can understand and verify.

---

## Problem Overview

### Input Files (per time slot)

| File                              | Contents                                            | Purpose                                   |
| --------------------------------- | --------------------------------------------------- | ----------------------------------------- |
| `instructors.csv`                 | 7-9 instructors available in this time slot         | Defines who can teach                     |
| `swimmers.csv`                    | 7-18 swimmers (individuals + pre-paired groups)     | Defines who needs to be taught            |
| `classes.csv`                     | One class per instructor (instructors pre-assigned) | Template to fill with swimmer assignments |
| `historical_pairings.csv`         | Previous instructor for each swimmer                | Enables continuity matching               |
| `personality_colors.csv`          | 4 personality colors (Blue, Orange, Green, Gold)    | Reference data for compatibility          |
| `instructor_styles.csv`           | 6 teaching styles (NR, HE, TD, A, SS, DIA)          | Reference data for compatibility          |
| `swimmer_types.csv`               | 7 swimmer personality types                         | Reference data for compatibility          |
| `swimmer_type_color_rankings.csv` | Preference ranking of colors per swimmer type (1-4) | Ranking data for compatibility scoring    |
| `swimmer_type_style_rankings.csv` | Preference ranking of styles per swimmer type (1-6) | Ranking data for compatibility scoring    |

### Problem Statement

**Given**:

- N instructors (7-9) available in a 30-minute time slot
- M swimmers/pairs (7-18 total swimmers) enrolled in that slot
- Historical pairing data
- Personality compatibility rules

**Find**:

- An assignment of swimmers to instructors that:
  1. Satisfies all hard constraints (HC-1 to HC-4)
  2. Maximizes continuity (Priority 1)
  3. Maximizes personality compatibility (Priority 2)
  4. Respects parent preferences in notes (Priority 3)

**Output**:

- Completed `classes.csv` with `swimmer_1_id` and `swimmer_2_id` filled
- Match confidence score (0-100%) for each assignment
- Human-readable explanation for each assignment

### Key Domain Rules

**Hard Constraints (Non-negotiable)**:

- **HC-1**: Each instructor teaches max 1 class (1-2 swimmers) per slot
- **HC-2**: Swimmers with special needs → adapted-capable instructors only
- **HC-3**: Babies → baby-capable instructors; Adults → adult-capable instructors
- **HC-4**: Two swimmers in same class must be ≤1 RSS level apart and ≤2 years age apart
  - **Note**: Pre-paired swimmers (same `pair_id`) already satisfy this

**Soft Priorities (In order)**:

1. **Continuity**: Assign swimmer to previous instructor if available
2. **Compatibility**: Assign to instructor with highest personality fit
3. **Notes**: Honor parent requests/exclusions

**Notes Parsing**:

Swimmer notes are parsed using a standardized keyword list. Only notes that match these patterns affect the algorithm — freeform notes are surfaced in output for human review but have no algorithmic effect.

| Pattern | Example | Effect |
|---|---|---|
| `prefer [name]` | `prefer Smith` | Moderately boost that instructor's compatibility score |
| `avoid [name]` | `avoid Smith` | Completely exclude that instructor from consideration |
| `no [name]` | `no Smith` | Equivalent to `avoid` |
| `always [name]` | `always Smith` | Strong boost — treat similarly to a continuity match |
| `never [name]` | `never Smith` | Equivalent to `avoid` |

Name matching is case-insensitive and matches on last name. If a note exclusion keyword targets the swimmer's previous instructor, continuity matching for that instructor is suppressed and the algorithm falls back to compatibility scoring as though no continuity history existed.

**Special Rules**:

- **DIA (Do-It-Alls) instructors**: Can teach any swimmer type effectively. Use secondary style to differentiate best matches.
- **Pre-paired swimmers**: Already validated for HC-4 compatibility. Must be assigned together as a unit.

---

## Solution Architecture

### Three-Phase Design

```
┌──────────────────────────────────────────────────────────────┐
│                    PHASE 1: CONTINUITY                       │
│                     (Greedy, Deterministic)                  │
│                                                              │
│  • Process swimmers with historical pairings                 │
│  • Sort by num_sessions (descending) for tiebreaking         │
│  • Assign to previous instructor if available & has capacity │
│                                                              │
│  Output: ~60% of swimmers matched via continuity             │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                 PHASE 2: CP-SAT OPTIMIZATION                 │
│                   (Globally Optimal)                         │
│                                                              │
│  • Model remaining swimmers & available instructor slots     │
│  • Apply hard constraints (HC-2, HC-3)                       │
│  • Maximize compatibility scores                             │
│  • Solve using Google OR-Tools CP-SAT                        │
│                                                              │
│  Output: Optimal assignment for remaining ~40% of swimmers   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│               PHASE 3: EXPLAINABILITY LAYER                  │
│                  (Human Translation)                         │
│                                                              │
│  • Generate reason for each assignment                       │
│  • Calculate confidence scores (0-100%)                      │
│  • Show alternatives considered                              │
│  • Flag low-confidence matches for review                    │
│                                                              │
│  Output: Annotated classes.csv + summary report              │
└──────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

1. **Phase 1 (Continuity) must be greedy**:
   - Continuity is binary (yes/no), not a spectrum
   - No benefit to "optimizing" across continuity claims
   - Tiebreaking by `num_sessions` is deterministic and fair

2. **Phase 2 (Compatibility) benefits from CP-SAT**:
   - This is where tradeoffs exist ("Swimmer A fits Instructor 1 at 87%, but Swimmer B fits at 90%")
   - Global optimization prevents greedy mistakes
   - Handles competing constraints elegantly

3. **Phase 3 (Explainability) is post-processing**:
   - CP-SAT produces optimal solution
   - Explainability layer makes it human-readable
   - Separate concerns: optimization vs communication

---

## Compatibility Scoring System

### 4.1 Overview

The compatibility score represents **how well an instructor matches a swimmer's personality and learning needs**. Scores range from **0 to 100**, where higher is better.

Each swimmer has a **swimmer type** (1 of 7).
Each instructor has:

- **Primary & secondary personality colors** (1 of 4 each, must differ)
- **Primary & secondary teaching styles** (1 of 6 each, must differ)

For each swimmer type, Aqua Essence provides **rankings** of colors and styles from most to least preferred.

### 4.2 Ranking System

Instead of binary compatibility (+1/-1), the system uses **preference rankings**.

**Example Rankings for "The Nervous/New" Swimmer Type**:

**Color Preference** (most to least preferred):

1. Blue (empathetic, caring)
2. Orange (flexible, fun)
3. Green (calm, analytical)
4. Gold (organized, structured)

**Style Preference** (most to least preferred):

1. New RSS/Babies (bubbly, fun)
2. High Energy (outgoing, loud)
3. Soft-Spoken (calm, trust-building)
4. Adapted (comfortable, authentic)
5. Technique Driven (serious, direct)
6. Do-It-Alls (knowledgeable, experienced)

### 4.3 Converting Rankings to Points

**For Colors** (4 options):

1st choice = 4 points
2nd choice = 3 points
3rd choice = 2 points
4th choice = 1 point

**For Styles** (6 options):

1st choice = 6 points
2nd choice = 5 points
3rd choice = 4 points
4th choice = 3 points
5th choice = 2 points
6th choice = 1 point

**General Formula**: `points = total_options - (rank - 1)`

**Why linear?** Simple, intuitive, and automatically scales if colors or styles are added/removed in the future.

### 4.4 Primary vs Secondary Trait Weighting

Instructors have both primary and secondary colors/styles. The primary trait is more defining.

**Weights**:

- **Primary trait**: 2.0x multiplier
- **Secondary trait**: 1.0x multiplier

**Rationale**: Primary is the instructor's dominant characteristic, but secondary adds important nuance.

### 4.5 Standard Compatibility Formula

```python
def calculate_compatibility(swimmer, instructor, rankings):
    """
    Calculate compatibility score (0-100) for a swimmer-instructor pair.

    Args:
        swimmer: Swimmer object with swimmer_type_id
        instructor: Instructor object with color/style IDs
        rankings: Dict with 'color' and 'style' ranking tables

    Returns:
        float: Compatibility score 0-100
    """

    # === STEP 1: GET SWIMMER'S RANKINGS ===
    color_ranking = get_color_ranking(swimmer.swimmer_type_id, rankings)
    style_ranking = get_style_ranking(swimmer.swimmer_type_id, rankings)

    # === STEP 2: FIND INSTRUCTOR'S TRAITS IN RANKINGS ===
    primary_color_rank = find_rank(instructor.primary_color_id, color_ranking)
    secondary_color_rank = find_rank(instructor.secondary_color_id, color_ranking)

    primary_style_rank = find_rank(instructor.primary_style_id, style_ranking)
    secondary_style_rank = find_rank(instructor.secondary_style_id, style_ranking)

    # === STEP 3: CONVERT RANKS TO POINTS ===
    num_colors = 4
    num_styles = 6

    primary_color_points = num_colors - (primary_color_rank - 1)
    secondary_color_points = num_colors - (secondary_color_rank - 1)

    primary_style_points = num_styles - (primary_style_rank - 1)
    secondary_style_points = num_styles - (secondary_style_rank - 1)

    # === STEP 4: APPLY PRIMARY/SECONDARY WEIGHTING ===
    # Standard weighting (modified for DIA below)
    primary_color_weighted = primary_color_points * 2.0
    secondary_color_weighted = secondary_color_points * 1.0

    primary_style_weighted = primary_style_points * 2.0
    secondary_style_weighted = secondary_style_points * 1.0

    # === STEP 5: HANDLE DIA SPECIAL CASE ===
    if instructor.primary_style_code == 'DIA':
        # DIA instructors: secondary style becomes primary differentiator
        # Give universal bonus + secondary style at enhanced weight
        universal_bonus = 3.0  # Base compatibility with all swimmers
        primary_style_weighted = universal_bonus
        secondary_style_weighted = secondary_style_points * 2.0  # Enhanced!

    # === STEP 6: CALCULATE RAW SCORES ===
    color_total = primary_color_weighted + secondary_color_weighted
    style_total = primary_style_weighted + secondary_style_weighted

    # === STEP 7: NORMALIZE TO 0-100 SCALE ===
    # Primary and secondary traits must differ, so best/worst cases reflect this:
    #
    # For colors (4 options, primary ≠ secondary):
    #   Best:  primary=1st (4pts × 2.0) + secondary=2nd (3pts × 1.0) = 11
    #   Worst: primary=4th (1pt × 2.0) + secondary=3rd (2pts × 1.0) = 4
    #
    # For styles (6 options, primary ≠ secondary):
    #   Best:  primary=1st (6pts × 2.0) + secondary=2nd (5pts × 1.0) = 17
    #   Worst: primary=6th (1pt × 2.0) + secondary=5th (2pts × 1.0) = 4
    color_max = (num_colors * 2.0) + ((num_colors - 1) * 1.0)  # = (4*2) + (3*1) = 11
    color_min = (1 * 2.0) + (2 * 1.0)  # = 4 (worst + second-worst)
    color_normalized = ((color_total - color_min) / (color_max - color_min)) * 100

    # Style normalization (standard case; DIA has its own min/max)
    style_max = (num_styles * 2.0) + ((num_styles - 1) * 1.0)  # = (6*2) + (5*1) = 17
    style_min = (1 * 2.0) + (2 * 1.0)  # = 4 (worst + second-worst)

    if instructor.primary_style_code == 'DIA':
        # DIA primary = universal bonus (3.0), secondary at enhanced weight (2.0x)
        # DIA does not have the primary/secondary constraint issue
        style_max = 3.0 + (num_styles * 2.0)  # = 3 + (6*2) = 15
        style_min = 3.0 + (1 * 2.0)  # = 3 + (1*2) = 5

    style_normalized = ((style_total - style_min) / (style_max - style_min)) * 100

    # === STEP 8: COMBINE COLOR AND STYLE (EQUAL WEIGHT) ===
    final_score = (color_normalized + style_normalized) / 2

    return final_score
```

### 4.6 DIA (Do-It-Alls) Instructor Handling

**The Challenge**: DIA instructors work well with all swimmer types. Their primary style provides little differentiation.

**The Solution**: DIA instructors receive:

1. A **universal compatibility bonus** (+3 points) instead of rank-based primary style points
2. Their **secondary style at enhanced weight** (2.0x instead of 1.0x)

**Why This Works**:

- DIA instructors are always competitive (never score terribly with any swimmer)
- Secondary style differentiates them (Soft-Spoken DIA > High-Energy DIA for nervous swimmers)
- They don't always win (a perfectly matched specialist can still score higher)
- Models reality: DIA instructors are versatile generalists

**Example**:

```python
# Instructor: Mike (DIA primary, Soft-Spoken secondary)
# Swimmer: Emma (Nervous/New)
# Emma's style ranking: NR(1st) > HE(2nd) > SS(3rd) > A(4th) > TD(5th) > DIA(6th)

# Standard calculation would give:
# Primary (DIA, rank 6): 6 - (6-1) = 1 point * 2.0 = 2.0
# Secondary (SS, rank 3): 6 - (3-1) = 4 points * 1.0 = 4.0
# Total: 6.0 (weak!)

# DIA special case gives:
# Primary (DIA): universal_bonus = 3.0
# Secondary (SS, rank 3): 4 points * 2.0 = 8.0 (enhanced!)
# Total: 11.0 (strong!)

# Compare to non-DIA specialist:
# Instructor: Sarah (Soft-Spoken primary, Technique Driven secondary)
# Primary (SS, rank 3): 4 points * 2.0 = 8.0
# Secondary (TD, rank 5): 2 points * 1.0 = 2.0
# Total: 10.0

# DIA with good secondary (11.0) slightly beats specialist (10.0)
```

### 4.7 Worked Example (Individual Swimmer)

**Swimmer**: Emma Wilson

- Swimmer Type: The Nervous/New (swimmer_type_id = 1)
- Color ranking: Blue > Orange > Green > Gold
- Style ranking: NR > HE > SS > A > TD > DIA

**Instructor**: Sarah Chen

- Primary color: Blue (color_id = 1)
- Secondary color: Gold (color_id = 4)
- Primary style: Technique Driven (style_id = 3)
- Secondary style: Soft-Spoken (style_id = 5)

**Calculation**:

```
STEP 1: Find ranks
- Primary color (Blue): rank 1 in Emma's ranking
- Secondary color (Gold): rank 4 in Emma's ranking
- Primary style (Technique Driven): rank 5 in Emma's ranking
- Secondary style (Soft-Spoken): rank 3 in Emma's ranking

STEP 2: Convert to points
- Primary color: 4 - (1-1) = 4 points
- Secondary color: 4 - (4-1) = 1 point
- Primary style: 6 - (5-1) = 2 points
- Secondary style: 6 - (3-1) = 4 points

STEP 3: Apply weights (Sarah is NOT DIA, standard weights)
- Primary color: 4 * 2.0 = 8.0
- Secondary color: 1 * 1.0 = 1.0
- Primary style: 2 * 2.0 = 4.0
- Secondary style: 4 * 1.0 = 4.0

STEP 4: Calculate totals
- Color total: 8.0 + 1.0 = 9.0
- Style total: 4.0 + 4.0 = 8.0

STEP 5: Normalize (primary ≠ secondary, so bounds reflect this)
- Color: max=11, min=4 → ((9.0 - 4.0) / (11.0 - 4.0)) * 100 = (5.0/7.0) * 100 = 71.4%
- Style: max=17, min=4 (Sarah is NOT DIA) → ((8.0 - 4.0) / (17.0 - 4.0)) * 100 = (4.0/13.0) * 100 = 30.8%

STEP 6: Combine (equal weight)
- Final score: (71.4 + 30.8) / 2 = 51.1%
```

**Interpretation**: Sarah is a **moderate match** for Emma (51.1%). Her Blue primary personality is excellent for Nervous/New swimmers (+71.4%), but her Technique Driven primary style is one of the least preferred for a nervous swimmer (+30.8%). The Soft-Spoken secondary style helps, but as a secondary trait (1.0x weight) it can't fully compensate for the primary style mismatch.

### 4.8 Pair Compatibility (Harmonic Mean)

For **semi-private classes** (two swimmers assigned to one instructor), we need a combined score.

**Problem**: Two swimmers may have different preferences!

**Example**:

- Swimmer A scores 70% with Instructor Sarah
- Swimmer B scores 90% with Instructor Sarah
- What's the pair score?

**Solution**: Use **Harmonic Mean**

**Formula**:

```python
harmonic_mean = (2 * score1 * score2) / (score1 + score2)
```

**Why Harmonic Mean?**

The harmonic mean emphasizes the **weaker match**, reflecting teaching reality:

- If one swimmer thrives (90%) but the other struggles (70%), the class is limited by the struggling swimmer
- The instructor must split attention, and class quality is pulled down by the weaker match
- Harmonic mean naturally captures this "bottleneck effect"

**Mathematical Property**: Harmonic mean is always ≤ arithmetic mean, and the gap increases with larger differences:

```
Well-matched pair:
- Swimmer A: 85%, Swimmer B: 87%
- Arithmetic mean: 86.0%
- Harmonic mean: 86.0%
- Difference: 0% (negligible penalty for small mismatch)

Moderately mismatched pair:
- Swimmer A: 75%, Swimmer B: 85%
- Arithmetic mean: 80.0%
- Harmonic mean: 79.4%
- Difference: 0.6% (small penalty)

Highly mismatched pair:
- Swimmer A: 60%, Swimmer B: 90%
- Arithmetic mean: 75.0%
- Harmonic mean: 72.0%
- Difference: 3.0% (significant penalty)

Extremely mismatched pair:
- Swimmer A: 40%, Swimmer B: 95%
- Arithmetic mean: 67.5%
- Harmonic mean: 57.5%
- Difference: 10.0% (heavy penalty)
```

**Implementation**:

```python
def calculate_pair_compatibility(swimmer1, swimmer2, instructor, rankings):
    """
    Calculate compatibility for a pre-paired semi-private class.

    Args:
        swimmer1, swimmer2: Pre-paired Swimmer objects (same pair_id)
        instructor: Instructor object
        rankings: Color and style ranking tables

    Returns:
        tuple: (pair_score, score1, score2)
               - pair_score: Harmonic mean (0-100)
               - score1, score2: Individual scores for explainability
    """
    score1 = calculate_compatibility(swimmer1, instructor, rankings)
    score2 = calculate_compatibility(swimmer2, instructor, rankings)

    # Harmonic mean
    pair_score = (2 * score1 * score2) / (score1 + score2)

    return pair_score, score1, score2
```

**Why Not Other Averaging Methods?**

- **Arithmetic mean** (simple average): Too lenient; doesn't capture that weak match limits class quality
- **Minimum**: Too conservative; heavily penalizes any difference, even if one swimmer is very happy
- **Weighted average with penalty**: Requires tuning an arbitrary penalty factor; harmonic mean achieves this naturally

### 4.9 Score Interpretation

| Score Range | Label           | Staff Action                       | CP-SAT Behavior               |
| ----------- | --------------- | ---------------------------------- | ----------------------------- |
| 90-100      | Excellent match | Accept confidently                 | Highly prioritized            |
| 80-89       | Strong match    | Accept with minimal review         | Preferred                     |
| 70-79       | Good match      | Quick review recommended           | Acceptable                    |
| 60-69       | Moderate match  | Detailed review recommended        | Fallback option               |
| 50-59       | Weak match      | Consider alternatives if available | Avoided when possible         |
| 0-49        | Poor match      | Flag for manual override           | Avoided unless no alternative |

**Note**: CP-SAT maximizes the **sum of all compatibility scores**, so it naturally:

- Assigns swimmers to their highest-scoring instructors when possible
- Makes tradeoffs when necessary (e.g., assigns one swimmer to their 2nd choice so another can get their 1st choice)
- Avoids poor matches unless hard constraints force them

---

## CP-SAT Model Specification

### Overview

This section defines the Constraint Programming (CP-SAT) model used in Phase 2 to optimally assign swimmers without continuity history to available instructors.

### Model Components

#### Decision Variables

**For individual swimmers**:

```python
# Binary variable: 1 if swimmer s is assigned to instructor i, 0 otherwise
x[s, i] = model.NewBoolVar(f'assign_swimmer_{s}_to_instructor_{i}')
```

**For pre-paired swimmers**:

```python
# Binary variable: 1 if pair p is assigned to instructor i, 0 otherwise
y[p, i] = model.NewBoolVar(f'assign_pair_{p}_to_instructor_{i}')
```

**Entities**: In the model, an "entity" is either:

- An individual swimmer (needs 1 instructor slot)
- A pre-paired group of 2 swimmers (needs 1 instructor slot with capacity 2)

#### Hard Constraints

##### HC-1: Capacity Constraints

**Each entity assigned to exactly one instructor**:

```python
# For each individual swimmer
for swimmer in individual_swimmers:
    model.Add(
        sum(x[swimmer.id, instr.id] for instr in available_instructors) == 1
    )

# For each pre-paired group
for pair in pre_paired_groups:
    model.Add(
        sum(y[pair.id, instr.id] for instr in available_instructors) == 1
    )
```

**Each instructor gets at most one entity** (either 1 individual OR 1 pair, not both):

```python
for instructor in available_instructors:
    # Sum of individuals assigned to this instructor
    individuals_assigned = sum(
        x[swimmer.id, instructor.id]
        for swimmer in individual_swimmers
    )

    # Sum of pairs assigned to this instructor
    pairs_assigned = sum(
        y[pair.id, instructor.id]
        for pair in pre_paired_groups
    )

    # Total must be at most 1
    model.Add(individuals_assigned + pairs_assigned <= 1)
```

**Note**: This automatically ensures each instructor teaches at most 2 swimmers (since pairs contain exactly 2 swimmers).

##### HC-2: Adapted Routing

**Swimmers with special needs must go to adapted-capable instructors**:

```python
for swimmer in individual_swimmers:
    if swimmer.has_special_needs:
        for instructor in available_instructors:
            if not instructor.can_teach_adapted:
                # Forbid this assignment
                model.Add(x[swimmer.id, instructor.id] == 0)

for pair in pre_paired_groups:
    if pair.swimmer1.has_special_needs or pair.swimmer2.has_special_needs:
        for instructor in available_instructors:
            if not instructor.can_teach_adapted:
                # Forbid this assignment
                model.Add(y[pair.id, instructor.id] == 0)
```

##### HC-3: Age Category Capabilities

**Babies (age < 2.5) must go to baby-capable instructors**:

```python
for swimmer in individual_swimmers:
    if swimmer.age < 2.5:
        for instructor in available_instructors:
            if not instructor.can_teach_babies:
                model.Add(x[swimmer.id, instructor.id] == 0)

# Similar logic for pairs
for pair in pre_paired_groups:
    if pair.swimmer1.age < 2.5 or pair.swimmer2.age < 2.5:
        for instructor in available_instructors:
            if not instructor.can_teach_babies:
                model.Add(y[pair.id, instructor.id] == 0)
```

**Adults (age >= 18) must go to adult-capable instructors**:

```python
for swimmer in individual_swimmers:
    if swimmer.age >= 18:
        for instructor in available_instructors:
            if not instructor.can_teach_adults:
                model.Add(x[swimmer.id, instructor.id] == 0)

# Similar logic for pairs (though adult pairs are rare in RSS program)
```

##### HC-4: Pairing Compatibility

**Not needed in CP-SAT model**:

- Pre-paired swimmers (same `pair_id`) already satisfy this constraint in the input
- The matching algorithm does not create new pairs
- This constraint is guaranteed by upstream data validation

#### Objective Function

**Goal**: Maximize total compatibility score across all assignments.

```python
# Pre-compute compatibility scores for all possible assignments
compatibility_scores = {}
individual_scores = {}  # Store per-swimmer scores for pairs (explainability)

# Individual swimmers
for swimmer in individual_swimmers:
    for instructor in available_instructors:
        score = calculate_compatibility(swimmer, instructor, rankings)
        compatibility_scores[(swimmer.id, instructor.id)] = score

# Pre-paired groups (using harmonic mean)
for pair in pre_paired_groups:
    for instructor in available_instructors:
        pair_score, score1, score2 = calculate_pair_compatibility(
            pair.swimmer1,
            pair.swimmer2,
            instructor,
            rankings
        )
        compatibility_scores[(pair.id, instructor.id)] = pair_score

        # Store individual scores for explainability
        individual_scores[(pair.id, instructor.id)] = {
            'swimmer1_score': score1,
            'swimmer2_score': score2,
            'pair_score': pair_score
        }

# Define objective
objective_terms = []

# Add terms for individual assignments
for swimmer in individual_swimmers:
    for instructor in available_instructors:
        score = compatibility_scores[(swimmer.id, instructor.id)]
        # Convert float score to integer (CP-SAT requires integer coefficients)
        score_int = int(score * 100)  # Scale to avoid rounding issues
        objective_terms.append(x[swimmer.id, instructor.id] * score_int)

# Add terms for pair assignments
for pair in pre_paired_groups:
    for instructor in available_instructors:
        score = compatibility_scores[(pair.id, instructor.id)]
        score_int = int(score * 100)
        objective_terms.append(y[pair.id, instructor.id] * score_int)

# Maximize total compatibility
model.Maximize(sum(objective_terms))
```

#### Section 5.3.1: Integer Scaling for CP-SAT

CP-SAT only accepts integer coefficients in the objective function. Since our compatibility scores are floats (0-100 with up to 2 decimal places), we must scale them to integers before using them in the model.

**The Problem**:

```python
score = 63.35  # Float - CP-SAT cannot use this directly!
```

**The Solution**: Multiply all scores by 100 and convert to integers

**Why 100x?**

- Our scores have at most 2 decimal places (e.g., 63.35)
- Multiplying by 100 preserves all precision (63.35 × 100 = 6335)
- Maintains relative ordering (if A > B, then A_scaled > B_scaled)
- No integer overflow risk (max value ≈ 18 million for 1800 swimmers; CP-SAT handles up to 2^63 ≈ 9×10^18)

**Examples**:

```python
63.35 → int(63.35 * 100) = 6335
85.12 → int(85.12 * 100) = 8512
72.6  → int(72.6 * 100)  = 7260
100.0 → int(100.0 * 100) = 10000
```

**Mathematical Equivalence**:

The scaled problem produces the same optimal solution as the float problem:

Original (floats): Maximize: (x₁ × 63.35) + (x₂ × 85.12) + (x₃ × 72.6)

Scaled (integers): Maximize: (x₁ × 6335) + (x₂ × 8512) + (x₃ × 7260)

Both have the same optimal assignment because the ranking is preserved:

- 85.12 > 72.6 > 63.35 (floats)
- 8512 > 7260 > 6335 (integers) ✓

**Implementation**:

```python
# === PRE-COMPUTE COMPATIBILITY SCORES ===
compatibility_scores = {}
individual_scores = {}  # Store floats separately for explainability

# For individual swimmers
for swimmer in individual_swimmers:
    for instructor in available_instructors:
        # Calculate float score (0-100)
        score_float = calculate_compatibility(swimmer, instructor, rankings, ref_tables)

        # Scale to integer for CP-SAT
        score_int = int(score_float * 100)

        # Store integer for optimization
        compatibility_scores[(swimmer.id, instructor.id)] = score_int

# For pre-paired swimmers
for pair in pre_paired_groups:
    for instructor in available_instructors:
        # Calculate float scores
        pair_score_float, score1_float, score2_float = calculate_pair_compatibility(
            pair.swimmer1,
            pair.swimmer2,
            instructor,
            rankings,
            ref_tables
        )

        # Scale to integer for CP-SAT
        pair_score_int = int(pair_score_float * 100)

        # Store integer for optimization
        compatibility_scores[(pair.id, instructor.id)] = pair_score_int

        # Store original floats for explainability (human-readable output)
        individual_scores[(pair.id, instructor.id)] = {
            'swimmer1_score': score1_float,    # Keep as float
            'swimmer2_score': score2_float,    # Keep as float
            'pair_score': pair_score_float     # Keep as float
        }

# === BUILD OBJECTIVE FUNCTION ===
objective_terms = []

# Add terms for individual swimmer assignments
for swimmer in individual_swimmers:
    for instructor in available_instructors:
        score_int = compatibility_scores[(swimmer.id, instructor.id)]
        objective_terms.append(
            x[(swimmer.id, instructor.id)] * score_int  # Integer coefficient!
        )

# Add terms for pair assignments
for pair in pre_paired_groups:
    for instructor in available_instructors:
        score_int = compatibility_scores[(pair.id, instructor.id)]
        objective_terms.append(
            y[(pair.id, instructor.id)] * score_int  # Integer coefficient!
        )

# Maximize sum of integer-scaled scores
model.Maximize(sum(objective_terms))
```

**Critical Points**:

1. **Scale UP when building CP-SAT model**: Convert floats to integers by multiplying by 100
2. **Store BOTH versions**:
   - Integer scores for CP-SAT optimization
   - Float scores for explainability and user-facing output
3. **Never scale back down**: CP-SAT just maximizes the sum; we don't need to convert the objective value back to float
4. **All explanations use floats**: When generating output for staff, always reference the original float scores (63.35%, not 6335)

**Example Output**:

When explaining matches to staff:

Emma Wilson → Sarah Chen (63.35%) ← Use float score

Liam Johnson → David Park (85.12%) ← Use float score

NOT:

Emma Wilson → Sarah Chen (6335) ← Don't show scaled integers to users!

**Edge Case**: If you later decide scores should have 3 decimal places (e.g., 63.354), scale by 1000 instead:

```python
score_int = int(score_float * 1000)  # For 3 decimal places
```

For now, 100x is sufficient for 2 decimal places.

### Solving the Model

```python
from ortools.sat.python import cp_model

# Create solver
solver = cp_model.CpSolver()

# Optional: Set time limit (e.g., 10 seconds)
solver.parameters.max_time_in_seconds = 10.0

# Solve
status = solver.Solve(model)

# Check result
if status == cp_model.OPTIMAL:
    print("Found optimal solution")
elif status == cp_model.FEASIBLE:
    print("Found feasible solution (not proven optimal)")
else:
    print("No solution found")
    # This should never happen with valid input
```

### Extracting the Solution

```python
assignments = []

# Extract individual assignments
for swimmer in individual_swimmers:
    for instructor in available_instructors:
        if solver.Value(x[swimmer.id, instructor.id]) == 1:
            assignments.append({
                'type': 'individual',
                'swimmer_id': swimmer.id,
                'instructor_id': instructor.id,
                'compatibility_score': compatibility_scores[(swimmer.id, instructor.id)]
            })

# Extract pair assignments
for pair in pre_paired_groups:
    for instructor in available_instructors:
        if solver.Value(y[pair.id, instructor.id]) == 1:
            assignments.append({
                'type': 'pair',
                'swimmer_1_id': pair.swimmer1.id,
                'swimmer_2_id': pair.swimmer2.id,
                'instructor_id': instructor.id,
                'compatibility_score': compatibility_scores[(pair.id, instructor.id)]
            })
```

### Model Properties

**Complexity**:

- Decision variables: O(n × m) where n = entities, m = instructors
- For typical input: ~15 entities × 8 instructors = 120 variables
- Constraints: O(n + m)
- Very small problem for CP-SAT

**Optimality**:

- CP-SAT guarantees optimal solution if status = OPTIMAL
- Typical solve time: <100ms for this problem size
- Scales to 1800 swimmers without issue

**Feasibility**:

- Solution always exists due to input guarantees:
  - N instructors, N to 2N swimmers
  - Balanced capacity (instructor slots match swimmer count)
- Hard constraints might make some assignments infeasible individually, but global feasibility is guaranteed

---

## Explainability Layer

### Purpose

The CP-SAT solver produces an optimal assignment, but doesn't explain _why_ each assignment was made. The explainability layer translates the mathematical solution into human-readable explanations that staff can understand and verify.

### Components

#### 1. Match Reason Generation

For each assignment, generate a text explanation:

```python
def generate_explanation(assignment, all_instructors, rankings):
    """
    Generates human-readable explanation for an assignment.

    Args:
        assignment: Dict with swimmer(s), instructor, score, and type
        all_instructors: List of all instructors for comparison
        rankings: Color and style ranking tables

    Returns:
        str: Formatted explanation text
    """

    swimmer = assignment['swimmer']  # or swimmer1 if pair
    instructor = assignment['instructor']
    score = assignment['compatibility_score']

    explanation = f"{swimmer.name} → {instructor.name} (Compatibility: {score:.1f}%)\n\n"

    # === WHY THIS MATCH ===
    explanation += "Why this match:\n"

    positive_signals = []
    negative_signals = []

    # Check color ranking
    color_ranking = get_color_ranking(swimmer.swimmer_type_id, rankings)
    primary_color_rank = find_rank(instructor.primary_color_id, color_ranking)
    color_name = get_color_name(instructor.primary_color_id)
    swimmer_type_name = get_swimmer_type_name(swimmer.swimmer_type_id)

    if primary_color_rank <= 2:
        positive_signals.append(
            f"Personality fit: {instructor.name}'s {color_name} personality is "
            f"{'top choice' if primary_color_rank == 1 else '2nd choice'} "
            f"for {swimmer_type_name} swimmers"
        )
    elif primary_color_rank >= 3:
        negative_signals.append(
            f"Personality mismatch: {color_name} is rank {primary_color_rank} of 4 "
            f"for {swimmer_type_name} swimmers"
        )

    # Check style ranking
    style_ranking = get_style_ranking(swimmer.swimmer_type_id, rankings)
    primary_style_rank = find_rank(instructor.primary_style_id, style_ranking)
    style_name = get_style_name(instructor.primary_style_id)

    if primary_style_rank <= 2:
        positive_signals.append(
            f"Teaching style fit: {style_name} is "
            f"{'top choice' if primary_style_rank == 1 else '2nd choice'} "
            f"for this swimmer type"
        )
    elif primary_style_rank >= 4:
        negative_signals.append(
            f"Teaching style mismatch: {style_name} is rank {primary_style_rank} of 6 "
            f"for this swimmer type"
        )

    # Add positive signals
    for signal in positive_signals:
        explanation += f"  ✓ {signal}\n"

    # Add warnings for negative signals
    if negative_signals:
        explanation += "\n"
        for signal in negative_signals:
            explanation += f"  ⚠ {signal}\n"

    # === PAIR EXPLANATION (if applicable) ===
    if assignment.get('is_pair'):
        s1_score = individual_scores[(pair.id, instructor.id)]['swimmer1_score']
        s2_score = individual_scores[(pair.id, instructor.id)]['swimmer2_score']
        pair_score = individual_scores[(pair.id, instructor.id)]['pair_score']

        difference = abs(s1_score - s2_score)

        if difference < 5:
            balance = "both swimmers are well-matched"
        elif difference < 15:
            balance = "swimmers have different but compatible needs"
        else:
            balance = "swimmers have significantly different needs"

        explanation += f"""
Semi-private class balance: {balance}
  • {assignment['swimmer1_name']}: {s1_score:.1f}% individual compatibility
  • {assignment['swimmer2_name']}: {s2_score:.1f}% individual compatibility
  • Pair score: {pair_score:.1f}% (harmonic mean)

Note: The harmonic mean emphasizes the weaker match to ensure both swimmers
receive appropriate instruction. This reflects that class quality is limited
by whichever swimmer is the poorer match.
"""

    # === ALTERNATIVES CONSIDERED ===
    explanation += "\nOther instructors considered:\n"

    alternatives = []
    for alt_instructor in all_instructors:
        if alt_instructor.id == instructor.id:
            continue

        alt_score = calculate_compatibility(swimmer, alt_instructor, rankings)
        alternatives.append((alt_instructor, alt_score))

    # Sort by score (descending)
    alternatives.sort(key=lambda x: x[1], reverse=True)

    # Show top 2-3 alternatives
    for alt_instructor, alt_score in alternatives[:3]:
        explanation += f"  • {alt_instructor.name}: {alt_score:.1f}%\n"

    # === CONCLUSION ===
    explanation += f"\n→ {instructor.name} was the optimal choice among available instructors.\n"

    return explanation
```

**Example Output**:

```
Sophia Martinez → David Park (Compatibility: 87.3%)

Why this match:
  ✓ Personality fit: David's Orange personality works well with Hard Worker swimmers
  ✓ Teaching style fit: Technique Driven is well-suited for this swimmer type

Other instructors considered:
  • Emma Li: 72.1%
  • Alex Chen: 68.5%
  • Sarah Kim: 65.2%

→ David Park was the optimal choice among available instructors.
```

#### 2. Confidence Score Calculation

The confidence score (0-100%) indicates how strongly the algorithm recommends this pairing.

```python
def calculate_confidence(assignment, match_type):
    """
    Calculates confidence score (0-100%) for an assignment.

    Args:
        assignment: Dict with assignment details
        match_type: 'continuity' or 'compatibility'

    Returns:
        float: Confidence percentage (0-100)
    """

    if match_type == 'continuity':
        # Continuity matches have high base confidence
        base_confidence = 85

        # Bonus for longer relationships
        num_sessions = assignment.get('num_sessions', 1)
        relationship_bonus = min(num_sessions * 3, 15)  # +3% per session, max +15%

        return base_confidence + relationship_bonus

    elif match_type == 'compatibility':
        # Start with compatibility score
        base_confidence = assignment['compatibility_score']

        # Apply adjustments

        # Penalty for negative personality signals
        if assignment.get('has_negative_signals', False):
            base_confidence -= 10

        # Slight penalty for pairs (harder to balance two personalities)
        if assignment.get('is_pair', False):
            base_confidence -= 5

        # Bonus if this was a parent request
        if assignment.get('was_parent_request', False):
            base_confidence += 5

        # Bonus if this was the swimmer's top-scored instructor
        if assignment.get('was_first_choice', False):
            base_confidence += 5

        # Penalty if hard constraints limited options significantly
        if assignment.get('limited_options', False):
            base_confidence -= 5

        # Clamp to [0, 100]
        return max(0, min(100, base_confidence))
```

**Confidence Interpretation**:

- **94-100%**: Excellent match (continuity with 3+ sessions, or perfect compatibility)
- **85-93%**: Strong match (recent continuity or very good compatibility)
- **75-84%**: Good match (typical successful assignments)
- **65-74%**: Moderate match (acceptable but worth quick review)
- **50-64%**: Weak match (requires detailed review)
- **Below 50%**: Poor match (flag for manual override)

#### 3. Summary Report Generation

```python
def generate_summary_report(all_assignments, continuity_count, compatibility_count):
    """
    Generates executive summary of matching results.

    Returns:
        str: Formatted summary report
    """

    total_swimmers = continuity_count + compatibility_count
    avg_confidence = sum(a['confidence'] for a in all_assignments) / len(all_assignments)

    report = f"""
=== AQUA ESSENCE MATCHING SUMMARY ===

Time Slot: {all_assignments[0]['time_slot']}
Total Swimmers: {total_swimmers}
Total Instructors: {len(set(a['instructor_id'] for a in all_assignments))}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 1 - CONTINUITY MATCHING:
  ✓ {continuity_count} swimmers ({continuity_count/total_swimmers*100:.0f}%) matched with previous instructor
  ✓ Average relationship length: {calc_avg_sessions(all_assignments):.1f} sessions
  ✓ 0 continuity conflicts

PHASE 2 - COMPATIBILITY MATCHING:
  ✓ {compatibility_count} swimmers ({compatibility_count/total_swimmers*100:.0f}%) matched via optimization
  ✓ Average compatibility score: {calc_avg_compatibility(all_assignments):.1f}%
  ✓ {count_semi_private(all_assignments)} semi-private classes formed
  ✓ All hard constraints satisfied:
      - Adapted swimmers → adapted-capable instructors ✓
      - Babies → baby-capable instructors ✓
      - Semi-private pairs within age/level limits ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATCHES REQUIRING REVIEW (confidence < 75%):
"""

    low_confidence = [a for a in all_assignments if a['confidence'] < 75]

    if low_confidence:
        for assignment in low_confidence:
            report += f"""
  ⚠ {assignment['swimmer_name']} → {assignment['instructor_name']} ({assignment['confidence']:.0f}%)
    Reason: {assignment['review_reason']}
    Suggestion: {assignment['suggestion']}
"""
    else:
        report += "  (None - all matches have confidence ≥ 75%)\n"

    report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OVERALL CONFIDENCE: {avg_confidence:.0f}% average across all matches

Status: Ready for review ✓
"""

    return report
```

#### 4. Output File Generation

The final output is a CSV file (completed `classes.csv`) with annotations:

```python
def generate_output_csv(assignments, classes_template, output_path):
    """
    Generates completed classes.csv with swimmer assignments and confidence scores.
    """

    output_rows = []

    for class_row in classes_template:
        class_id = class_row['class_id']
        instructor_id = class_row['instructor_id']

        # Find assignment for this instructor
        assignment = next(
            (a for a in assignments if a['instructor_id'] == instructor_id),
            None
        )

        if assignment:
            output_rows.append({
                'class_id': class_id,
                'day_of_week': class_row['day_of_week'],
                'start_time': class_row['start_time'],
                'end_time': class_row['end_time'],
                'instructor_id': instructor_id,
                'class_level': f"RSS {assignment['class_level']}",
                'swimmer_1_id': assignment['swimmer_1_id'],
                'swimmer_2_id': assignment.get('swimmer_2_id', ''),
                'match_confidence': round(assignment['confidence'], 1),
                'continuity_dispute': assignment.get('continuity_dispute', False),
            })

    # Write to CSV
    df = pd.DataFrame(output_rows)
    df.to_csv(output_path, index=False)

    return df
```

**Example Output CSV**:

```csv
class_id,day_of_week,start_time,end_time,instructor_id,class_level,swimmer_1_id,swimmer_2_id,match_confidence,continuity_dispute
1,Wednesday,17:00,17:30,3,RSS 5,7,8,71.2,False
2,Wednesday,17:00,17:30,5,RSS 3,9,,78.5,False
3,Wednesday,17:00,17:30,1,RSS 7,1,,94.0,False
4,Wednesday,17:00,17:30,2,RSS 8,4,,87.3,True
```

#### 5. Unassigned Swimmers

Any swimmer who could not be matched must appear in a separate output section with a plain-language reason. This is not an algorithmic failure — it is an operational flag for staff to act on.

```python
def generate_unassigned_report(unassigned_swimmers, reason_map):
    """
    Returns a list of dicts describing swimmers who could not be matched.

    reason_map: dict mapping swimmer_id → reason string, populated during
                Phase 1 and Phase 2 when a swimmer is added to unmatched.
    """
    rows = []
    for swimmer in unassigned_swimmers:
        rows.append({
            'swimmer_id': swimmer.swimmer_id,
            'reason': reason_map.get(swimmer.swimmer_id, 'No available instructor'),
        })
    return rows
```

Common reasons to populate in `reason_map`:

| Reason | When to set |
|---|---|
| `No adapted-capable instructor available` | HC-2 eliminates all instructors for a `has_special_needs` swimmer |
| `No instructor with remaining capacity` | All instructors filled after continuity and compatibility passes |
| `Hard constraints eliminate all instructors` | HC-3 age routing leaves no valid instructor |

The unassigned report is written alongside the main CSV so staff can act on it directly (e.g. request an additional instructor, move the swimmer to a different slot).

---

## Implementation Guide

### Technology Stack

**Required Libraries**:

- `ortools` (Google OR-Tools): For CP-SAT solver
- `pandas`: For CSV file I/O and data manipulation
- `numpy`: For numerical operations (optional, but useful)

**Installation**:

```bash
pip install ortools pandas numpy
```

### Current Project Structure

```
AquaEssence/
├── core/scoring/                   # Shared compatibility scorer
├── solvers/python_cpsat/
│   ├── solver_wrapper.py           # Isolated worker contract
│   └── engine/
│       ├── data_loader.py
│       ├── phase1_continuity.py
│       ├── phase2_cpsat.py
│       ├── phase3_explainability.py
│       ├── pdf_report.py
│       └── tests/
├── data/source/                    # Public reference tables
├── examples/demo/matching/         # Tracked synthetic demonstration
└── data_generation/                # Synthetic development tooling
```

### Implementation Steps

#### Step 1: Data Loading

```python
# src/data_loader.py

import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Swimmer:
    swimmer_id: int
    first_name: str
    last_name: str
    swimmer_type_id: int
    skill_level: int
    age: float
    has_special_needs: bool
    notes: str
    pair_id: Optional[int]

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

@dataclass
class Instructor:
    instructor_id: int
    first_name: str
    last_name: str
    primary_color_id: int
    secondary_color_id: int
    primary_style_id: int
    secondary_style_id: int
    is_team_captain: bool
    can_teach_NL: bool
    can_teach_babies: bool
    can_teach_adults: bool
    can_teach_adapted: bool

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

def load_data(data_dir: str) -> Dict:
    """
    Loads all input CSV files and returns structured data.

    Args:
        data_dir: Path to directory containing input CSV files

    Returns:
        Dict with keys: instructors, swimmers, classes, historical_pairings,
                        rankings, reference_tables
    """

    # Load reference tables
    personality_colors = pd.read_csv(f"{data_dir}/personality_colors.csv")
    instructor_styles = pd.read_csv(f"{data_dir}/instructor_styles.csv")
    swimmer_types = pd.read_csv(f"{data_dir}/swimmer_types.csv")

    color_rankings = pd.read_csv(f"{data_dir}/swimmer_type_color_rankings.csv")
    style_rankings = pd.read_csv(f"{data_dir}/swimmer_type_style_rankings.csv")

    # Load entity tables
    instructors_df = pd.read_csv(f"{data_dir}/instructors.csv")
    swimmers_df = pd.read_csv(f"{data_dir}/swimmers.csv")
    classes_df = pd.read_csv(f"{data_dir}/classes.csv")
    historical_df = pd.read_csv(f"{data_dir}/historical_pairings.csv")

    # Convert to domain objects
    instructors = [
        Instructor(**row)
        for row in instructors_df.to_dict('records')
    ]

    swimmers = [
        Swimmer(**row)
        for row in swimmers_df.to_dict('records')
    ]

    return {
        'instructors': instructors,
        'swimmers': swimmers,
        'classes': classes_df,
        'historical_pairings': historical_df,
        'rankings': {
            'color': color_rankings,
            'style': style_rankings
        },
        'reference_tables': {
            'colors': personality_colors,
            'styles': instructor_styles,
            'swimmer_types': swimmer_types
        }
    }
```

#### Step 2: Compatibility Scoring

```python
# src/compatibility.py

def get_ranking_for_swimmer_type(swimmer_type_id, ranking_table, id_col):
    """
    Retrieves the full ranking for a swimmer type.

    Args:
        swimmer_type_id: ID of the swimmer's personality type
        ranking_table: DataFrame with ranking data
        id_col: Column name for trait ID ('color_id' or 'style_id')

    Returns:
        dict: Mapping of trait_id -> rank
    """
    rows = ranking_table[ranking_table['swimmer_type_id'] == swimmer_type_id]
    return dict(zip(rows[id_col], rows['rank']))


def find_rank(trait_id, ranking_dict):
    """
    Finds the rank of a specific trait in a ranking dictionary.

    Args:
        trait_id: The color_id or style_id to look up
        ranking_dict: Dict mapping trait_id -> rank

    Returns:
        int: The rank (1 = most preferred)
    """
    return ranking_dict.get(trait_id, len(ranking_dict))  # Default to last if missing


def get_style_code(style_id, styles_table):
    """Helper to look up style code from ID."""
    match = styles_table[styles_table['style_id'] == style_id]
    if match.empty:
        return None
    return match.iloc[0]['style_code']


def calculate_compatibility(swimmer, instructor, rankings, ref_tables):
    """
    Calculates compatibility score (0-100) between swimmer and instructor
    using the ranking-based system.

    Args:
        swimmer: Swimmer object with swimmer_type_id
        instructor: Instructor object with color/style IDs
        rankings: Dict with 'color' and 'style' ranking DataFrames
        ref_tables: Dict with reference tables (for style code lookup)

    Returns:
        float: Compatibility score from 0 to 100
    """
    num_colors = 4
    num_styles = 6

    # Step 1: Get rankings for this swimmer type
    color_ranking = get_ranking_for_swimmer_type(
        swimmer.swimmer_type_id, rankings['color'], 'color_id'
    )
    style_ranking = get_ranking_for_swimmer_type(
        swimmer.swimmer_type_id, rankings['style'], 'style_id'
    )

    # Step 2: Find instructor's trait ranks
    primary_color_rank = find_rank(instructor.primary_color_id, color_ranking)
    secondary_color_rank = find_rank(instructor.secondary_color_id, color_ranking)
    primary_style_rank = find_rank(instructor.primary_style_id, style_ranking)
    secondary_style_rank = find_rank(instructor.secondary_style_id, style_ranking)

    # Step 3: Convert ranks to points
    primary_color_points = num_colors - (primary_color_rank - 1)
    secondary_color_points = num_colors - (secondary_color_rank - 1)
    primary_style_points = num_styles - (primary_style_rank - 1)
    secondary_style_points = num_styles - (secondary_style_rank - 1)

    # Step 4: Apply primary/secondary weighting
    primary_color_weighted = primary_color_points * 2.0
    secondary_color_weighted = secondary_color_points * 1.0
    primary_style_weighted = primary_style_points * 2.0
    secondary_style_weighted = secondary_style_points * 1.0

    # Step 5: DIA special case
    instructor_primary_style_code = get_style_code(
        instructor.primary_style_id, ref_tables['styles']
    )
    if instructor_primary_style_code == 'DIA':
        universal_bonus = 3.0
        primary_style_weighted = universal_bonus
        secondary_style_weighted = secondary_style_points * 2.0

    # Step 6: Calculate totals
    color_total = primary_color_weighted + secondary_color_weighted
    style_total = primary_style_weighted + secondary_style_weighted

    # Step 7: Normalize to 0-100
    # Primary ≠ secondary, so bounds account for the constraint:
    color_max = (num_colors * 2.0) + ((num_colors - 1) * 1.0)  # = (4*2) + (3*1) = 11
    color_min = (1 * 2.0) + (2 * 1.0)  # = 4 (worst + second-worst)
    color_normalized = ((color_total - color_min) / (color_max - color_min)) * 100

    style_max = (num_styles * 2.0) + ((num_styles - 1) * 1.0)  # = (6*2) + (5*1) = 17
    style_min = (1 * 2.0) + (2 * 1.0)  # = 4 (worst + second-worst)

    # DIA special case normalization
    if instructor_primary_style_code == 'DIA':
        style_max = 3.0 + (num_styles * 2.0)  # = 3 + 12 = 15
        style_min = 3.0 + (1 * 2.0)  # = 3 + 2 = 5

    style_normalized = ((style_total - style_min) / (style_max - style_min)) * 100

    # Step 8: Combine (equal weight)
    return (color_normalized + style_normalized) / 2


def calculate_pair_compatibility(swimmer1, swimmer2, instructor, rankings, ref_tables):
    """
    Calculates pair compatibility using harmonic mean.

    Returns:
        tuple: (pair_score, score1, score2)
    """
    score1 = calculate_compatibility(swimmer1, instructor, rankings, ref_tables)
    score2 = calculate_compatibility(swimmer2, instructor, rankings, ref_tables)

    # Harmonic mean emphasizes the weaker match
    pair_score = (2 * score1 * score2) / (score1 + score2)
    return pair_score, score1, score2
```

#### Step 3: Phase 1 - Continuity Matching

```python
# src/phase1_continuity.py

def continuity_pass(swimmers, instructors, historical_pairings):
    """
    Phase 1: Greedy continuity matching.
    Assigns swimmers to their previous instructor if available.

    Args:
        swimmers: List of Swimmer objects
        instructors: List of Instructor objects
        historical_pairings: DataFrame with previous instructor assignments

    Returns:
        tuple: (continuity_matches, unmatched_swimmers, available_instructors)
    """

    continuity_matches = []
    unmatched_swimmers = []
    instructor_capacity = {instr.instructor_id: 1 for instr in instructors}

    # Separate individuals and pairs
    individuals = [s for s in swimmers if not has_pair(s, swimmers)]
    pairs = group_pairs(swimmers)

    # Sort individuals by num_sessions (descending) for tiebreaking
    individuals_with_history = []
    for swimmer in individuals:
        history = historical_pairings[
            historical_pairings['swimmer_id'] == swimmer.swimmer_id
        ]
        if not history.empty:
            num_sessions = history.iloc[0]['num_sessions']
            prev_instructor_id = history.iloc[0]['instructor_id']
            individuals_with_history.append((swimmer, prev_instructor_id, num_sessions))

    individuals_with_history.sort(key=lambda x: x[2], reverse=True)

    # Process individuals with continuity
    for swimmer, prev_instructor_id, num_sessions in individuals_with_history:
        # Check if previous instructor is available and has capacity
        if instructor_capacity.get(prev_instructor_id, 0) > 0:
            continuity_matches.append({
                'swimmer_id': swimmer.swimmer_id,
                'instructor_id': prev_instructor_id,
                'num_sessions': num_sessions,
                'is_pair': False,
                'continuity_dispute': False,  # may be set True later by dispute detection
            })
            instructor_capacity[prev_instructor_id] = 0  # Mark as assigned
        else:
            unmatched_swimmers.append(swimmer)

    # Process pairs with continuity (both had same instructor)
    for pair in pairs:
        swimmer1, swimmer2 = pair

        history1 = historical_pairings[
            historical_pairings['swimmer_id'] == swimmer1.swimmer_id
        ]
        history2 = historical_pairings[
            historical_pairings['swimmer_id'] == swimmer2.swimmer_id
        ]

        # Check if both have history with the same instructor
        if not history1.empty and not history2.empty:
            prev_instr1 = history1.iloc[0]['instructor_id']
            prev_instr2 = history2.iloc[0]['instructor_id']

            if prev_instr1 == prev_instr2:
                # Both had same instructor - check availability
                if instructor_capacity.get(prev_instr1, 0) > 0:
                    num_sessions = min(
                        history1.iloc[0]['num_sessions'],
                        history2.iloc[0]['num_sessions']
                    )

                    continuity_matches.append({
                        'swimmer_1_id': swimmer1.swimmer_id,
                        'swimmer_2_id': swimmer2.swimmer_id,
                        'instructor_id': prev_instr1,
                        'num_sessions': num_sessions,
                        'is_pair': True,
                        'continuity_dispute': False,
                    })
                    instructor_capacity[prev_instr1] = 0
                    continue

        # No shared continuity - check for partial dispute:
        # One swimmer has a continuity claim on an available instructor, the other does not.
        # Rule P1-DISP: private (one-on-one) swimmer's claim takes precedence over the pair's.
        # The pair falls through to unmatched; the individual continuity claim is honoured
        # by the individuals_with_history pass above. Flag the dispute on the individual match.
        for instr_history, swimmer in [(history1, swimmer1), (history2, swimmer2)]:
            if not instr_history.empty:
                prev_id = instr_history.iloc[0]['instructor_id']
                # Mark the individual's already-recorded continuity match as disputed
                for m in continuity_matches:
                    if (m.get('swimmer_id') == swimmer.swimmer_id
                            and m.get('instructor_id') == prev_id
                            and not m.get('is_pair', False)):
                        m['continuity_dispute'] = True

        # Add unmatched pair swimmers to be resolved by compatibility pass
        unmatched_swimmers.extend([swimmer1, swimmer2])

    # Add individuals without history to unmatched
    for swimmer in individuals:
        if swimmer not in [s for s, _, _ in individuals_with_history]:
            unmatched_swimmers.append(swimmer)

    # Determine available instructors
    available_instructors = [
        instr for instr in instructors
        if instructor_capacity[instr.instructor_id] > 0
    ]

    return continuity_matches, unmatched_swimmers, available_instructors


def has_pair(swimmer, all_swimmers):
    """Check if swimmer is part of a pre-paired group."""
    if pd.isna(swimmer.pair_id):
        return False

    # Check if another swimmer shares this pair_id
    partners = [s for s in all_swimmers if s.pair_id == swimmer.pair_id and s.swimmer_id != swimmer.swimmer_id]
    return len(partners) > 0


def group_pairs(swimmers):
    """Group pre-paired swimmers into tuples."""
    pairs = []
    processed = set()

    for swimmer in swimmers:
        if swimmer.swimmer_id in processed:
            continue

        if not pd.isna(swimmer.pair_id):
            partners = [
                s for s in swimmers
                if s.pair_id == swimmer.pair_id and s.swimmer_id != swimmer.swimmer_id
            ]
            if partners:
                pairs.append((swimmer, partners[0]))
                processed.add(swimmer.swimmer_id)
                processed.add(partners[0].swimmer_id)

    return pairs
```

#### Step 4: Phase 2 - CP-SAT Optimization

```python
# src/phase2_cpsat.py

from ortools.sat.python import cp_model

def compatibility_pass(unmatched_swimmers, available_instructors, rankings, ref_tables):
    """
    Phase 2: CP-SAT optimization for compatibility-based matching.

    Args:
        unmatched_swimmers: List of Swimmer objects not assigned in Phase 1
        available_instructors: List of Instructor objects with remaining capacity
        rankings: Dict with 'color' and 'style' ranking DataFrames
        ref_tables: Reference tables (colors, styles, swimmer types)

    Returns:
        list: Compatibility matches with scores
    """

    if not unmatched_swimmers or not available_instructors:
        return []

    model = cp_model.CpModel()

    # Separate individuals and pairs
    individuals = [s for s in unmatched_swimmers if not has_pair(s, unmatched_swimmers)]
    pairs = group_pairs(unmatched_swimmers)

    # === DECISION VARIABLES ===

    # x[swimmer_id, instructor_id] = 1 if assigned
    x = {}
    for swimmer in individuals:
        for instructor in available_instructors:
            x[(swimmer.swimmer_id, instructor.instructor_id)] = model.NewBoolVar(
                f'assign_s{swimmer.swimmer_id}_i{instructor.instructor_id}'
            )

    # y[pair_id, instructor_id] = 1 if assigned
    y = {}
    for pair in pairs:
        pair_id = pair[0].pair_id  # Both swimmers share same pair_id
        for instructor in available_instructors:
            y[(pair_id, instructor.instructor_id)] = model.NewBoolVar(
                f'assign_pair{pair_id}_i{instructor.instructor_id}'
            )

    # === HARD CONSTRAINTS ===

    # HC-1: Each swimmer/pair assigned to exactly one instructor
    for swimmer in individuals:
        model.Add(
            sum(x[(swimmer.swimmer_id, instr.instructor_id)]
                for instr in available_instructors) == 1
        )

    for pair in pairs:
        pair_id = pair[0].pair_id
        model.Add(
            sum(y[(pair_id, instr.instructor_id)]
                for instr in available_instructors) == 1
        )

    # HC-1: Each instructor gets at most one entity (individual OR pair)
    for instructor in available_instructors:
        individuals_assigned = sum(
            x[(swimmer.swimmer_id, instructor.instructor_id)]
            for swimmer in individuals
        )
        pairs_assigned = sum(
            y[(pair[0].pair_id, instructor.instructor_id)]
            for pair in pairs
        )
        model.Add(individuals_assigned + pairs_assigned <= 1)

    # HC-2: Adapted routing
    for swimmer in individuals:
        if swimmer.has_special_needs:
            for instructor in available_instructors:
                if not instructor.can_teach_adapted:
                    model.Add(x[(swimmer.swimmer_id, instructor.instructor_id)] == 0)

    for pair in pairs:
        if pair[0].has_special_needs or pair[1].has_special_needs:
            pair_id = pair[0].pair_id
            for instructor in available_instructors:
                if not instructor.can_teach_adapted:
                    model.Add(y[(pair_id, instructor.instructor_id)] == 0)

    # HC-3: Age category capabilities
    for swimmer in individuals:
        for instructor in available_instructors:
            # Babies
            if swimmer.age < 2.5 and not instructor.can_teach_babies:
                model.Add(x[(swimmer.swimmer_id, instructor.instructor_id)] == 0)
            # Adults
            if swimmer.age >= 18 and not instructor.can_teach_adults:
                model.Add(x[(swimmer.swimmer_id, instructor.instructor_id)] == 0)

    # Similar for pairs
    for pair in pairs:
        pair_id = pair[0].pair_id
        for instructor in available_instructors:
            if (pair[0].age < 2.5 or pair[1].age < 2.5) and not instructor.can_teach_babies:
                model.Add(y[(pair_id, instructor.instructor_id)] == 0)
            if (pair[0].age >= 18 or pair[1].age >= 18) and not instructor.can_teach_adults:
                model.Add(y[(pair_id, instructor.instructor_id)] == 0)

    # === OBJECTIVE: MAXIMIZE COMPATIBILITY ===

    # Pre-compute all compatibility scores
    compatibility_scores = {}

    for swimmer in individuals:
        for instructor in available_instructors:
            score = calculate_compatibility(swimmer, instructor, rankings, ref_tables)
            compatibility_scores[(swimmer.swimmer_id, instructor.instructor_id)] = score

    for pair in pairs:
        pair_id = pair[0].pair_id
        for instructor in available_instructors:
            pair_score, score1, score2 = calculate_pair_compatibility(
                pair[0], pair[1], instructor, rankings, ref_tables
            )
            compatibility_scores[(pair_id, instructor.instructor_id)] = pair_score

    # Build objective
    objective_terms = []

    for swimmer in individuals:
        for instructor in available_instructors:
            score = compatibility_scores[(swimmer.swimmer_id, instructor.instructor_id)]
            score_int = int(score * 100)  # Scale to integer
            objective_terms.append(
                x[(swimmer.swimmer_id, instructor.instructor_id)] * score_int
            )

    for pair in pairs:
        pair_id = pair[0].pair_id
        for instructor in available_instructors:
            score = compatibility_scores[(pair_id, instructor.instructor_id)]
            score_int = int(score * 100)
            objective_terms.append(
                y[(pair_id, instructor.instructor_id)] * score_int
            )

    model.Maximize(sum(objective_terms))

    # === SOLVE ===

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        raise RuntimeError("CP-SAT solver failed to find solution")

    # === EXTRACT SOLUTION ===

    compatibility_matches = []

    for swimmer in individuals:
        for instructor in available_instructors:
            if solver.Value(x[(swimmer.swimmer_id, instructor.instructor_id)]) == 1:
                compatibility_matches.append({
                    'swimmer_id': swimmer.swimmer_id,
                    'swimmer_name': swimmer.name,
                    'instructor_id': instructor.instructor_id,
                    'match_type': 'compatibility',
                    'compatibility_score': compatibility_scores[(swimmer.swimmer_id, instructor.instructor_id)],
                    'is_pair': False
                })

    for pair in pairs:
        pair_id = pair[0].pair_id
        for instructor in available_instructors:
            if solver.Value(y[(pair_id, instructor.instructor_id)]) == 1:
                compatibility_matches.append({
                    'swimmer_1_id': pair[0].swimmer_id,
                    'swimmer_2_id': pair[1].swimmer_id,
                    'swimmer_1_name': pair[0].name,
                    'swimmer_2_name': pair[1].name,
                    'instructor_id': instructor.instructor_id,
                    'match_type': 'compatibility',
                    'compatibility_score': compatibility_scores[(pair_id, instructor.instructor_id)],
                    'is_pair': True
                })

    return compatibility_matches
```

#### Step 5: Phase 3 - Explainability

```python
# src/phase3_explainability.py

def generate_explanations(all_matches, instructors, swimmers, rankings, ref_tables):
    """
    Phase 3: Generate human-readable explanations for all matches.

    Args:
        all_matches: Combined list of continuity and compatibility matches
        instructors: List of all instructors
        swimmers: List of all swimmers
        rankings: Color and style ranking tables
        ref_tables: Reference tables

    Returns:
        list: Matches with added explanation text and confidence scores
    """

    annotated_matches = []

    for match in all_matches:
        # Calculate confidence
        if match['match_type'] == 'continuity':
            confidence = calculate_continuity_confidence(match)
        else:
            confidence = calculate_compatibility_confidence(match)

        # Generate explanation
        explanation = generate_match_explanation(
            match, instructors, swimmers, rankings, ref_tables
        )

        annotated_matches.append({
            **match,
            'confidence': confidence,
            'explanation': explanation
        })

    return annotated_matches


def calculate_continuity_confidence(match):
    """Calculate confidence for continuity matches."""
    base = 85
    bonus = min(match.get('num_sessions', 1) * 3, 15)
    return base + bonus


def calculate_compatibility_confidence(match):
    """Calculate confidence for compatibility matches."""
    base = match['compatibility_score']

    # Apply adjustments (placeholder - would need full logic)
    # TODO: Check for negative signals, parent requests, etc.

    return max(0, min(100, base))


def generate_match_explanation(match, instructors, swimmers, rankings, ref_tables):
    """Generate human-readable explanation for a single match."""

    # Get instructor object
    instructor = next(i for i in instructors if i.instructor_id == match['instructor_id'])

    if match['match_type'] == 'continuity':
        if match['is_pair']:
            return (
                f"Continuity: Both {match['swimmer_1_name']} and {match['swimmer_2_name']} "
                f"had {instructor.name} last session ({match['num_sessions']} session(s) together)"
            )
        else:
            return (
                f"Continuity: {match['swimmer_name']} returns to {instructor.name} "
                f"({match['num_sessions']} session(s) together)"
            )

    else:  # compatibility match
        # Get swimmer object(s)
        if match['is_pair']:
            swimmer1 = next(s for s in swimmers if s.swimmer_id == match['swimmer_1_id'])
            swimmer2 = next(s for s in swimmers if s.swimmer_id == match['swimmer_2_id'])
            return f"Optimal compatibility for pair: {match['compatibility_score']:.1f}%"
        else:
            swimmer = next(s for s in swimmers if s.swimmer_id == match['swimmer_id'])

            # Generate detailed compatibility explanation
            signals = analyze_compatibility_signals(swimmer, instructor, rankings, ref_tables)

            explanation = f"Compatibility: {match['compatibility_score']:.1f}%\n"
            if signals['positive']:
                explanation += "  Strengths: " + ", ".join(signals['positive']) + "\n"
            if signals['negative']:
                explanation += "  Considerations: " + ", ".join(signals['negative'])

            return explanation


def analyze_compatibility_signals(swimmer, instructor, rankings, ref_tables):
    """
    Analyzes why a swimmer-instructor pairing has certain compatibility.
    Returns positive and negative signals.
    """
    # TODO: Implement detailed signal analysis
    # This would check each color/style compatibility and generate natural language

    return {
        'positive': ["Good personality fit", "Appropriate teaching style"],
        'negative': []
    }
```

#### Step 6: Main Orchestration

```python
# src/main.py

def main(data_dir, output_dir):
    """
    Main entry point for the matching system.
    Orchestrates all three phases.
    """

    # Load data
    print("Loading data...")
    data = load_data(data_dir)

    # Phase 1: Continuity
    print("Phase 1: Continuity matching...")
    continuity_matches, unmatched_swimmers, available_instructors = continuity_pass(
        data['swimmers'],
        data['instructors'],
        data['historical_pairings']
    )
    print(f"  ✓ {len(continuity_matches)} continuity matches")

    # Phase 2: CP-SAT
    print("Phase 2: Compatibility optimization...")
    compatibility_matches = compatibility_pass(
        unmatched_swimmers,
        available_instructors,
        data['rankings'],
        data['reference_tables']
    )
    print(f"  ✓ {len(compatibility_matches)} compatibility matches")

    # Combine all matches
    all_matches = continuity_matches + compatibility_matches

    # Phase 3: Explainability
    print("Phase 3: Generating explanations...")
    annotated_matches = generate_explanations(
        all_matches,
        data['instructors'],
        data['swimmers'],
        data['rankings'],
        data['reference_tables']
    )

    # Generate output
    print("Writing output files...")
    output_csv = generate_output_csv(
        annotated_matches,
        data['classes'],
        f"{output_dir}/classes_completed.csv"
    )

    summary_report = generate_summary_report(
        annotated_matches,
        len(continuity_matches),
        len(compatibility_matches)
    )

    with open(f"{output_dir}/matching_report.txt", 'w') as f:
        f.write(summary_report)

    print("\n" + "="*60)
    print("MATCHING COMPLETE")
    print("="*60)
    print(summary_report)
    print(f"\nOutput written to: {output_dir}/")


if __name__ == "__main__":
    main(data_dir="./data", output_dir="./output")
```

---

## Testing Strategy

### Unit Tests

**Test compatibility scoring**:

```python
def test_ranking_to_points_conversion():
    """Test that rankings are correctly converted to points."""
    # Rank 1 of 4 colors → 4 points
    assert (4 - (1 - 1)) == 4
    # Rank 4 of 4 colors → 1 point
    assert (4 - (4 - 1)) == 1
    # Rank 1 of 6 styles → 6 points
    assert (6 - (1 - 1)) == 6

def test_compatibility_score_range():
    """Test that scores are always in [0, 100]."""
    score = calculate_compatibility(swimmer, instructor, rankings, ref_tables)
    assert 0 <= score <= 100

def test_dia_universal_bonus():
    """Test that DIA instructors get universal bonus + enhanced secondary."""
    # Create DIA instructor with known secondary style
    # Verify universal bonus (+3) replaces rank-based primary
    # Verify secondary style gets 2.0x weight
    pass

def test_pair_harmonic_mean():
    """Test that pair scoring uses harmonic mean."""
    # Harmonic mean of 80 and 60 = (2*80*60)/(80+60) = 68.57
    pair_score, s1, s2 = calculate_pair_compatibility(
        swimmer1, swimmer2, instructor, rankings, ref_tables
    )
    expected = (2 * s1 * s2) / (s1 + s2)
    assert abs(pair_score - expected) < 0.01
```

**Test continuity phase**:

```python
def test_continuity_tiebreaker():
    """Test that higher num_sessions wins tiebreaker."""
    # Two swimmers both want same instructor
    # One has 3 sessions, other has 1
    # Verify swimmer with 3 sessions gets assigned
    pass

def test_pair_continuity():
    """Test that pairs with shared history are matched correctly."""
    pass
```

**Test CP-SAT phase**:

```python
def test_cpsat_finds_solution():
    """Test that CP-SAT always finds valid solution for balanced input."""
    # Generate balanced input (N instructors, N-2N swimmers)
    # Verify solution exists
    pass

def test_hard_constraints_satisfied():
    """Test that all hard constraints are respected."""
    # Verify no special needs swimmer goes to non-adapted instructor
    # Verify no baby goes to non-baby instructor
    pass
```

### Integration Tests

```python
def test_end_to_end():
    """Test full pipeline with synthetic data."""
    # Load test data
    # Run all three phases
    # Verify output format
    # Verify all swimmers assigned
    pass

def test_all_continuity_scenario():
    """Test when all swimmers have continuity."""
    # No swimmers should go through CP-SAT
    pass

def test_no_continuity_scenario():
    """Test when no swimmers have history."""
    # All swimmers should go through CP-SAT
    pass
```

### Validation Checks

After each run, validate:

1. ✓ All swimmers are assigned
2. ✓ No instructor has more than 2 swimmers
3. ✓ All hard constraints satisfied
4. ✓ Confidence scores in [0, 100]
5. ✓ Output CSV has all required columns

---

## Tuning and Iteration

### Weight Tuning Process

**Step 1: Baseline**

- Start with default weights (2:1, 50/50, DIA flip)
- Run on 10-20 synthetic scenarios
- Collect baseline metrics

**Step 2: Staff Feedback**

- Present output to Aqua Essence
- Ask: "Which matches felt right? Which didn't?"
- Categorize feedback:
  - ✓ Good match (keep as-is)
  - ⚠ Questionable match (investigate)
  - ✗ Bad match (definitely wrong)

**Step 3: Adjust Weights**

- For each bad match, analyze:
  - Was color or style the issue?
  - Should primary/secondary ratio change?
  - Is DIA rule working correctly?

**Step 4: Re-run and Compare**

- Apply new weights
- Compare outputs side-by-side
- Measure improvement in staff agreement

**Step 5: Iterate**

- Repeat until staff agreement is high (>90%)

### Configurable Weights

Make weights easily tunable:

```python
# config.py

WEIGHTS = {
    'color_primary': 2.0,
    'color_secondary': 1.0,
    'style_primary': 2.0,
    'style_secondary': 1.0,
    'dia_universal_bonus': 3.0,    # DIA primary style bonus
    'dia_secondary_weight': 2.0,   # DIA secondary style weight (enhanced)
    'color_vs_style': 0.5,         # 0.5 = equal weight (50/50)
}

def calculate_compatibility_with_config(swimmer, instructor, rankings, ref_tables, weights=WEIGHTS):
    # Use weights from config
    pass
```

### Metrics to Track

| Metric                       | Target    | Purpose                                 |
| ---------------------------- | --------- | --------------------------------------- |
| Continuity preservation rate | >95%      | Ensure continuity is prioritized        |
| Average compatibility score  | >75       | Ensure quality of compatibility matches |
| Staff agreement rate         | >90%      | Validate that matches feel right        |
| Low-confidence match rate    | <15%      | Minimize need for manual review         |
| Solve time                   | <1 second | Ensure scalability                      |

---

## Appendix: Design Decisions Summary

| Decision                       | Choice                                              | Rationale                                                     |
| ------------------------------ | --------------------------------------------------- | ------------------------------------------------------------- |
| **Compatibility system**       | Ranking-based (1st, 2nd, 3rd...)                    | Simpler data collection, no conflicts, easier to explain      |
| **Point conversion**           | Linear (1st = max points, descending)               | Intuitive, auto-scales with option changes                    |
| **Primary:Secondary ratio**    | 2:1                                                 | Primary traits are more defining, but secondary still matters |
| **Color:Style balance**        | 50/50 after normalization                           | Both dimensions equally emphasized in domain                  |
| **DIA instructor handling**    | Universal bonus (+3) + secondary style at 2x weight | Captures versatility while allowing differentiation           |
| **Pair compatibility scoring** | Harmonic mean                                       | Emphasizes weaker match, models bottleneck effect naturally   |
| **Score scale**                | 0-100                                               | Intuitive percentage, matches confidence score format         |
| **Optimization method**        | CP-SAT                                              | Guarantees optimal solution, handles constraints elegantly    |
| **Architecture**               | Three-phase (continuity, CP-SAT, explainability)    | Separates concerns, maintains transparency                    |

---

## Document Change Log

| Version | Date          | Changes                                                                         |
| ------- | ------------- | ------------------------------------------------------------------------------- |
| 1.0     | February 2026 | Initial specification                                                           |
| 2.0     | February 2026 | Migration to ranking-based compatibility system with harmonic mean pair scoring |

---

## References

- Google OR-Tools CP-SAT Documentation: https://developers.google.com/optimization/cp/cp_solver
- Aqua Essence Domain Requirements: See project README.md
- Compatibility Scoring Research: Based on domain expert interviews

---

**End of Specification**
