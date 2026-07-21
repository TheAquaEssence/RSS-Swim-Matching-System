"""Tests for notes_parser module."""
import pytest
from solvers.python_cpsat.engine.notes_parser import parse_notes


class TestParseNotes:

    def test_empty_notes(self):
        result = parse_notes("")
        assert result == {'prefer': [], 'avoid': [], 'always': [], 'never': []}

    def test_prefer_keyword(self):
        result = parse_notes("prefer Jordan Smith")
        assert "Jordan Smith" in result['prefer']

    def test_no_keyword_maps_to_avoid(self):
        """'no' is a synonym for 'avoid'."""
        result = parse_notes("no Taylor Jones")
        assert "Taylor Jones" in result['avoid']

    def test_never_keyword(self):
        result = parse_notes("never Alex Brown")
        assert "Alex Brown" in result['never']

    def test_always_keyword(self):
        result = parse_notes("always Sam Lee")
        assert "Sam Lee" in result['always']

    def test_case_insensitive(self):
        result = parse_notes("AVOID Jordan Smith")
        assert "Jordan Smith" in result['avoid']

    def test_multiple_keywords(self):
        result = parse_notes("prefer Jordan Smith; no Taylor Jones")
        assert "Jordan Smith" in result['prefer']
        assert "Taylor Jones" in result['avoid']

    def test_unrecognized_text_ignored(self):
        result = parse_notes("loves swimming with friends")
        assert all(len(v) == 0 for v in result.values())
