# Aqua Essence Matching Process Rules and Guidelines

This document describes how the current matching process works in the Python
CP-SAT production pipeline. The discontinued C++ and experimental legacy
solvers are not part of the active application.

## 1. Purpose

The system assigns swimmers to instructor-led class slots for the Ready, Set, Swim! program.

The matching process tries to:

1. Preserve swimmer-instructor continuity when appropriate.
2. Fill as many swimmers as possible.
3. Respect hard safety and routing constraints.
4. Optimize personality/teaching-style compatibility.
5. Produce explainable results for staff review.

## 2. Main Inputs

The solver expects a request containing paths to these CSV files:

- `classes.csv`
- `swimmers.csv`
- `instructors.csv`
- `historical_pairings.csv`
- Reference CSVs:
  - `personality_colors.csv`
  - `instructor_styles.csv`
  - `swimmer_types.csv`
  - `swimmer_type_color_rankings.csv`
  - `swimmer_type_style_rankings.csv`

## 3. Class Data Rules

Each class row represents one instructor capacity slot.

The Python loaders accept either of these class formats:

- Generated/internal format with `instructor_id`.
- Partner/Jackrabbit-style internal format with `instructor_name`.

When `instructor_id` is present and non-empty, it is used directly.

When `instructor_name` is present, the loader resolves names like `Olivia R.` by matching:

- first name exactly, and
- last initial against the start of the instructor last name.

Day abbreviations are normalized:

- `Mon` -> `Monday`
- `Tue` -> `Tuesday`
- `Wed` -> `Wednesday`
- `Thu` -> `Thursday`
- `Fri` -> `Friday`
- `Sat` -> `Saturday`
- `Sun` -> `Sunday`

Times with `AM` or `PM` are normalized to 24-hour format:

- `07:30 AM` -> `07:30`
- `06:30 PM` -> `18:30`

Times already in 24-hour format are kept as-is.

## 4. Jackrabbit Class Export Rules

The FastAPI backend can detect and convert Jackrabbit/partner class exports before solving.

The expected partner class columns include:

- `Location`
- `Class`
- `Status`
- `Session`
- `Start Date`
- `End Date`
- `Days`
- `Start Time`
- `End Time`
- `Instructors`
- `Cat 1`
- `Open`
- `Size`

During conversion:

1. Rows with `Status != Active` are skipped.
2. Rows without an instructor are skipped.
3. Multi-instructor cells are split into one row per instructor.
4. Dates are converted from `M/D/YYYY` or `M/D/YY` to `YYYY-MM-DD`.
5. New `class_id` values are assigned sequentially.
6. `cat_2` is left blank because there is no source field in the partner export.
7. The converted class file uses `instructor_name`, not `instructor_id`.

`backend/csv_import.py` performs this conversion for the active FastAPI
application before the Python CP-SAT solver runs.

## 5. Swimmer Data Rules

Each swimmer row contains:

- `swimmer_id`
- `first_name`
- `last_name`
- `swimmer_type_id`
- `skill_level`
- `age`
- `has_special_needs`
- `notes`
- `pair_id`

`pair_id` controls pre-paired swimmers:

- Blank or missing `pair_id` means the swimmer is an individual.
- Exactly two swimmers with the same `pair_id` are treated as a pair.
- One swimmer with a `pair_id` is treated as an individual.
- More than two swimmers with the same `pair_id` raises an error.

`swimmer_type_id = 0` is the non-response sentinel — assigned when no survey data exists
(e.g., Jackrabbit import with no linked survey). Neutral compatibility rankings are used
so the swimmer can still be matched. Every match for a type-0 swimmer is flagged with
`non_response_swimmer_type` for staff review.

## 6. Instructor Data Rules

Each instructor row contains:

- `instructor_id`
- `first_name`
- `last_name`
- `primary_color_id`
- `secondary_color_id`
- `primary_style_id`
- `secondary_style_id`
- `is_team_captain`
- `can_teach_NL`
- `can_teach_babies`
- `can_teach_adults`
- `can_teach_adapted`

The solver uses capability flags for hard constraints and color/style IDs for compatibility scoring.

## 7. Reference Data Validation

