# Contributing

## Commit attribution

Every commit in the public repository must include exactly these privacy-safe
trailers:

```text
Co-Authored-By: Daniel Nwogo <118936910+nigerianpickle@users.noreply.github.com>
Co-Authored-By: Ibrahim Mamman <97623924+Nabxz@users.noreply.github.com>
```

CI validates the complete public history and rejects missing, duplicated, or
additional `Co-Authored-By` trailers.

Start with [docs/development.md](docs/development.md) for setup, architecture,
verification commands, and engineering rules.

## Changes

- Keep commits focused and preserve unrelated working-tree changes.
- Add tests for behavior changes and update the relevant current document.
- Use synthetic fixtures and invented identifiers only.
- Do not weaken matching hard constraints, local-host security, process
  isolation, or persistence guarantees without an explicit reviewed decision.
- Coordinate CSV contract changes with external integrations.

Before publishing a change, run Ruff, the complete Python suite, and any
affected desktop or packaging checks listed in the developer guide.

## Pull requests

Explain the problem, the chosen boundary, user impact, and verification. Keep
file moves separate from behavior changes when practical. Do not attach real
swimmer, instructor, enrollment, medical, job, report, or log data.

## Security

Do not open a public issue for a suspected vulnerability or include
operational data in a report. Follow [SECURITY.md](SECURITY.md).
