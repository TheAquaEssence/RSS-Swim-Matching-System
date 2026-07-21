# Reference Data Provenance

This documents where the tracked reference tables came from, replacing the
untracked workbooks and legacy CSVs that previously carried this history.

## Canonical reference tables (tracked, `data/source/`)

| File | Content | Origin |
|------|---------|--------|
| `personality_colors.csv` | 4 personality colors + traits | Program's color personality framework (Blue/Orange/Green/Gold) |
| `instructor_styles.csv` | 6 teaching styles + expertise areas | Program's instructor style categories (NR/HE/TD/A/SS/DIA) |
| `swimmer_types.csv` | Swimmer type definitions (incl. non-response type 8) | Program's swimmer intake categories |
| `swimmer_type_color_rankings.csv` | Per-swimmer-type ranking of instructor colors | Transcribed from the coordinator's `Rankings.xlsx` workbook |
| `swimmer_type_style_rankings.csv` | Per-swimmer-type ranking of instructor styles | Transcribed from the coordinator's `Rankings.xlsx` workbook |

The ranking-based scorer (`core/scoring/`) consumes the two ranking tables
directly; the CSVs in `data/source/` are the single machine-readable source of
truth.

## Untracked local reference material (`reference/`, gitignored)

- `Rankings.xlsx` — the coordinator's original ranking workbook. Human
  reference only; its content is fully transcribed into the two ranking CSVs
  above. Kept locally for provenance, not needed by any code.
- `combined.xlsx` — coordinator worksheet combining the matching legend with a
  Jackrabbit class-export sheet. The class sheet may contain real instructor
  names, so this file is treated as operational data and must never be
  committed.

## Removed legacy material (`data/legacy/`, gitignored)

- `csv/` — the pre-2026-03 *compatibility-matrix* reference format
  (`swimmer_type_color_compatibility.csv`, `swimmer_type_style_compatibility.csv`,
  `swimmer_color_matches.csv`, `swimmer_style_matches.csv`) superseded by the
  ranking-based format in `data/source/`. Early copies of
  `personality_colors.csv`, `instructor_styles.csv`, and `swimmer_types.csv`
  matched the current tracked versions apart from minor header/punctuation
  renames (`area_of_expertise` → `expertise_area`); the current
  `swimmer_types.csv` additionally defines type 8 (Non-Response / Unknown).
- `code/generate_reference_data_v1.py` — v1 generator for the compatibility
  format, superseded by `data_generation/generate_reference_data.py`.
- `csv/Monday Spring Export (test).xlsx` — a sample Jackrabbit export used
  during import development; treated as potentially real partner data.