The loader validates:

- instructor color IDs exist in `personality_colors.csv`
- instructor style IDs exist in `instructor_styles.csv`
- swimmer type IDs exist in `swimmer_types.csv`

The ranking loader validates:

- every swimmer type has a complete ranking for all 4 colors
- every swimmer type has a complete ranking for all 6 teaching styles
- each ranking set is a valid permutation

## 8. Matching Pipeline Overview

The Python CP-SAT solver runs in three phases:

1. Phase 1: Continuity matching
2. Phase 2: Compatibility optimization
3. Phase 3: Explainability, confidence, reports, and output files

The final output includes:

- `result.json`
- `classes_filled.csv`
- `report.txt`
- optional `matching_report.pdf`
- `profiles.json`

## 9. Hard Constraints

### HC-1: Capacity

Each instructor/class slot can receive at most one entity.

An entity is either:

- one individual swimmer, or
- one pair of swimmers.

An individual swimmer can be assigned to at most one instructor.

A pair can be assigned to at most one instructor.

Swimmers may remain unassigned if no legal capacity exists.

### HC-2: Adapted Routing

In Phase 2, swimmers with `has_special_needs = True` can only be assigned to instructors where `can_teach_adapted = True`.

For pairs, if either swimmer has special needs, the instructor must be adapted-capable.

Continuity exception:

- Phase 1 can allow a continuity match that violates adapted capability.
- That match is flagged for review with adapted override flags.
- This is a client-policy exception, not a Phase 2 rule.

### HC-3: Age Routing

Baby swimmers are swimmers younger than 2.5 years.

Baby swimmers require `can_teach_babies = True`.

Adult swimmers are swimmers aged 18 or older.

Adult swimmers require `can_teach_adults = True`.

For pairs:

- if either swimmer is a baby, the instructor must be baby-capable
- if either swimmer is an adult, the instructor must be adult-capable

Continuity does not override age routing.

### HC-4: Pair Compatibility

The configured pair limits are:

- max RSS level difference: 1
- max age difference: 2 years

Current-code note:

The thresholds exist in `config.py`, but the current Python CP-SAT phase does not visibly add constraints that reject invalid pre-paired swimmers by age or level difference. Treat this as a known implementation gap unless a separate pre-validation step is added.

## 10. Notes Rules

The notes parser recognizes these keywords:

- `prefer <instructor name>`
- `avoid <instructor name>`
- `no <instructor name>`
- `always <instructor name>`
- `never <instructor name>`

Notes are parsed by semicolon-delimited clauses.

Examples:

- `prefer Olivia Robertson`
- `avoid Ava Anderson`
- `always Olivia Robertson; never Ava Anderson`

`no` is treated as a synonym for `avoid`.

The parser expects full instructor names, not short Jackrabbit names.

### Notes in Phase 1

Continuity is skipped if notes say `avoid` or `never` for the previous instructor.

The swimmer then goes to Phase 2.

### Notes in Phase 2

`avoid` and `never` become hard exclusions.

An excluded instructor cannot be assigned to that swimmer.

For pairs, if either swimmer blocks an instructor, the pair cannot be assigned to that instructor.

`prefer` adds a compatibility boost.

`always` adds a larger compatibility boost.

Current-code note:

`always` is a strong preference boost, not an absolute hard assignment requirement in Phase 2.

## 11. Phase 1: Continuity Matching Rules

Continuity runs first when enabled.

It uses `historical_pairings.csv`.

It is greedy and deterministic.

Instructor capacity starts at 1 for every instructor.

The phase separates swimmers into individuals and pairs.

### Individual Continuity

Individuals with history are processed before individuals without history.

Individuals with history are sorted by `num_sessions` descending.

The swimmer is assigned to their previous instructor if:

1. notes do not block that instructor,
2. age routing allows the match,
3. adapted routing allows the match,
4. the instructor still has capacity.

If assigned:

- the instructor capacity becomes 0
- the match type is `continuity`
- `num_sessions` is retained for explanation

If blocked:

- the swimmer goes to Phase 2
- flags may be recorded, depending on the reason

### Pair Continuity

