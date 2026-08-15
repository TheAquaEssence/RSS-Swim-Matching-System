# Jackrabbit Exporter Integration

The Jackrabbit Exporter browser extension is maintained as a separately
versioned project:

- Repository: <https://github.com/TheAquaEssence/jackrabbit-exporter>
- Initial visibility: private pending privacy and public-release review

The extension source is intentionally not vendored into Aqua Essence. The two
projects integrate through a versioned downloaded bundle rather than runtime
code.

## Compatibility boundary

Aqua Essence owns bundle validation, CSV conversion, source selection, and
database import. The exporter owns browser permissions, Jackrabbit page
extraction, buffering, and bundle generation.

The supported release compatibility is Aqua Essence 0.2.0, Jackrabbit
Exporter 1.1.0, and bundle contract version 1 (`format_version: 1`).

The only supported bundle handoff is
`aqua_essence_jackrabbit_export.json`, produced by Jackrabbit Exporter 1.1.0,
with:

- `format`: `aqua-essence-jackrabbit-export`
- `format_version`: `1`
- `exporter`: `{"name": "Jackrabbit Exporter", "version": "1.1.0"}`
- `exported_at`: a timezone-aware ISO-8601 timestamp
- a `files` object containing the CSV payloads below

Changes to the following exported headers must be coordinated and tested in
both repositories:

- `jackrabbit_students.csv`
- `jackrabbit_classes.csv`
- `jackrabbit_staff.csv`
- `jackrabbit_pairings.csv`

The `files` object must contain exactly those four names. Students and classes
must contain data rows. Staff and pairings may be header-only; class
`instructor_id` values supplement missing staff identities without inventing
status, position, qualifications, or matcher-owned profile attributes. The
desktop import rejects unknown formats, versions, metadata, file keys, and
version-1 headers before it changes selected sources.

### Locked format-version-1 headers

Header spelling, capitalization, and order are part of the contract. Each
embedded CSV must use exactly one of these header rows:

```text
jackrabbit_students.csv
Student ID,Student First Name,Student Last Name,Family,Status,DOB,Age,Current Classes,Skill Level,Notes,Special Needs

jackrabbit_classes.csv
Class ID,Class,instructor_id,Instructors,Days,Start Time,End Time,Location,Status,Session,Start Date,End Date,Cat 1,Open,Size

jackrabbit_staff.csv
Staff ID,Name,Status,Position,Instructor

jackrabbit_pairings.csv
swimmer_id,class_id,instructor_id,class_name,session,status
```

The CSV payloads follow RFC-style CSV quoting: commas, doubled quotes, and
embedded CR/LF are preserved when a field is quoted. Students and classes must
produce at least one usable converted record; a non-empty payload made only of
invalid required rows is rejected with a reviewable error.

The desktop app converts each embedded CSV independently, selects the classes
and swimmers for the next run, adds only instructor identities missing from
the database, preserves existing curated instructor profiles, and imports
historical pairings by Jackrabbit session. Skipped optional pairing rows are
reported as warnings. New identity-only instructor records remain incomplete
and cannot be used for matching until an operator explicitly completes their
colors, styles, and teaching qualifications in Data & settings. Unknown
qualifications are treated fail-closed, never as an affirmative certification.
Student, class, staff, swimmer,
class-assignment, and instructor xIDs remain strings so leading zeroes survive
conversion, matching, persistence, and output generation. Multi-instructor
assignments are keyed by `(Class ID, instructor_id)` and retain the original
Class ID on every row.

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
