"""Tests for PDF report generation."""
import os
import tempfile
import pytest
from unittest.mock import MagicMock

from solvers.python_cpsat.engine.pdf_report import generate_pdf_report


def _make_mock_swimmer(swimmer_id, name='Test Swimmer', skill_level=5, age=8.0, has_special_needs=False):
    """Create a mock swimmer object."""
    mock = MagicMock()
    mock.swimmer_id = swimmer_id
    mock.name = name
    mock.skill_level = skill_level
    mock.age = age
    mock.has_special_needs = has_special_needs
    return mock


def _make_annotated_match(match_type='compatibility', type_='individual', confidence=75.0,
                          score=70.0, instructor_id=1, swimmer_id=1):
    """Create a test annotated match dict."""
    swimmer = _make_mock_swimmer(swimmer_id)
    return {
        'type': type_,
        'match_type': match_type,
        'instructor_id': instructor_id,
        'instructor_name': f'Instructor {instructor_id}',
        'swimmer_id': swimmer_id,
        'swimmer': swimmer,
        'confidence': confidence,
        'compatibility_score': score,
        'reason_summary': f'Optimal compatibility match ({score:.1f}%)',
    }


def _make_pair_match(confidence=72.0, score=68.0):
    """Create a test pair match."""
    s1 = _make_mock_swimmer(10, name='Swimmer A')
    s2 = _make_mock_swimmer(11, name='Swimmer B')
    return {
        'type': 'pair',
        'match_type': 'compatibility',
        'instructor_id': 2,
        'instructor_name': 'Instructor 2',
        'swimmer_1_id': 10,
        'swimmer_2_id': 11,
        'swimmer_1': s1,
        'swimmer_2': s2,
        'confidence': confidence,
        'compatibility_score': score,
        'reason_summary': f'Optimal compatibility match ({score:.1f}%)',
    }


class TestPdfReportGeneration:
    """Tests for PDF report file generation."""

    def test_generates_file(self):
        """PDF report file is created and non-empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')
            matches = [_make_annotated_match()]
            classes = {1: MagicMock()}

            result = generate_pdf_report(path, matches, [], 0, 1, classes)

            assert result == path
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_with_no_matches(self):
        """PDF report handles empty matches gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')

            result = generate_pdf_report(path, [], [], 0, 0, {})

            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_with_unassigned_swimmers(self):
        """PDF report includes unassigned swimmers section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')
            unassigned = [_make_mock_swimmer(99, name='Unassigned Kid', age=3.5)]
            matches = [_make_annotated_match()]
            classes = {1: MagicMock()}

            result = generate_pdf_report(path, matches, unassigned, 0, 1, classes)

            assert os.path.exists(path)
            assert os.path.getsize(path) > 1000  # Should be substantial

    def test_with_review_flags_and_unassigned_diagnostics(self):
        """PDF report includes flagged matches and unassigned diagnostics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')
            matches = [_make_annotated_match()]
            matches[0]['flag_codes'] = ['forced_assignment']
            unassigned = [_make_mock_swimmer(99, name='Threshold Kid', age=7.0)]
            diagnostics = {
                99: {
                    'flag_codes': ['below_min_auto_assign_score'],
                    'best_available_instructor_name': 'Instructor 9',
                    'best_available_score': 42.0,
                    'min_auto_assign_score': 50.0,
                }
            }

            result = generate_pdf_report(
                path, matches, unassigned, 0, 1, {1: MagicMock()},
                unassigned_diagnostics=diagnostics,
            )

            assert result == path
            assert os.path.exists(path)
            assert os.path.getsize(path) > 1000

    def test_with_pair_matches(self):
        """PDF report handles pair matches correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')
            matches = [_make_pair_match()]
            classes = {1: MagicMock()}

            result = generate_pdf_report(path, matches, [], 0, 1, classes)

            assert os.path.exists(path)

    def test_with_disputed_matches(self):
        """PDF report handles disputed matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')
            matches = [_make_annotated_match(match_type='continuity', confidence=80.0)]
            classes = {1: MagicMock()}
            disputed = {1}  # swimmer_id 1 is disputed

            result = generate_pdf_report(path, matches, [], 1, 0, classes, disputed_ids=disputed)

            assert os.path.exists(path)

    def test_confidence_color_coding(self):
        """PDF generates successfully with various confidence levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'report.pdf')
            matches = [
                _make_annotated_match(confidence=95.0, swimmer_id=1, instructor_id=1),
                _make_annotated_match(confidence=75.0, swimmer_id=2, instructor_id=2),
                _make_annotated_match(confidence=55.0, swimmer_id=3, instructor_id=3),
                _make_annotated_match(confidence=30.0, swimmer_id=4, instructor_id=4),
            ]
            classes = {i: MagicMock() for i in range(1, 5)}

            result = generate_pdf_report(path, matches, [], 0, 4, classes)

            assert os.path.exists(path)

    def test_creates_output_directory(self):
        """PDF report creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'sub', 'dir', 'report.pdf')

            result = generate_pdf_report(path, [], [], 0, 0, {})

            assert os.path.exists(path)