A pair receives continuity only if both swimmers have history with the same previous instructor.

If both swimmers share the same previous instructor, the pair is assigned if:

1. notes do not block the instructor,
2. age routing allows both swimmers,
3. adapted routing is either satisfied or allowed as a flagged override,
4. the instructor still has capacity.

The pair's continuity session count is the minimum of both swimmers' historical session counts.

If the shared instructor was already taken by an individual continuity claim:

- both swimmers are marked as disputed
- continuity conflict flags may be added
- the pair goes to Phase 2

Pairs without shared continuity go to Phase 2.

## 12. Phase 2: CP-SAT Compatibility Optimization

Phase 2 receives:

- swimmers not assigned in Phase 1
- instructors still available after Phase 1

It uses Google OR-Tools CP-SAT.

The model creates binary decision variables:

- `x[swimmer, instructor]` for individual assignments
- `y[pair, instructor]` for pair assignments

The solver accepts `OPTIMAL` or `FEASIBLE` solutions.

If no feasible assignment exists, it returns no Phase 2 matches.

### Phase 2 Objective

The objective is:

1. maximize the number of assigned swimmers first
2. then maximize compatibility score

This is implemented by giving assignment count a weight larger than any possible compatibility improvement.

That means one extra assigned swimmer outweighs a better compatibility arrangement among fewer swimmers, but only among assignments that meet the minimum auto-assignment quality floor.

Pairs count as two assigned swimmers.

### Phase 2 Quality Floor

Phase 2 does not auto-assign matches below `min_auto_assign_score`.

The default is 50.0.

Any legal individual or pair candidate with compatibility below this threshold is made infeasible in the CP-SAT model.

This prevents the solver from forcing poor matches just to maximize the number of assigned swimmers.

Operational interpretation:

- 50+ can be auto-assigned if legal and optimal.
- Below 50 is left unassigned for manual review or override.
- The threshold can be overridden in solver config with `min_auto_assign_score`.

Notes boosts are applied before this threshold is checked, so a `prefer` or `always` request can lift a candidate above the auto-assignment floor.

When a swimmer is unassigned because every legal candidate is below the quality floor, the unassigned result includes:

- `flag_codes: ["below_min_auto_assign_score"]`
- `best_available_score`
- `best_available_instructor_id`
- `best_available_instructor_name`
- `min_auto_assign_score`

This distinguishes quality-floor unassignment from capacity failure or hard-constraint failure.

### Phase 2 Time Limit

If `max_time_seconds` is provided in config and is positive, it is used.

Otherwise:

- up to 75 entities and 75 instructors: 20 seconds
- up to 250 entities and 250 instructors: 30 seconds
- up to 450 entities and 450 instructors: 45 seconds
- larger: 60 seconds

`num_workers = 0`, which lets OR-Tools use available cores.

## 13. Greedy Solution Hint

Before solving, the CP-SAT model receives a greedy hint.

The hint:

1. builds feasible options for each individual and pair
2. sorts entities by:
   - fewest feasible instructors first
   - pairs before individuals when feasibility is tied
   - higher best score when still tied
3. assigns each entity to the highest-scoring still-available instructor
4. passes those tentative assignments as CP-SAT hints

The hint does not force the final solution.

It only helps the solver find a good feasible solution faster.

## 14. Compatibility Scoring

Compatibility is ranking-based, not binary.

Each swimmer type ranks:

- 4 personality colors
- 6 teaching styles

Rank 1 is best.

Ranks are converted to points:

- color points = `4 - (rank - 1)`
- style points = `6 - (rank - 1)`

### Color Score

Instructor primary and secondary colors are scored.

Weights:

- primary color: 2.0
- secondary color: 1.0

Color raw score is normalized to 0-100.

Normalization assumes primary and secondary colors differ:

- best: rank 1 primary plus rank 2 secondary
- worst: rank 4 primary plus rank 3 secondary

### Style Score

Instructor primary and secondary styles are scored.

Weights:

- primary style: 2.0
- secondary style: 1.0

Style raw score is normalized to 0-100.

### DIA Style Rule

If the instructor's primary style code is `DIA`, the scorer uses a special Do-It-All rule.

