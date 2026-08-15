# Aqua Essence 0.2.0 User Manual

This manual explains how to prepare input files, run the application, review
the results, and maintain the reference data used by the matching system. It
covers Aqua Essence 0.2.0, which supports Jackrabbit Exporter 1.1.0 through
bundle contract version 1.

## 1. What The App Does

Aqua Essence matches swimmers to instructors for RSS classes. The app uses:

- `classes.csv` to define the class rows and assigned instructors for a time slot
- `swimmers.csv` to define which swimmers need to be placed
- `instructors.csv` to define which instructors are available and what profiles they have

The app can also read Jackrabbit partner exports directly from `.csv`, `.xlsx`, and `.xlsm` files. If you pick a partner export, Aqua Essence converts it to the internal format automatically when you generate a solution.

If you use Excel workbooks, the app reads the first worksheet in the file. If your export is not on the first sheet, save it as CSV first or move the export to the first sheet.

## 2. Starting The App

For normal use, start the application from the Aqua Essence desktop or Start
menu shortcut. The app opens in its own desktop window and starts its local
matching service automatically.

You do not need to run Python commands, open `index.html`, or start the server manually.

You do not need to run a `.bat` file. Source-development launch instructions
are separate from the normal operator workflow.

## 3. Core Files You Need

For a real matching run, start with these three files:

| File | Required | Purpose | Typical Source |
| --- | --- | --- | --- |
| `classes.csv` | Yes | Defines the classes that need swimmers and which instructor is tied to each row | Jackrabbit classes export |
| `swimmers.csv` | Yes | Defines the swimmers to place into classes | Jackrabbit students export |
| `instructors.csv` | Yes | Defines the active teaching staff available for matching | Jackrabbit ActiveStaff export |

You can also supply these optional files in **Data & settings**:

| File | Required | Purpose |
| --- | --- | --- |
| `historical_pairings.csv` | No | Preserves continuity with previous instructors |
| `swimmer_type_color_rankings.csv` | No | Color preference ranking for each swimmer type |
| `swimmer_type_style_rankings.csv` | No | Style preference ranking for each swimmer type |
| `personality_colors.csv` | No | Lookup table for instructor personality colors |
| `instructor_styles.csv` | No | Lookup table for instructor teaching styles |
| `swimmer_types.csv` | No | Lookup table for swimmer types |

## 4. How To Generate A Solution

### Step 1: Open the app

Launch Aqua Essence and wait until the status in the lower-left corner reads
**Host: online**.

### Step 2: Select the three core files

In the **Matching** workspace:

1. Select `classes.csv`
2. Select `swimmers.csv`
3. Select `instructors.csv`

The **Generate matching** button becomes available only when all required
sources are ready. You can also choose **Use database instructors** instead of
selecting an instructor file.

### Step 3: Add optional files if you have them

Open **Data & settings** from the left navigation. Review historical sessions,
reference data, rankings, and instructor defaults, then return to **Matching**.

Notes:

- If you do not select `historical_pairings.csv`, the app can proceed with an empty history file.
- The app remembers your last selected files and restores them on the next launch.

### Step 4: Click `Generate matching`

When you click **Generate matching**, Aqua Essence:

1. Validates the selected files.
2. Detects whether each selected file is already in the internal format or is a Jackrabbit partner export.
3. Converts partner exports automatically when needed.
4. Normalizes swimmer and instructor data before solving.
5. Runs the selected solver.
6. Opens the **Results** workspace.

### Step 5: Review the outputs

After a successful run, the UI shows:

- A results summary with assigned swimmers, unassigned swimmers, classes, empty classes, and average confidence
- A match table with instructor, swimmer, confidence, flags, and reason
- An unassigned swimmers table when applicable
- A button to download the filled classes CSV
- A button to open the latest matching report PDF, when produced
- An **Explain decisions** action and an **Explainability** workspace

