"""Tests for the public commit-attribution policy."""

from types import SimpleNamespace

import pytest

from scripts import check_commit_attribution


APPROVED_MESSAGE = """Public change

Co-Authored-By: Daniel Nwogo <118936910+nigerianpickle@users.noreply.github.com>
Co-Authored-By: Ibrahim Mamman <97623924+Nabxz@users.noreply.github.com>
"""


def test_validate_message_accepts_exact_approved_trailers():
    assert check_commit_attribution.validate_message(APPROVED_MESSAGE) == []


def test_validate_message_rejects_missing_trailers():
    assert check_commit_attribution.validate_message("Public change") == [
        "commit must contain exactly the two approved Co-Authored-By trailers"
    ]


@pytest.mark.parametrize(
    "email",
    [
        "12345+person@users.noreply.github.com",
        "person@users.noreply.github.com",
        "noreply@github.com",
    ],
)
def test_validate_email_accepts_github_noreply_addresses(email):
    assert check_commit_attribution.validate_email("author", email) == []


def test_validate_email_rejects_personal_address():
    assert check_commit_attribution.validate_email("committer", "person@example.com") == [
        "committer email must use a GitHub no-reply address"
    ]


def test_validate_commit_checks_merge_identity_but_not_trailers():
    record = check_commit_attribution.CommitRecord(
        commit="a" * 40,
        parents=("b" * 40, "c" * 40),
        author_email="12345+person@users.noreply.github.com",
        committer_email="noreply@github.com",
        message="Merge pull request",
    )

    assert check_commit_attribution.validate_commit(record) == []


def test_validate_commit_rejects_personal_merge_author():
    record = check_commit_attribution.CommitRecord(
        commit="a" * 40,
        parents=("b" * 40, "c" * 40),
        author_email="person@example.com",
        committer_email="noreply@github.com",
        message="Merge pull request",
    )

    assert check_commit_attribution.validate_commit(record) == [
        "author email must use a GitHub no-reply address"
    ]


def test_commit_records_reads_merge_and_non_merge_commits(monkeypatch, tmp_path):
    merge_sha = "a" * 40
    commit_sha = "d" * 40
    parent_one = "b" * 40
    parent_two = "c" * 40

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            stdout=(
                f"{merge_sha}\0{parent_one} {parent_two}\0"
                "12345+person@users.noreply.github.com\0noreply@github.com\0"
                "Merge pull request\0\n"
                f"{commit_sha}\0{merge_sha}\0"
                "12345+person@users.noreply.github.com\0"
                "12345+person@users.noreply.github.com\0"
                f"{APPROVED_MESSAGE}\0\n"
            )
        )

    monkeypatch.setattr(check_commit_attribution.subprocess, "run", fake_run)

    assert check_commit_attribution.commit_records(tmp_path) == [
        check_commit_attribution.CommitRecord(
            commit=merge_sha,
            parents=(parent_one, parent_two),
            author_email="12345+person@users.noreply.github.com",
            committer_email="noreply@github.com",
            message="Merge pull request",
        ),
        check_commit_attribution.CommitRecord(
            commit=commit_sha,
            parents=(merge_sha,),
            author_email="12345+person@users.noreply.github.com",
            committer_email="12345+person@users.noreply.github.com",
            message=APPROVED_MESSAGE.strip(),
        ),
    ]