For DIA:

- primary style rank is replaced by a universal bonus of 3.0
- secondary style receives an enhanced weight of 2.0
- DIA-specific normalization bounds are used

### Final Individual Compatibility

Final compatibility is:

- 50% color score
- 50% style score

The result is rounded to two decimals.

### Pair Compatibility

For pairs:

1. score swimmer 1 with the instructor
2. score swimmer 2 with the instructor
3. combine using harmonic mean

Formula:

`pair_score = (2 * score1 * score2) / (score1 + score2)`

If either score is zero, the pair score is zero.

The harmonic mean penalizes lopsided pairs where one swimmer fits much worse than the other.

## 15. Notes Boosts

After base compatibility scoring:

- `prefer` adds 15 points
- `always` adds 40 points

Scores are capped at 100.

For pairs, the solver uses the maximum applicable boost from either swimmer.

## 16. Phase 3: Explainability and Confidence

Phase 3 annotates every match with:

- instructor object
- `instructor_name`
- confidence score
- detailed explanation
- short reason summary
- review flags

Continuity explanations state the previous instructor relationship and session count.

Compatibility explanations include:

- assigned swimmer(s)
- assigned instructor
- compatibility score
- positive signals
- considerations
- top alternative instructors considered

## 17. Confidence Formula

Confidence is not the same as compatibility.

Compatibility decides Phase 2 optimization.

Confidence estimates how much human review the result needs.

### Signal 1: Base Confidence

Continuity matches start at 90.

Compatibility matches use tiers:

- compatibility >= 75: base 80
- compatibility 50-74: base 65
- compatibility 25-49: base 45
- compatibility < 25: base 25

### Signal 2: Margin Bonus

For compatibility matches:

`margin = top_score - second_best_score`

`margin_bonus = min(10, margin / 5)`

Current-code note:

The confidence function expects `top_score` and `second_best_score`, but the current CP-SAT extraction path does not populate them in the match dict. In that case, the margin defaults to zero.

### Signal 3: Pair Weakness Penalty

For pairs:

1. calculate harmonic mean of individual scores
2. compare it to the weaker swimmer's score
3. subtract half of the difference if positive

This penalizes pair assignments where the combined score hides weakness for one swimmer.

### Signal 4: Dispute Penalty

If a swimmer was involved in a continuity dispute, subtract 10.

This mainly applies when pair continuity lost to an individual continuity claim.

### Signal 5: Forced Assignment Penalty

For compatibility matches, if the swimmer has one or fewer eligible instructors under HC-2 and HC-3, subtract 5.

Final confidence is clamped between 0 and 100.

## 18. Confidence Categories

Confidence categories are:

- 90-100: Excellent
- 80-89: Strong
- 70-79: Good
- 60-69: Moderate
- 50-59: Weak
- below 50: Poor

Matches below 70 are listed as requiring review in the summary report.

## 19. Review Flags

The system uses shared flag vocabulary from `core/flag_vocabulary.json`.

Flags can come from:

- continuity blocked by adapted, baby, or adult capability
- continuity capacity conflicts
- continuity pairing conflicts
- forced assignments
- adapted swimmer with only one adapted-capable instructor in the pool
- best legal match below the minimum auto-assign score
- non-response swimmer type (swimmer_type_id = 0 — survey data missing, staff should update)

For each completed class row, the output includes:

- `flag_codes`
- `flag_summary`
- `review_action`
- `review_severity`

Highest-severity flag controls the primary review action.

## 20. Output CSV Rules

The solver writes `classes_filled.csv`.

For assigned classes, it includes:

- class ID
- day
- start/end time
- instructor name
- instructor ID
- class level
- swimmer names and IDs
- match type
- compatibility score
- match confidence
- match reason
- continuity dispute flag
- review flags and actions

For pair assignments:

- class level is the lower/minimum RSS level of the two swimmers
- swimmer 1 and swimmer 2 columns are populated

For individual assignments:

- class level is that swimmer's RSS level
- only swimmer 1 columns are populated

For unfilled class slots:

- instructor ID remains present
- assignment columns are blank
- review severity is `none`