Select a result row to open its review drawer, or select a swimmer or instructor
name to open profile details. Use the result search and review-status filter to
narrow a large run.

## 5. Jackrabbit Export Requirements

Use **Import export** for the supported Jackrabbit Exporter workflow. Select the
file named `aqua_essence_jackrabbit_export.json` produced by Jackrabbit Exporter
1.1.0. Aqua Essence 0.2.0 accepts bundle format
`aqua-essence-jackrabbit-export`, bundle contract version 1 only
(`format_version: 1`).

The bundle must contain exactly these four embedded CSV files:

- `jackrabbit_students.csv` — required and must contain usable student rows
- `jackrabbit_classes.csv` — required and must contain usable class rows
- `jackrabbit_staff.csv` — optional data; a header-only file is valid
- `jackrabbit_pairings.csv` — optional history; a header-only file is valid

The app validates the locked version-1 headers before changing the selected run
sources. It preserves quoted commas, doubled quotes, embedded line breaks, and
leading zeroes in every external ID. For classes with multiple instructors,
each `Class ID`/`instructor_id` assignment remains a separate row with the
original Class ID.

After import, review every warning:

- A missing `Skill Level` or `Special Needs` value stays blank; Aqua Essence
  does not infer it from another field.
- Imported swimmers use `Non-Response / Unknown` until intake or survey data is
  supplied.
- Staff data supplies identity only. Existing desktop-curated instructor
  profiles are preserved. New or partial instructor identities must have their
  colors, styles, and teaching qualifications completed in **Data & settings**
  before matching can run.
- Invalid or duplicate optional historical-pairing rows are skipped and counted
  in the import warnings.

The app still supports selecting standalone internal or legacy partner files
manually. That is a separate compatibility workflow; it is not the Jackrabbit
Exporter 1.1.0 bundle contract.

## 6. Recommended Jackrabbit Export Checklist

For the normal desktop workflow, capture students and classes in the browser
extension, optionally capture staff and pairing history, then choose **Download
Aqua Essence bundle**. In Aqua Essence, choose **Import export** and select
`aqua_essence_jackrabbit_export.json`. The app validates the bundle, selects
the run sources, adds missing instructors without replacing edited profiles,
and imports any historical pairings. The bundle always contains all four
version-1 CSV names; staff and historical pairings may contain only their
header row.

Before running a real session, verify:

- The import summary reports the expected student, class, staff, and historical
  pairing counts.
- Every warning about missing skill levels and special-needs values has been
  reviewed.
- Every new instructor has an explicitly completed profile and teaching
  qualifications.
- Every multi-instructor class shows each expected Class ID/instructor ID row.
- The source summary shows the imported classes, swimmers, and database
  instructors as ready.

## 7. Editing Swimmer Types, Colors, Styles, And Rankings

Open **Data & settings** to manage the reference data that drives compatibility scoring.

### 7.1 Add Or Edit Personality Colors

Use the `personality_colors.csv` row and click **Add / edit**.

This editor lets you maintain:

- `color_name`
- `traits`

Use this when the program wants to rename a color or change its descriptive traits.

### 7.2 Add Or Edit Instructor Styles

Use the `instructor_styles.csv` row and click **Add / edit**.

This editor lets you maintain:

- `style_code`
- `style_name`
- `traits`
- `expertise_area`

Use this when a teaching style is renamed, a new style is introduced, or the style descriptions need updating.

### 7.3 Add Or Edit Swimmer Types

Use the `swimmer_types.csv` row and click **Add / edit**.

This editor lets you maintain the swimmer type names used throughout the system.

Important note:

- The hidden system type `Non-Response / Unknown` is used internally and is not treated like a normal public swimmer type in the editor workflow.

### 7.4 Edit Color Rankings

Use the `swimmer_type_color_rankings.csv` row and click **Edit rankings**.

This editor lets you reorder the color preferences for each swimmer type.

How it works:

