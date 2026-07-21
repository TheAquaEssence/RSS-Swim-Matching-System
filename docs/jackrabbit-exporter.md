# Jackrabbit Exporter Integration

The Jackrabbit Exporter browser extension is maintained as a separately
versioned project:

- Repository: <https://github.com/TheAquaEssence/jackrabbit-exporter>
- Initial visibility: private pending privacy and public-release review

The extension source is intentionally not vendored into Aqua Essence. The two
projects integrate through downloaded CSV files rather than runtime code.

## Compatibility boundary

Aqua Essence owns detection, validation, conversion, and import of Jackrabbit
CSV data. The exporter owns browser permissions, Jackrabbit page extraction,
buffering, and CSV generation.

Changes to the following exported headers must be coordinated and tested in
both repositories:

- `jackrabbit_students.csv`
- `jackrabbit_classes.csv`
- `jackrabbit_pairings.csv`

Do not copy real student, instructor, enrollment, medical, or session data
between repositories for testing. Use synthetic fixtures and invented
identifiers.

## Public-release gate

Before changing the exporter repository to public visibility:

1. Review every revision for operational data, credentials, and internal-only
   Jackrabbit implementation details.
2. Rewrite or squash history if personal author email addresses should not be
   published.
3. Configure a private security-reporting channel.
4. Review browser permissions and the privacy statement.
5. Confirm CI passes from a clean clone.
