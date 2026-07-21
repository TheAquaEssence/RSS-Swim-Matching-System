# Aqua Essence User Manual

This manual explains how to prepare input files, run the application, review the results, and maintain the reference data used by the matching system.

## 1. What The App Does

Aqua Essence matches swimmers to instructors for RSS classes. The app uses:

- `classes.csv` to define the class rows and assigned instructors for a time slot
- `swimmers.csv` to define which swimmers need to be placed
- `instructors.csv` to define which instructors are available and what profiles they have

The app can also read Jackrabbit partner exports directly from `.csv`, `.xlsx`, and `.xlsm` files. If you pick a partner export, Aqua Essence converts it to the internal format automatically when you generate a solution.

If you use Excel workbooks, the app reads the first worksheet in the file. If your export is not on the first sheet, save it as CSV first or move the export to the first sheet.

## 2. Starting The App

For normal use, start the application by double-clicking `AquaEssence.exe`.

The app starts by itself and opens the browser UI automatically.

You do not need to run Python commands, open `index.html`, or start the server manually.

You also do not need to run any `.bat` file to start the main app. In the current repo, batch files are used for internal helper processes such as solver or dashboard launch support, not as the primary user-facing app launcher.

## 3. Core Files You Need

For a real matching run, start with these three files:

| File | Required | Purpose | Typical Source |
| --- | --- | --- | --- |
| `classes.csv` | Yes | Defines the classes that need swimmers and which instructor is tied to each row | Jackrabbit classes export |
| `swimmers.csv` | Yes | Defines the swimmers to place into classes | Jackrabbit students export |
| `instructors.csv` | Yes | Defines the active teaching staff available for matching | Jackrabbit ActiveStaff export |

You can also supply these optional files in **Advanced inputs (optional)**:

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

Launch Aqua Essence and wait for the browser UI to load.

### Step 2: Select the three core files

In the main screen:

1. Select `classes.csv`
2. Select `swimmers.csv`
3. Select `instructors.csv`

The **Generate solution** button becomes available only when all three are selected.

### Step 3: Add optional files if you have them

Open **Advanced inputs (optional)** and select any additional reference files or historical pairings you want to use.

Notes:

- If you do not select `historical_pairings.csv`, the app can proceed with an empty history file.
- The app remembers your last selected files and restores them on the next launch.

### Step 4: Click `Generate solution`

When you click **Generate solution**, Aqua Essence:

1. Validates the selected files.
2. Detects whether each selected file is already in the internal format or is a Jackrabbit partner export.
3. Converts partner exports automatically when needed.
4. Normalizes swimmer and instructor data before solving.
5. Runs the selected solver.
6. Loads the results into the browser UI.

### Step 5: Review the outputs

After a successful run, the UI shows:

- A results summary with assigned swimmers, unassigned swimmers, classes, empty classes, and average confidence
- A match table with instructor, swimmer, confidence, flags, and reason
- An unassigned swimmers table when applicable
- A button to download the filled classes CSV
- A button to open the latest matching report PDF, when produced
- A button to open the XAI dashboard

You can also click swimmer and instructor names in the results to open profile details.

## 5. Jackrabbit Export Requirements

This section is important when you export data from Jackrabbit.

The app uses the header names exactly as they appear in the partner exports. Your sample files show the names Jackrabbit is currently using. When exporting, make sure those columns are included.

### 5.1 Classes Export

Sample file used: `single_classes.xlsx`

Important Jackrabbit headers:

- `Current Classes` or `Class`
- `Description`
- `Session`
- `Location`
- `Days`
- `Start Time`
- `End Time`
- `Instructors`
- `Open`
- `Size`
- `Status`
- `Cat 1`
- `Start Date`
- `End Date`

Recommended rule:

- Export all of the columns above, especially `Current Classes`, `Instructors`, schedule fields, capacity fields, and `Status`.

How Aqua Essence uses them:

- `Current Classes` or `Class` becomes the class name
- `Instructors` is used to build one internal row per instructor
- `Status` must be `Active` for the row to be imported
- `Open` and `Size` are preserved for class capacity context

### 5.2 Students Export

