# Persistence and Crash Safety

Aqua Essence keeps mutable runtime state under the configured application-data
root. Its settings and database use different persistence mechanisms, but both
avoid exposing a partially written logical update after a process crash.

## Settings

`settings/user_settings.json` is serialized completely to a sibling `.tmp`
file and then installed with `os.replace()`. If serialization or the temporary
write fails, the prior settings file is untouched. If replacement fails or the
process exits before replacement, startup continues to read the last complete
settings file and ignores the temporary file. A later save safely replaces the
stale temporary file.

Invalid or missing settings are treated as recoverable configuration loss: the
backend starts with defaults instead of attempting to merge a partial JSON
document. This can require the user to select input files again, but does not
alter those input files.

## SQLite database

Schema migrations execute inside explicit SQLite transactions and advance
`PRAGMA user_version` only in the same transaction as their schema changes.
Ordinary multi-row writes also use SQLite transactions. If the backend exits
before commit, SQLite rolls the incomplete transaction back when the database
is reopened; callers never intentionally persist half of a session import or
schema step.

The application must not copy, replace, or restore the database while the
backend is running. Upgrade and backup rules are documented in
[Database Schema Migrations](database-schema-migrations.md).

## Scope

These guarantees cover application/process crashes and ordinary write errors.
They do not replace protected backups or guarantee recovery from storage-device
failure, filesystem corruption, malware, or abrupt power loss before the
operating system has durably flushed its caches.
