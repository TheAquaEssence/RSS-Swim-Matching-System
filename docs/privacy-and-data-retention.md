# Privacy and Data Retention

Aqua Essence processes operational records about children and staff. Those
records can include names, ages, lesson history, instructor assignments, and
free-text notes describing disabilities or support needs. Treat every real
export, generated job, database, and log as confidential operational data.

This document describes the current local application. It is an operational
policy, not a claim that the application provides regulatory compliance on its
own. The organization operating the software remains responsible for consent,
access control, retention periods, backups, breach response, and applicable
privacy-law requirements.

## Local-only processing boundary

The matching application is designed to run on the user's computer. The active
backend binds to `127.0.0.1`, and the repository contains no feature that sends
matching inputs or results to a hosted Aqua Essence service. Staff may still
move data outside this boundary themselves—for example, by syncing the app-data
directory, uploading a report, or selecting an input from a cloud-synced folder.

Use a dedicated, access-controlled app-data directory on an encrypted device.
For source runs, set it explicitly:

```powershell
python start.py --data-dir "C:\path\to\AquaEssenceData"
```

Future desktop packages must map this same boundary to the platform's private
per-user application-data directory.

## What is stored

| Location under the app-data directory | Contents | Current deletion behavior |
| --- | --- | --- |
| `data/aqua_essence.db` | Instructor profiles, imported session history, pairings, and import/undo history | Retained until records are removed in the app or the database file is securely deleted. Deleting one session removes that session and its pairings, not the rest of the database. |
| `settings/user_settings.json` | Preferences and paths to files selected by the user | Retained until the settings file or app-data directory is deleted. Paths can reveal usernames or folder names. |
| `jobs/job_*/` | Per-run request, normalized/imported CSVs, solver results, reports, and `profiles.json` | Application-created jobs older than 30 days are removed at backend startup. These files can repeat the most sensitive swimmer data. |
| `logs/<component>/*.jsonl` | Diagnostic events, request/job identifiers, errors, and limited subprocess output | Log files older than 14 days are removed when logging starts and during long-running sessions. Logs are not guaranteed to be free of personal data, so access must still be restricted. |
| `resources/` | Writable copies of bundled demo/reference resources | Retained until deleted. Bundled demos are synthetic; do not replace them with operational exports. |
| User-selected files outside app data | Original Jackrabbit/CSV/XLSX inputs and any exported reports | Never deleted by the application. Their retention follows the policy of the folder or system where the user saved them. |

The repository's `.gitignore` excludes known operational locations, including
the database, jobs, logs, settings, generated data, local workbooks, and staged
Jackrabbit exports. Ignore rules reduce accidental commits; they are not
encryption, access control, secure deletion, or a substitute for reviewing a
commit before publishing it.

## Deleting operational data

1. Close Aqua Essence and make sure no matching job is running.
2. Preserve only records that the organization's approved retention schedule
   requires. Exporting a report creates another copy that must be managed too.
3. Delete obsolete sessions through the session-management UI when only those
   database records should be removed.
4. The application removes its expired `jobs/job_<32 lowercase hex>`
   directories at startup. Delete newer obsolete jobs manually if they should
   not remain until the next retention cutoff. Removing a job does not remove
   its saved session from the database.
5. Delete obsolete source exports and reports from their original folders.
6. To remove all local application state, delete the dedicated app-data
   directory, including its database, settings, jobs, logs, and resources.
7. Also remove copies from backups, recycle bins, synchronization services, and
   shared folders according to organizational policy.

Ordinary filesystem deletion may not make data unrecoverable from all storage
media. Use the organization's approved device-erasure and media-disposal
procedure when secure destruction is required.

## Retention configuration and safety boundary

The centralized defaults are 30 days for generated jobs and 14 days for logs.
Desktop/process hosts can set `AQUA_JOB_RETENTION_DAYS` and
`AQUA_LOG_RETENTION_DAYS` to non-negative whole numbers. `0` makes eligible
artifacts expire at the next cleanup; an unset, negative, or malformed value
uses the safe default. Shorter periods reduce exposure but can remove reports
needed for operational review, so align overrides with the organization's
approved schedule and backup obligations.

Job cleanup is deliberately narrow. It operates only in the configured
app-data `jobs/` directory, only on direct child directories using the current
cryptographically random `job_<32 lowercase hex>` naming format, and never
follows symlinks or a path outside app data. Unknown/legacy names, loose files,
original imports, exported reports, and any user-selected files elsewhere are
preserved. Log cleanup applies only inside the configured application log
directory. Cleanup is ordinary filesystem deletion, not guaranteed secure
erasure.

## Minimum operating rules

- Import only the fields needed for matching; avoid unnecessary notes.
- Do not use real names or medical/support notes in screenshots, bug reports,
  tests, demos, issues, or pull requests.
- Do not email operational datasets or place them in personal cloud storage.
- Limit app-data and exported-report access to staff who need it.
- Use synthetic data only from `examples/demo/` for development and public
  demonstrations. `data/app_samples/` is retired and ignored.
- Stop and report a suspected exposure through the organization's incident
  process; do not paste affected records into a public GitHub issue.

## Public-release checklist

Before creating a public GitHub release or source archive:

1. Review the complete Git history, not only the current working tree, for
   operational CSV/XLSX files, databases, job artifacts, logs, credentials,
   names, dates of birth, and support/medical notes.
2. Run automated secret and sensitive-file scanning, then investigate every
   finding. A clean scanner result does not replace manual review.
3. Build release artifacts from a clean checkout containing only tracked files.
4. Open representative bundled sample files and confirm they are synthetic.
5. Confirm runtime data, reports, and local configuration are excluded from the
   package and source archive.
6. If sensitive data ever entered Git history, treat it as disclosed: remove it
   with an approved history-rewrite process, rotate any exposed credentials,
   notify affected parties as required, and verify forks/caches where possible.

A user-facing "delete all local data" control is still pending. Until it is
implemented, operators must perform whole-app-data cleanup manually as
described above.
