"""Require the approved privacy-safe co-author trailers on public commits."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REQUIRED_TRAILERS = {
    "Daniel Nwogo <118936910+nigerianpickle@users.noreply.github.com>",
    "Ibrahim Mamman <97623924+Nabxz@users.noreply.github.com>",
}
TRAILER = re.compile(r"^Co-Authored-By:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def validate_message(message: str) -> list[str]:
    trailers = TRAILER.findall(message)
    errors: list[str] = []
    if set(trailers) != REQUIRED_TRAILERS or len(trailers) != len(REQUIRED_TRAILERS):
        errors.append(
            "commit must contain exactly the two approved Co-Authored-By trailers"
        )
    return errors


def commit_messages(repository: Path) -> list[tuple[str, str]]:
    output = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x00"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    fields = [field.strip() for field in output.split("\0") if field.strip()]
    if len(fields) % 2:
        raise ValueError("unexpected git log output")
    return list(zip(fields[0::2], fields[1::2], strict=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args(argv)

    failed = False
    for commit, message in commit_messages(args.repository.resolve()):
        for error in validate_message(message):
            print(f"{commit[:12]}: {error}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    print("public commit attribution is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
