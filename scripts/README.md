# Scripts

This directory contains command-line maintenance and release tools. None are
application startup entry points.

| Tool | Classification | Support boundary |
|---|---|---|
| `generate_third_party_notices.py` | Supported release tooling | Used by tests and packaging. Its `--check` mode must pass whenever runtime dependencies or bundled assets change. |
| `import_pairings.py` | Administrative migration utility | Manually imports an approved Jackrabbit pairings CSV into a selected local SQLite database. Back up the database first and never commit the input or database. Normal users should use the application import flow. |
| `enrich_instructors.py` | One-time/administrative data preparation | Converts approved staff and matching workbooks into the internal instructor schema. It is not part of application runtime or CI. Review output before import and use only private local paths. |
| `nicknames.json` | Data for `enrich_instructors.py` | Keep beside the enrichment script; it is not shipped as an application resource. |

Run every script from the repository root with `python scripts/<name>.py
--help`. Administrative scripts may process personal information: use only
authorized local inputs, do not place output in tracked paths, and follow
`docs/privacy-and-data-retention.md`.