- Pick a swimmer type from the drop-down.
- Drag items or use the move buttons to change the order.
- Save when done.

Best practice:

- If you need a brand new color, add it through `personality_colors.csv` first, then reopen the rankings editor and place it correctly for each swimmer type.

### 7.5 Edit Style Rankings

Use the `swimmer_type_style_rankings.csv` row and click **Edit rankings**.

This editor works the same way as the color rankings editor, but for instructor teaching styles.

Best practice:

- If you need a brand new style, add it through `instructor_styles.csv` first, then reopen the rankings editor and place it correctly for each swimmer type.

### 7.6 Edit Instructor Styles And Colors Directly On The Selected Instructor File

After you select an instructors file, an **Edit styles and colors** button appears beside it.

Use this when you want to update instructor personality and style assignments directly in the selected instructor source file.

This is especially useful when:

- the selected instructors file is a partner staff export that already contains profile columns
- you need to correct style or color IDs before generating
- you want to reduce how many rows fall back to the default instructor profile

### 7.7 Edit The Default Instructor Profile

In **Data & settings**, click **Edit** beside **Default instructor profile**.

This controls the fallback values used when an instructor row is missing:

- primary color
- secondary color
- primary style
- secondary style
- team captain flag
- NL flag
- baby qualification
- adult qualification
- adapted qualification

Any match that depends on this fallback is flagged for review.

## 8. Review Flags

The app attaches review flags to matches and unassigned swimmers. These flags tell staff what needs attention after generation.

### Severity Levels

| Severity | Meaning |
| --- | --- |
| `info` | Not necessarily wrong, but worth noting |
| `review` | Staff should inspect this before finalizing |
| `urgent` | Needs direct policy or qualification review |

### Flag Table

| Flag code | Title | Severity | What it means | Recommended action |
| --- | --- | --- | --- | --- |
| `low_confidence_under_50` | Low confidence | `review` | Match confidence is below 50, so the assignment quality is weak | Consider reassignment |
| `continuity_dispute` | Continuity dispute | `review` | More than one swimmer claimed the same continuity instructor, and this swimmer lost the tiebreak | Review the continuity tiebreak |
| `match_confidence_below_70` | Confidence below review target | `info` | Match confidence is below 70, so staff should check it | Quick review of the assignment |
| `compatibility_below_50` | Low compatibility | `review` | Compatibility score is below 50, so the instructor may not be a good fit | Consider reassignment |
| `forced_assignment` | Only one legal option | `info` | Only one legal instructor remained after constraints were applied | Confirm there was no better legal option |
| `uneven_pair_fit` | Uneven pair fit | `info` | One swimmer in a pair fits the instructor much better than the other | Review pair balance |
| `note_requested_assignment` | Note-requested assignment | `info` | A prefer or always note influenced this assignment | Verify the note request is still current |
| `continuity_overrides_adapted_capability` | Adapted capability override | `urgent` | Continuity was preserved even though the prior instructor is not marked adapted-capable | Verify the instructor qualification record |
| `manual_policy_review_required` | Manual policy review required | `urgent` | The solver found a continuity versus qualification tradeoff that needs human confirmation | Confirm the policy override |
| `continuity_capacity_conflict` | Continuity capacity conflict | `review` | Several swimmers claimed the same continuity instructor, but only one class slot was available | Review the continuity tiebreak |
| `continuity_blocked_by_adult_capability` | Adult capability blocked continuity | `review` | An adult swimmer had continuity, but that instructor is not adult-capable | Verify the instructor qualification record |
| `continuity_blocked_by_baby_capability` | Baby capability blocked continuity | `review` | A baby swimmer had continuity, but that instructor is not baby-capable | Verify the instructor qualification record |
| `continuity_pairing_conflict` | Pairing continuity conflict | `review` | A pair lost continuity because the prior instructor was assigned to a private continuity swimmer | Review the pairing decision |
| `non_response_swimmer_type` | Default swimmer type used | `review` | The swimmer used the `Non-Response / Unknown` type because survey data was not provided | Update the swimmer type |
| `default_instructor_profile` | Default instructor profile used | `review` | The instructor was missing profile data, so fallback values were used | Update the instructor profile |
| `pre_assigned_instructor` | Pre-assigned instructor | `info` | The class already had an instructor filled in and that assignment was preserved | Quick review of the assignment |
| `registered_class_not_found` | Registered class not found | `review` | The swimmer's registered class name was not found in the selected classes file | Verify class registration |
| `registered_class_full` | Registered class full | `review` | The swimmer's class exists, but the fixed-roster import could not place them into that class row | Verify class registration |
| `pre_assigned_instructor_name_ambiguous` | Pre-assigned instructor name ambiguous | `review` | A pre-assigned instructor name matched multiple instructors and one was chosen automatically | Verify the instructor qualification record |
| `adapted_swimmer_single_legal_instructor` | Single adapted-capable option | `review` | The adapted swimmer had only one legal adapted-capable instructor available | Confirm there was no better legal option |
| `below_min_auto_assign_score` | Below auto-assignment threshold | `review` | The best legal match was below the minimum auto-assign threshold | Review whether a manual override is appropriate |

