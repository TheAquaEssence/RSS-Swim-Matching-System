# Changelog

All notable user-visible changes are recorded here. Versioning follows
[docs/versioning.md](docs/versioning.md).

## Unreleased

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
