"""Shared flag vocabulary for all solvers.

Loads the canonical flag/review-action definitions from core/flag_vocabulary.json.
All Python solvers import from here; C++ solvers load the same JSON directly
via nlohmann/json.

Usage:
    from core.flags import FLAG_CODES, REVIEW_ACTIONS, SEVERITY_LEVELS
    from core.flags import get_highest_severity, get_primary_review_action, validate_flag_codes
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

_VOCAB_PATH = Path(__file__).parent / "flag_vocabulary.json"

with _VOCAB_PATH.open(encoding="utf-8") as _f:
    _vocab = json.load(_f)

FLAG_CODES: dict = _vocab["flag_codes"]
REVIEW_ACTIONS: dict = _vocab["review_actions"]
SEVERITY_LEVELS: list = _vocab["severity_levels"]  # ordered lowest → highest

_SEVERITY_RANK = {level: i for i, level in enumerate(SEVERITY_LEVELS)}


def get_highest_severity(flag_codes: List[str]) -> str:
    """Return the highest severity level across the given flag codes.

    Returns 'none' for an empty list.
    """
    if not flag_codes:
        return "none"
    best = "none"
    for code in flag_codes:
        entry = FLAG_CODES.get(code, {})
        sev = entry.get("severity", "none")
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(best, 0):
            best = sev
    return best


def get_primary_review_action(flag_codes: List[str]) -> str:
    """Return the review action for the highest-severity flag.

    Returns empty string for an empty list.
    """
    if not flag_codes:
        return ""
    best_code = None
    best_rank = -1
    for code in flag_codes:
        entry = FLAG_CODES.get(code, {})
        sev = entry.get("severity", "none")
        rank = _SEVERITY_RANK.get(sev, 0)
        if rank > best_rank:
            best_rank = rank
            best_code = code
    if best_code is None:
        return ""
    return FLAG_CODES[best_code]["default_review_action"]


def expand_flag_codes(flag_codes: List[str]) -> List[dict]:
    """Return UI/API-ready metadata for each known flag code."""
    expanded = []
    for code in flag_codes:
        entry = FLAG_CODES.get(code)
        if not entry:
            expanded.append({
                "code": code,
                "title": code,
                "description": "",
                "severity": "none",
                "review_action": "",
                "review_action_label": "",
            })
            continue

        action = entry.get("default_review_action", "")
        expanded.append({
            "code": code,
            "title": entry.get("title", code),
            "description": entry.get("description", ""),
            "severity": entry.get("severity", "none"),
            "review_action": action,
            "review_action_label": REVIEW_ACTIONS.get(action, action),
        })
    return expanded


def validate_flag_codes(flag_codes: List[str]) -> None:
    """Raise ValueError if any code in flag_codes is not in the approved vocabulary."""
    unknown = [c for c in flag_codes if c not in FLAG_CODES]
    if unknown:
        raise ValueError(f"unknown flag code(s): {unknown}")
