# Changelog

All notable user-visible changes are recorded here. Versioning follows
[docs/versioning.md](docs/versioning.md).

## Unreleased

## 0.2.0 — 2026-08-14

### Added

- Added strict import support for Jackrabbit Exporter 1.1.0 format-version-1
  JSON bundles, including header-only optional data, staff identity
  supplementation, multi-instructor class assignments, and leading-zero xID
  preservation. Identity-only staff remain fail-closed and must be completed
  before matching.

### Changed

- Redesigned the desktop interface around dedicated Matching, Results, Data &
  settings, and Explainability workspaces while preserving the existing light
  and dark color themes.
- Unified review drawers, editors, historical-session controls, result filters,
  and loading, empty, error, focus, and disabled states.

### Accessibility

- Added keyboard-operable secondary workflows, focus restoration for dialogs
  and drawers, view-heading focus management, descriptive window titles, live
  status announcements, reduced-motion behavior, and duplicate-run prevention.

## 0.1.0 — 2026-07-21

### Added

- Local-first FastAPI, CP-SAT, XAI, and Electron application architecture.
- Frozen Windows backend and NSIS packaging workflow with packaged smoke tests.
- Synthetic demonstration data, explicit application-data storage, retention,
  transactional database migrations, and persistent structured logging.
- Complete locked Python runtime inventory, bundled license archive, and
  CycloneDX SBOM verification.
- Tag-gated GitHub Release automation with generated release notes and
  SHA-256 installer checksums.

### Changed

- Separated the Jackrabbit Exporter into its own private repository pending a
  privacy and public-release review.
- Consolidated repository architecture, development, contribution, security,
  script ownership, and documentation guidance.
- Refreshed the Matching and Explainability interfaces while preserving the
  offline-only runtime contract.

### Fixed

- Restored native Classes and Swimmers file dialogs in sandboxed packaged
  Electron builds.
- Replaced solver-owned filesystem paths with authenticated result-download
  URLs for PDF and CSV exports.

This entry establishes the changelog baseline; earlier implementation detail
remains available in dated historical documents and Git history.
