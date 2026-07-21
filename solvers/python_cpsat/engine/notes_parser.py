"""
Parse swimmer notes fields into structured keyword mappings.

NOTE: This parser is designed for Jackrabbit-shaped import data. Synthetic
fixtures may omit these free-text patterns, so note-driven assignment behavior
is covered by focused tests rather than assumed in every generated dataset.

Recognized patterns:
  prefer <name>   — swimmer prefers this instructor
  avoid <name>    — swimmer prefers not to have this instructor
  no <name>       — synonym for avoid
  always <name>   — swimmer must be assigned to this instructor
  never <name>    — swimmer must not be assigned to this instructor
"""

import re
from typing import Dict, List


_KEYWORD_MAP = {
    'prefer': 'prefer',
    'avoid': 'avoid',
    'no': 'avoid',      # synonym
    'always': 'always',
    'never': 'never',
}

# Matches: keyword followed by the rest of the clause (until ; or end)
_PATTERN = re.compile(
    r'\b(prefer|avoid|no|always|never)\b\s+([^;]+)',
    re.IGNORECASE
)


def parse_notes(notes: str) -> Dict[str, List[str]]:
    """
    Parse a notes string into a dict of {category: [instructor_name, ...]}.

    Returns:
        {
            'prefer': [...],
            'avoid': [...],   # 'no' is merged here
            'always': [...],
            'never': [...],
        }
    """
    result: Dict[str, List[str]] = {
        'prefer': [],
        'avoid': [],
        'always': [],
        'never': [],
    }

    for match in _PATTERN.finditer(notes):
        keyword = match.group(1).lower()
        name = match.group(2).strip().rstrip(';').strip()
        category = _KEYWORD_MAP[keyword]
        if name:
            result[category].append(name)

    return result
