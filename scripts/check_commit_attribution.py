"""Enforce privacy-safe identities and co-author trailers on public commits."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
import subprocess
import sys
from pathlib import Path


REQUIRED_TRAILERS = {
    "Daniel Nwogo <118936910+nigerianpickle@users.noreply.github.com>",
    "Ibrahim Mamman <97623924+Nabxz@users.noreply.github.com>",
}
TRAILER = re.compile(r"^Co-Authored-By:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
GITHUB_NOREPLY = re.compile(
    r"^(?:[^@\s]+@users\.noreply\.github\.com|noreply@github\.com)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommitRecord:
    commit: str
    parents: tuple[str, ...]
    author_email: str
    committer_email: str
    message: str

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1


def validate_message(message: str) -> list[str]:
    trailers = TRAILER.findall(message)
    errors: list[str] = []
    if set(trailers) != REQUIRED_TRAILERS or len(trailers) != len(REQUIRED_TRAILERS):
        errors.append(
            "commit must contain exactly the two approved Co-Authored-By trailers"
        )
    return errors


def validate_email(role: str, email: str) -> list[str]:
    if GITHUB_NOREPLY.fullmatch(email):
        return []
    return [f"{role} email must use a GitHub no-reply address"]


def validate_commit(record: CommitRecord) -> list[str]:
    errors = [
        *validate_email("author", record.author_email),
        *validate_email("committer", record.committer_email),
    ]
    if not record.is_merge:
        errors.extend(validate_message(record.message))
    return errors


def commit_records(repository: Path) -> list[CommitRecord]:
    output = subprocess.run(
        ["git", "log", "--format=%H%x00%P%x00%ae%x00%ce%x00%B%x00"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    fields = output.split("\0")
    trailing = fields.pop()
    if trailing.strip() or len(fields) % 5:
        raise ValueError("unexpected git log output")
    records = []
    for index in range(0, len(fields), 5):
        commit, parents, author_email, committer_email, message = fields[
            index : index + 5
        ]
        records.append(
            CommitRecord(
                commit=commit.strip(),
                parents=tuple(parents.strip().split()),
                author_email=author_email.strip(),
                committer_email=committer_email.strip(),
                message=message.strip(),
            )
        )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args(argv)

    failed = False
    for record in commit_records(args.repository.resolve()):
        for error in validate_commit(record):
            print(f"{record.commit[:12]}: {error}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    print("public commit attribution is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