## 9. Common Workflow Tips

- Use internal CSV files when you want the cleanest editing workflow for reference tables and rankings.
- Use Jackrabbit exports when you want the app to convert current operational data quickly.
- If a run fails because instructors do not match, compare the instructor names in the classes file with the names in the selected instructor file.
- If a run fails because registered classes do not match, refresh both the classes and students exports from the same Jackrabbit snapshot.
- Review all `review` and `urgent` flags before finalizing the schedule.
- Treat `Non-Response / Unknown` swimmers and defaulted instructor profiles as items that still need staff cleanup.

## 10. Output Files

Each completed run creates a job folder under `jobs/` and may include:

- `result.json`
- `classes_filled.csv`
- `matching_report.pdf`
- `profiles.json`

These files are the source for the UI downloads, reports, and clickable profile
views. They can contain personal and support/medical information. App-owned job
folders are retained for 30 days by default; exports saved elsewhere are not
removed by Aqua Essence. Follow
[Privacy and Data Retention](docs/privacy-and-data-retention.md) for storage,
manual cleanup, and public-release rules.

## 11. Troubleshooting

### `Generate matching` is disabled

Make sure all three core files are selected:

- `classes.csv`
- `swimmers.csv`
- `instructors.csv`

### A swimmer was not rostered into the expected class

Check:

- the students export contains `Current Classes`
- the class name in the students file matches the classes file exactly
- the class exists and is active in the selected classes file

### Special-needs routing looks wrong

Check:

- the students export includes `Special Needs`
- staff did not assume `Notes` alone would drive this field
- the selected instructors file has accurate `can_teach_adapted` values

### Many instructors are flagged with `Default instructor profile used`

Check:

- whether the selected instructor file contains profile columns already
- whether the default instructor profile needs to be updated
- whether staff should use **Edit styles and colors** to complete missing instructor data before generating

### The results look technically valid but not operationally ready

Check:

- continuity history
- swimmer type assignments
- RSS skill levels
- instructor profile completeness
- review and urgent flags

## 12. Suggested Best Practice

For the cleanest workflow:

1. Capture fresh students and classes with Jackrabbit Exporter 1.1.0; capture
   staff and pairing history when available.
2. Download `aqua_essence_jackrabbit_export.json` and import it into Aqua Essence.
3. Review the import counts, warnings, and selected sources.
4. Complete missing swimmer fields and every new instructor profile.
5. Confirm swimmer types, colors, styles, qualifications, and rankings are current.
6. Generate the matching.
7. Review flags, unassigned swimmers, and low-confidence matches.
8. Download the filled classes CSV and matching report for operational use.
