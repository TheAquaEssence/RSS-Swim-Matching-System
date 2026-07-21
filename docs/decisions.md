# Architecture and Release Decisions

This file records current decisions transferred from dated audits and plans.
Change a decision here only with an explicit reviewed rationale.

## Product and licensing

- Version 1 supports Windows desktop packaging.
- The project is licensed under MIT and is intended for a sanitized public
  repository.
- The current private development repository remains the historical archive;
  the public repository starts from a reviewed clean tree without inherited
  operational-data history.

## Runtime architecture

- Electron packages and manages the existing renderer and Python backend.
- FastAPI is the sole backend.
- Python OR-Tools CP-SAT is the sole production solver strategy for version 1.
- The solver remains an isolated subprocess for timeout and crash containment.
- Automatic application updates are deferred until after the first release.

## Data and upgrades

- Operational data is private and never ships in repositories or installers.
- Installed-mode writes stay under the platform application-data directory.
- Existing user databases survive compatible upgrades through ordered,
  transactional SQLite migrations. A newer unsupported schema is rejected
  without modification.
- Application-owned job directories expire after 30 days and logs after 14
  days by default. User-selected source files and exports outside application
  data are never automatically deleted.

## Integrations

- The Jackrabbit Exporter is a separately versioned repository and integrates
  with Aqua Essence through reviewed CSV contracts only.

## Release posture

- Installer artifacts are unsigned until code-signing capability is available.
  Release documentation must warn that unsigned builds can trigger Windows
  SmartScreen.
- Public releases require clean-machine install/uninstall validation, privacy
  review, matching tag/application versions, and published SHA-256 checksums.
- Automatic updates and code signing are not blockers for internal validation,
  but their status must be explicit in public release notes.
