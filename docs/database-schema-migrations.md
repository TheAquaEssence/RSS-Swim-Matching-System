# Database Schema Migrations

Aqua Essence stores its local operational database at
`<app-data>/data/aqua_essence.db`. The application owns the schema and upgrades
it automatically during backend startup.

## Version contract

- SQLite `PRAGMA user_version` is the authoritative schema version.
- Version `0` means either a new file or an unversioned database made by an
  older Aqua Essence release.
- `backend/db.py` contains an ordered migration list. Released migrations are
  immutable: schema changes append a new migration rather than editing an old
  one.
- Each migration and its version update run in one transaction. If a migration
  fails, that migration is rolled back and startup fails; a later launch can
  retry safely from the last completed version.
- Initialization at the current version is a no-op and is safe on every launch.
- A database whose version is newer than the running application supports is
  rejected before schema changes. Open it with the same or a newer Aqua Essence
  release instead of attempting a downgrade.

The first versioned release recognizes existing unversioned databases, creates
any missing baseline tables and indexes, and adds the optional operator
attribution columns without deleting existing instructors, sessions, or
pairings.

## Upgrade and failure behavior

The desktop host should treat database initialization failure as a startup
failure and show the backend error without repeatedly restarting it. Migration
errors must not be ignored: continuing with a partially upgraded schema could
turn a recoverable migration problem into data loss.

Successful earlier migration steps can remain committed if a later step fails.
This is intentional; every committed version is a valid schema, and the next
startup resumes at the first incomplete step. The failing step itself is fully
rolled back.

## Backups and recovery

The app does not silently create database copies during migration. The database
can contain children's and staff data, so automatic copies would expand the
number of sensitive files and make retention less predictable.

Before installing an upgrade that changes the schema, close Aqua Essence and
copy the complete `aqua_essence.db` file to protected storage. Do not copy it
while the backend is running. If an upgrade fails:

1. Preserve the failed database and backend log for diagnosis.
2. Reopen it with the last compatible app release, or restore the pre-upgrade
   copy while the app is stopped.
3. Do not lower `PRAGMA user_version` manually; the schema and recorded version
   would no longer agree.

Backups contain the same personal data as the live database. Encrypt them,
limit access, and delete them according to
[Privacy and Data Retention](privacy-and-data-retention.md).

## Adding a migration

1. Append one migration callable to `_MIGRATIONS` in `backend/db.py`.
2. Make it accept both the exact prior version and realistic legacy state where
   appropriate. Use catalog/`PRAGMA table_info` checks for additive changes.
3. Keep all statements inside the transaction supplied by `init_db()`; do not
   call `commit()` or use `executescript()` in the migration.
4. Add tests for a fresh database, upgrade from the previous version, retry or
   repeat initialization, preservation of existing records, and rejection of a
   future version.

