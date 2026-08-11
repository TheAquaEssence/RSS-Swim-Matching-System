"""Tests for the public commit-attribution policy."""

from types import SimpleNamespace

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


def test_commit_messages_ignores_merge_commits(monkeypatch, tmp_path):
    commit_sha = "a" * 40
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=f"{commit_sha}\0{APPROVED_MESSAGE}\0")

    monkeypatch.setattr(check_commit_attribution.subprocess, "run", fake_run)

    assert check_commit_attribution.commit_messages(tmp_path) == [
        (commit_sha, APPROVED_MESSAGE.strip())
    ]
    assert "--no-merges" in calls[0][0]
