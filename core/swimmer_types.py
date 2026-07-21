"""Shared swimmer-type constants and normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional


NON_RESPONSE_SWIMMER_TYPE_ID = 8
NON_RESPONSE_SWIMMER_TYPE_NAME = "Non-Response / Unknown"

# Canonical consensus rankings from the April 2026 audit/meeting notes.
NON_RESPONSE_COLOR_ORDER = [1, 4, 3, 2]  # Blue > Gold > Green > Orange
NON_RESPONSE_STYLE_ORDER = [2, 3, 4, 5, 1, 6]  # HE > TD > A > SS > NR > DIA

_NON_RESPONSE_NAME_KEYS = {
    "nonresponse/unknown",
    "nonresponse",
    "non-response/unknown",
    "non-response",
    "unknown",
}


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum() or ch in {"/", "-"})


def find_non_response_swimmer_type_id(swimmer_types: Mapping[int, str]) -> Optional[int]:
    """Return the configured Non-Response swimmer type id if present."""
    for swimmer_type_id, swimmer_type_name in swimmer_types.items():
        normalized = _normalize_name(str(swimmer_type_name))
        if normalized in _NON_RESPONSE_NAME_KEYS:
            return int(swimmer_type_id)

    if NON_RESPONSE_SWIMMER_TYPE_ID in swimmer_types:
        return NON_RESPONSE_SWIMMER_TYPE_ID
    return None


def coerce_swimmer_type_id(
    raw_value: Any,
    swimmer_types: Mapping[int, str],
    *,
    allow_invalid_passthrough: bool = False,
) -> Optional[int]:
    """Return a valid swimmer type id, defaulting to Non-Response when needed."""
    default_type_id = find_non_response_swimmer_type_id(swimmer_types)

    try:
        if raw_value is None:
            raise ValueError
        text = str(raw_value).strip()
        if not text or text.lower() == "nan":
            raise ValueError
        swimmer_type_id = int(float(text))
    except (TypeError, ValueError):
        swimmer_type_id = None

    if swimmer_type_id in swimmer_types:
        return swimmer_type_id
    if default_type_id is not None:
        return default_type_id
    if allow_invalid_passthrough:
        return swimmer_type_id
    return None


def is_non_response_swimmer_type(swimmer_type_id: Any, swimmer_types: Mapping[int, str]) -> bool:
    """Return True when the id matches the configured Non-Response type."""
    default_type_id = find_non_response_swimmer_type_id(swimmer_types)
    return default_type_id is not None and swimmer_type_id == default_type_id
