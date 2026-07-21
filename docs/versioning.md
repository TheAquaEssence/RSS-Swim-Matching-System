# Versioning and Changelog Policy

Aqua Essence uses semantic versioning for public desktop releases:

- major: incompatible user-data, API, or operational workflow changes;
- minor: backward-compatible features;
- patch: backward-compatible fixes and documentation changes.

The canonical application version is `desktop/package.json`. Release tooling
must propagate and verify that version in packaged metadata, installer names,
Git tags, and health/release responses. Release tags use `vMAJOR.MINOR.PATCH`.

Every user-visible change belongs under `Unreleased` in the root
`CHANGELOG.md`. At release time, move those entries into a dated version
section, update the application version, generate release notes from that
section, and publish checksums for installer artifacts.

Pushing a matching `vMAJOR.MINOR.PATCH` tag runs the Windows packaging workflow
and publishes a GitHub Release only after `scripts/prepare_release.py` verifies
the tag, `desktop/package.json`, backend health version, installer filename,
and changelog section agree. The release contains the NSIS installer and a
generated `SHA256SUMS`; ordinary branch and pull-request runs never publish a
GitHub Release.

Pre-1.0 releases may change internal APIs, but database migrations and user
data must still follow the compatibility and backup rules documented in
`database-schema-migrations.md`.