Rows are sorted by match confidence ascending, with empty confidence rows treated as high priority after assigned low-confidence rows.

## 21. Result JSON Rules

The wrapper writes `result.json` with:

- `ok`
- `result_files`
- `summary`
- `matches`
- `unassigned`

For each match, the JSON includes:

- match type: individual or pair
- instructor ID and name
- confidence
- compatibility score
- reason
- reason summary
- match type: continuity or compatibility
- explanation
- continuity dispute flag
- swimmer IDs and names

For unassigned swimmers, it includes:

- swimmer ID
- swimmer name
- skill level
- age
- special-needs flag
- reason

## 22. Unassigned Reason Rules

Unassigned reasons are inferred after matching.

Possible reason categories include:

- no adapted-capable instructor available
- no baby-capable instructor available
- no adult-capable instructor available
- hard constraints eliminate all instructors
- no instructor capacity remaining

## 23. Operational Guidelines

Use `python start.py` to launch the current application. The FastAPI app and
application factory are defined in `backend/server.py` and
`backend/application.py`.

Use the Python CP-SAT solver for production behavior.

Use graph-based and greedy-based solvers for comparison or fallback behavior.

Use the C++ exact solver carefully when class files use `instructor_name`; the C++ binary expects `instructor_id`.

Keep scoring weights in `core/scoring/config.py`.

Keep solver thresholds and confidence settings in `solvers/python_cpsat/engine/config.py`.

Do not hardcode weights or thresholds inside phase logic.

Regenerate or validate CSV data before solving if reference IDs change.

The production loader rejects non-finite ages, ages outside 0–100, RSS skill
levels outside 1–12, duplicate entity IDs, malformed pair groups, and pairs
that violate HC-4. Missing baby, adult, or adapted instructor qualifications
default to `false`; staff must explicitly confirm those safety capabilities.

Review all matches below 70 confidence.

Review all matches with non-empty flag codes.

Review continuity qualification blocks and correct stale instructor capability records when necessary.

Manually review continuity disputes.

Manually review forced assignments where only one legal instructor exists.

Do not assume `always` in notes is a hard constraint; current code treats it as a strong score boost.

HC-4 age/level pair validation is enforced in every assignment phase and by the final result validator.

## 24. Jackrabbit Session Cycle

The full session cycle for Jackrabbit-sourced data:

1. **Export from Jackrabbit:** Export Classes and Students as CSV from the Jackrabbit dashboard.
2. **Upload to the app:** The FastAPI backend auto-detects the partner format and converts transparently.
   - Classes: upload as the classes file in `POST /api/generate`.
   - Students: upload as the swimmers file in `POST /api/generate`.
3. **Supply instructors.csv manually:** Jackrabbit has no instructor export. Staff must provide the internal `instructors.csv` separately each session.
4. **Supply historical_pairings.csv from the prior session:** Jackrabbit has no historical pairings export. After the first session, use `POST /api/generate_historical_pairings` with the session label (e.g., `"2026-Spring"`) to generate `historical_pairings.csv` from the last completed job's `classes_filled.csv`. Download and store this file; upload it as the historical pairings input for the next session. For the very first session, request a one-time class history export from the Jackrabbit account administrator.
5. **Set skill_level before solving:** Jackrabbit Students exports do not include RSS skill level. Staff must edit the converted swimmers CSV to add each swimmer's level (1–12) before the solver can produce correct class assignments. The loader rejects the import placeholder value `0`; the import warning will remind staff if this step was skipped.
6. **Review non-response flags:** Any swimmer imported from Jackrabbit will have `swimmer_type_id = 0` until survey data is linked. Every match for such a swimmer will carry a `non_response_swimmer_type` review flag prompting staff to update the type.

### What Jackrabbit Does NOT Export

| Data | Status |
|---|---|
| `instructors.csv` | Not exported. Must be managed separately by staff. |
| `historical_pairings.csv` | Not exported. Generate from prior session output via `POST /api/generate_historical_pairings`. |
| `swimmer_type_id` | Not exported. Defaults to 0 (non-response) until survey data is linked. |
| `skill_level` (RSS level) | Not exported. Must be supplied manually before solving. |