Sample file used: `single_students.xlsx`

Important Jackrabbit headers:

- `Student First Name`
- `Student Last Name`
- `Family`
- `Status`
- `DOB`
- `Age`
- `Current Classes`
- `Notes`
- `Disabilities`
- `Special Needs`

Minimum fields the importer requires:

- `Student First Name`
- `Student Last Name`
- `Family`
- `Status`
- `Age`

Fields you should always include in practice:

- `Current Classes`
- `Special Needs`
- `Notes`
- `DOB`
- `Disabilities`

Why these are important:

- `Current Classes` is used to connect each swimmer to the class they are registered in. If this column is missing or inconsistent with the selected classes file, the swimmer may not be rostered correctly.
- `Special Needs` should be exported explicitly. Do not rely on `Notes` alone for this flag.
- `Notes` can carry useful free-text information, such as preference notes, but a numeric note count is not treated as a special-needs signal.

Important limitations of the current Jackrabbit import:

- Jackrabbit does not provide `skill_level` for the solver in the current import path, so imported swimmers default to `skill_level = 0`.
- Imported swimmers also default to the swimmer type `Non-Response / Unknown` until survey or intake data is supplied.

Operational recommendation:

- After importing Jackrabbit students data, verify that RSS levels and swimmer types are correct before relying on the output for final scheduling decisions.

### 5.3 ActiveStaff Export

Sample file used: `ActiveStaff.xlsx`

Important Jackrabbit headers:

- `Name`
- `Status`
- `Position`
- `Classes`
- `Instructor`

Profile columns that may also appear in an enriched staff file:

- `primary_color_id`
- `secondary_color_id`
- `primary_style_id`
- `secondary_style_id`
- `is_team_captain`
- `can_teach_NL`
- `can_teach_babies`
- `can_teach_adults`
- `can_teach_adapted`
- `used_default_profile`

Minimum fields the importer requires:

- `Name`
- `Status`

How Aqua Essence filters staff rows:

- Only active rows are imported.
- If `Position` is present, only teaching roles are imported.
- Accepted teaching roles are:
  - `Instructor`
  - `Instructor Team Captain`
  - `Youth Leader`
  - `Aquafit Instructor`
  - `Coach`
- If `Position` is not present, the importer falls back to the `Instructor` truthy flag.

Important note:

- If color, style, or certification fields are missing, the app fills them from the configured default instructor profile and flags those instructors for review.

## 6. Recommended Jackrabbit Export Checklist

Before running a real session, verify:

- The classes export includes `Current Classes` or `Class`, `Instructors`, `Status`, `Days`, `Start Time`, `End Time`, `Open`, `Size`, `Session`, `Start Date`, and `End Date`.
- The students export includes `Current Classes` and `Special Needs`.
- The students export includes `Notes`, but staff understand that `Notes` is not a replacement for `Special Needs`.
- The staff export includes active teaching staff only, or at minimum has reliable `Status` and `Position` values.
- Class names in the students export match the class names in the classes export exactly.
- Instructor names in the classes export match the names in the instructor file closely enough to resolve correctly.

## 7. Editing Swimmer Types, Colors, Styles, And Rankings

Open **Advanced inputs (optional)** to manage the reference data that drives compatibility scoring.

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

In **Advanced inputs (optional)**, click **Edit** beside **Default instructor profile**.

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

These files are the source for the UI downloads, reports, and clickable profile views.
They can contain personal and support/medical information and are not deleted
automatically. Follow
[Privacy and Data Retention](docs/privacy-and-data-retention.md) for storage,
manual cleanup, and public-release rules.

## 11. Troubleshooting

### `Generate solution` is disabled

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

1. Export fresh classes, students, and staff files from Jackrabbit.
2. Verify that the required Jackrabbit columns are included, especially `Current Classes` and `Special Needs` in the students export.
3. Load the files into Aqua Essence.
4. Update instructor styles and colors if needed.
5. Confirm swimmer types, colors, styles, and rankings are current.
6. Generate the solution.
7. Review flags, unassigned swimmers, and low-confidence matches.
8. Download the filled classes CSV and matching report for operational use.
