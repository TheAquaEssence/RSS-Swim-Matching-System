---
name: run-all-tests
description: "Run the complete current Aqua Essence Python test suite with repository-wide pytest discovery, then summarize passes, failures, and environment-gated skips. Usage: /run-all-tests"
---

Run the complete Python test suite from the repository root and produce a concise pass/fail summary.

1. Confirm the current directory is the repository root containing `AGENTS.md`, `backend/`, `core/`, `frontend/`, and `solvers/`.
2. Run `python -m pytest -q` without enumerating test directories. Repository-wide discovery must include all active suites, including `frontend/tests/` and `core/profiles/tests/`.
3. Do not skip a missing suite silently or fall back to obsolete `swim_matching/...` paths.

After pytest completes, report:

- Overall passed, failed, errored, and skipped counts.
- Each skipped test and its stated reason, distinguishing expected environment gates from unexpected skips.
- Each failing or errored test name with the first useful traceback or assertion details.
- The pytest exit code.

If collection fails, report the collection error and stop; do not present a partial run as the full suite.
