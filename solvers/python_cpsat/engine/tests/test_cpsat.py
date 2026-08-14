"""Tests for Phase 2: CP-SAT Optimization (v2)."""

import pytest
from core.scoring import CompatibilityScorer
from solvers.python_cpsat.engine.data_loader import Swimmer, Instructor
from solvers.python_cpsat.engine import phase2_cpsat
from solvers.python_cpsat.engine.phase2_cpsat import (
    compatibility_pass,
    _get_pair_key,
    _compute_all_scores,
    _resolve_time_limit_seconds,
    _resolve_min_auto_assign_score,
    _build_greedy_hint,
    diagnose_unassigned_swimmers,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def rankings():
    """Minimal rankings for 2 swimmer types."""
    color = {
        (1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4,
        (2, 1): 3, (2, 2): 4, (2, 3): 1, (2, 4): 2,
    }
    style = {
        (1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6,
        (2, 2): 1, (2, 3): 2, (2, 5): 3, (2, 4): 4, (2, 1): 5, (2, 6): 6,
    }
    return color, style


@pytest.fixture
def scorer(rankings):
    return CompatibilityScorer(*rankings)


def _make_swimmer(sid, type_id=1, pair_id=None, age=10.0, special_needs=False):
    return Swimmer(
        swimmer_id=sid, first_name=f"S{sid}", last_name="Test",
        swimmer_type_id=type_id, skill_level=3, age=age,
        has_special_needs=special_needs, notes="", pair_id=pair_id
    )


def _make_instructor(iid, primary_color=1, secondary_color=2,
                     primary_style=1, secondary_style=2,
                     can_adapted=True, can_babies=True, can_adults=True):
    return Instructor(
        instructor_id=iid, first_name=f"I{iid}", last_name="Test",
        primary_color_id=primary_color, secondary_color_id=secondary_color,
        primary_style_id=primary_style, secondary_style_id=secondary_style,
        is_team_captain=False, can_teach_NL=True,
        can_teach_babies=can_babies, can_teach_adults=can_adults,
        can_teach_adapted=can_adapted
    )


class MockDataLoader:
    """Minimal mock for style code lookups."""
    _styles = {1: 'NR', 2: 'HE', 3: 'TD', 4: 'A', 5: 'SS', 6: 'DIA'}

    def get_style_code(self, style_id):
        return self._styles.get(style_id)


# ============================================================================
# Tests
# ============================================================================

class TestPairKey:

    def test_consistent_ordering(self):
        s1 = _make_swimmer(5)
        s2 = _make_swimmer(3)
        assert _get_pair_key(s1, s2) == (3, 5)
        assert _get_pair_key(s2, s1) == (3, 5)


class TestScorePreComputation:

    def test_individual_scores_computed(self, scorer):
        individuals = [_make_swimmer(1), _make_swimmer(2, type_id=2)]
        instructors = [_make_instructor(100), _make_instructor(200)]
        data_loader = MockDataLoader()

        scores, pair_details = _compute_all_scores(
            individuals, [], instructors, scorer, data_loader
        )

        assert ('individual', 1, 100) in scores
        assert ('individual', 1, 200) in scores
        assert ('individual', 2, 100) in scores
        assert ('individual', 2, 200) in scores
        assert len(scores) == 4

    def test_pair_scores_computed(self, scorer):
        pairs = [(_make_swimmer(1, pair_id=10), _make_swimmer(2, pair_id=10, type_id=2))]
        instructors = [_make_instructor(100)]
        data_loader = MockDataLoader()

        scores, pair_details = _compute_all_scores([], pairs, instructors, scorer, data_loader)

        pair_key = (1, 2)
        assert ('pair', pair_key, 100) in scores
        assert (pair_key, 100) in pair_details

    def test_scores_in_valid_range(self, scorer):
        individuals = [_make_swimmer(1)]
        instructors = [_make_instructor(100)]
        data_loader = MockDataLoader()

        scores, _ = _compute_all_scores(individuals, [], instructors, scorer, data_loader)
        for score in scores.values():
            assert 0 <= score <= 100


class TestCompatibilityPass:

    def test_basic_assignment(self, scorer):
        """Every swimmer gets exactly one instructor."""
        swimmers = [_make_swimmer(1), _make_swimmer(2, type_id=2)]
        instructors = [
            _make_instructor(100),
            _make_instructor(200, primary_color=3, secondary_color=4,
                             primary_style=2, secondary_style=3),
        ]
        data_loader = MockDataLoader()

        matches = compatibility_pass(swimmers, instructors, scorer, data_loader)
        assert len(matches) == 2

        assigned_swimmers = {m['swimmer_id'] for m in matches}
        assert assigned_swimmers == {1, 2}

        assigned_instructors = {m['instructor_id'] for m in matches}
        assert len(assigned_instructors) == 2

    def test_empty_input(self, scorer):
        data_loader = MockDataLoader()
        matches = compatibility_pass([], [_make_instructor(100)], scorer, data_loader)
        assert matches == []

    def test_pair_assignment(self, scorer):
        """Pair gets assigned as a unit."""
        swimmers = [
            _make_swimmer(1, pair_id=10),
            _make_swimmer(2, pair_id=10, type_id=2),
            _make_swimmer(3),
        ]
        instructors = [
            _make_instructor(100),
            _make_instructor(200, primary_color=3, secondary_color=4,
                             primary_style=2, secondary_style=3),
        ]
        data_loader = MockDataLoader()

        matches = compatibility_pass(swimmers, instructors, scorer, data_loader)
        assert len(matches) == 2  # 1 pair + 1 individual

        pair_match = next(m for m in matches if m['type'] == 'pair')
        assert 'swimmer_1_score' in pair_match
        assert 'swimmer_2_score' in pair_match

    def test_adapted_constraint(self, scorer):
        """Special needs swimmer cannot go to non-adapted instructor."""
        swimmers = [_make_swimmer(1, special_needs=True)]
        instructors = [
            _make_instructor(100, can_adapted=False),
            _make_instructor(200, can_adapted=True),
        ]
        data_loader = MockDataLoader()

        matches = compatibility_pass(swimmers, instructors, scorer, data_loader)
        assert matches[0]['instructor_id'] == 200

    def test_baby_constraint(self, scorer):
        """Baby swimmer must go to baby-capable instructor."""
        swimmers = [_make_swimmer(1, age=1.5)]
        instructors = [
            _make_instructor(100, can_babies=False),
            _make_instructor(200, can_babies=True),
        ]
        data_loader = MockDataLoader()

        matches = compatibility_pass(swimmers, instructors, scorer, data_loader)
        assert matches[0]['instructor_id'] == 200

    def test_adult_constraint(self, scorer):
        """Adult swimmer must go to adult-capable instructor."""
        swimmers = [_make_swimmer(1, age=25.0)]
        instructors = [
            _make_instructor(100, can_adults=False),
            _make_instructor(200, can_adults=True),
        ]
        data_loader = MockDataLoader()

        matches = compatibility_pass(swimmers, instructors, scorer, data_loader)
        assert matches[0]['instructor_id'] == 200

    def test_instructor_capacity(self, scorer):
        """Each instructor gets at most one entity."""
        swimmers = [_make_swimmer(1), _make_swimmer(2, type_id=2), _make_swimmer(3)]
        instructors = [
            _make_instructor(100),
            _make_instructor(200),
            _make_instructor(300),
        ]
        data_loader = MockDataLoader()

        matches = compatibility_pass(swimmers, instructors, scorer, data_loader)
        instructor_ids = [m['instructor_id'] for m in matches]
        assert len(instructor_ids) == len(set(instructor_ids))  # All unique

    def test_assignment_count_beats_compatibility_for_acceptable_pairs(self, monkeypatch):
        """A pair should beat one individual when both candidate scores are auto-assignable."""
        swimmers = [
            _make_swimmer(1, pair_id=10),
            _make_swimmer(2, pair_id=10, type_id=2),
            _make_swimmer(3),
        ]
        instructors = [_make_instructor(100)]
        pair_key = (1, 2)

        def fake_scores(individuals, pairs, available_instructors, scorer, data_loader):
            return (
                {
                    ('individual', 3, 100): 100.0,
                    ('pair', pair_key, 100): 55.0,
                },
                {
                    (pair_key, 100): (55.0, 55.0, 55.0),
                },
            )

        monkeypatch.setattr(phase2_cpsat, '_compute_all_scores', fake_scores)

        matches = compatibility_pass(
            swimmers, instructors, object(), object(),
            config={'min_auto_assign_score': 50.0},
        )

        assert len(matches) == 1
        assert matches[0]['type'] == 'pair'
        assert {matches[0]['swimmer_1_id'], matches[0]['swimmer_2_id']} == {1, 2}

    def test_poor_match_below_quality_floor_is_left_unassigned(self, monkeypatch):
        """A legal candidate below min_auto_assign_score should not be forced into a slot."""
        swimmers = [_make_swimmer(1)]
        instructors = [_make_instructor(100)]

        def fake_scores(individuals, pairs, available_instructors, scorer, data_loader):
            return (
                {('individual', 1, 100): 20.0},
                {},
            )

        monkeypatch.setattr(phase2_cpsat, '_compute_all_scores', fake_scores)

        matches = compatibility_pass(
            swimmers, instructors, object(), object(),
            config={'min_auto_assign_score': 50.0},
        )

        assert matches == []


class TestTimeBudget:

    def test_explicit_time_limit_override_wins(self):
        limit = _resolve_time_limit_seconds(
            [_make_swimmer(1)],
            [],
            [_make_instructor(100)],
            config={'max_time_seconds': 12},
        )
        assert limit == 12.0

    def test_large_problem_gets_extended_budget(self):
        individuals = [_make_swimmer(i) for i in range(1, 401)]
        pairs = [(_make_swimmer(1000 + i * 2, pair_id=5000 + i), _make_swimmer(1001 + i * 2, pair_id=5000 + i)) for i in range(50)]
        instructors = [_make_instructor(i) for i in range(1, 501)]

        limit = _resolve_time_limit_seconds(individuals, pairs, instructors)

        assert limit == 60.0


class TestMinimumAutoAssignScore:

    def test_default_min_auto_assign_score_is_50(self):
        assert _resolve_min_auto_assign_score() == 50.0

    def test_min_auto_assign_score_override(self):
        assert _resolve_min_auto_assign_score({'min_auto_assign_score': 35}) == 35.0

    def test_min_auto_assign_score_override_is_clamped(self):
        assert _resolve_min_auto_assign_score({'min_auto_assign_score': -10}) == 0.0
        assert _resolve_min_auto_assign_score({'min_auto_assign_score': 250}) == 100.0

    def test_unassigned_diagnostic_flags_quality_floor_block(self, monkeypatch):
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)

        def fake_scores(individuals, pairs, available_instructors, scorer, data_loader):
            return ({('individual', 1, 100): 20.0}, {})

        monkeypatch.setattr(phase2_cpsat, '_compute_all_scores', fake_scores)

        diagnostics = diagnose_unassigned_swimmers(
            [swimmer],
            [swimmer],
            [instructor],
            object(),
            object(),
            config={'min_auto_assign_score': 50.0},
        )

        assert diagnostics[1]['flag_codes'] == ['below_min_auto_assign_score']
        assert diagnostics[1]['best_available_score'] == 20.0
        assert diagnostics[1]['best_available_instructor_id'] == 100
        assert diagnostics[1]['min_auto_assign_score'] == 50.0

    def test_unassigned_diagnostic_omits_capacity_only_case(self, monkeypatch):
        swimmer = _make_swimmer(1)
        instructor = _make_instructor(100)

        def fake_scores(individuals, pairs, available_instructors, scorer, data_loader):
            return ({('individual', 1, 100): 80.0}, {})

        monkeypatch.setattr(phase2_cpsat, '_compute_all_scores', fake_scores)

        diagnostics = diagnose_unassigned_swimmers(
            [swimmer],
            [swimmer],
            [instructor],
            object(),
            object(),
            config={'min_auto_assign_score': 50.0},
        )

        assert diagnostics == {}

    def test_best_candidate_supports_string_instructor_ids(self):
        candidates = [
            (20.0, _make_instructor("010")),
            (20.0, _make_instructor("002")),
            (10.0, _make_instructor("001")),
        ]

        best = phase2_cpsat._best_candidate(candidates)

        assert best is not None
        assert best[0] == 20.0
        assert best[1].instructor_id == "002"


class TestWarmStartHint:

    def test_greedy_hint_respects_feasibility_and_capacity(self):
        swimmers = [
            _make_swimmer(1, special_needs=True),
            _make_swimmer(2, pair_id=10),
            _make_swimmer(3, pair_id=10, type_id=2),
        ]
        individuals = [swimmers[0]]
        pairs = [(swimmers[1], swimmers[2])]
        instructors = [
            _make_instructor(100, can_adapted=True),
            _make_instructor(200, can_adapted=False),
        ]
        pair_key = (2, 3)
        compatibility_scores = {
            ('individual', 1, 100): 60.0,
            ('individual', 1, 200): 99.0,
            ('pair', pair_key, 100): 40.0,
            ('pair', pair_key, 200): 80.0,
        }

        hinted_individuals, hinted_pairs = _build_greedy_hint(
            individuals,
            pairs,
            instructors,
            compatibility_scores,
            min_auto_assign_score=0.0,
        )

        assert hinted_individuals == {1: 100}
        assert hinted_pairs == {pair_key: 200}

    def test_greedy_hint_respects_quality_floor(self):
        swimmers = [_make_swimmer(1)]
        instructors = [_make_instructor(100), _make_instructor(200)]
        compatibility_scores = {
            ('individual', 1, 100): 90.0,
            ('individual', 1, 200): 20.0,
        }

        hinted_individuals, hinted_pairs = _build_greedy_hint(
            swimmers,
            [],
            instructors,
            compatibility_scores,
            min_auto_assign_score=50.0,
        )

        assert hinted_individuals == {1: 100}
        assert hinted_pairs == {}


# =============================================================================
# End-to-end: non-response swimmer type flows through all three phases
# =============================================================================

class TestNonResponseSwimmerE2E:
    """Smoke test: a type_id=0 swimmer completes Phases 2→3 without error
    and the final match carries the non_response_swimmer_type flag."""

    @pytest.fixture
    def scorer_nr(self):
        """Scorer that includes type_id=0 neutral rankings."""
        color = {
            (1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4,
            (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4,
        }
        style = {
            (1, 1): 1, (1, 2): 2, (1, 5): 3, (1, 4): 4, (1, 3): 5, (1, 6): 6,
            (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4, (0, 5): 5, (0, 6): 6,
        }
        return CompatibilityScorer(color, style)

    def test_nonresponse_swimmer_assigned_and_flagged(self, scorer_nr):
        """Phase 2 assigns the swimmer; Phase 3 attaches the non_response flag."""
        from solvers.python_cpsat.engine.phase2_cpsat import compatibility_pass
        from solvers.python_cpsat.engine.phase3_explainability import generate_explanations

        class FullMockDataLoader:
            _styles = {1: 'NR', 2: 'HE', 3: 'TD', 4: 'A', 5: 'SS', 6: 'DIA'}
            _colors = {1: 'Blue', 2: 'Orange', 3: 'Green', 4: 'Gold'}
            _types  = {0: 'Non-Response/Unknown', 1: 'The Nervous/New'}
            _style_names = {1: 'New RSS', 2: 'High Energy', 3: 'Technique',
                            4: 'Adapted', 5: 'Soft-Spoken', 6: 'Do-It-All'}

            def __init__(self):
                self.swimmer_types = {
                    type_id: type("SwimmerType", (), {"swimmer_type_name": name})()
                    for type_id, name in self._types.items()
                }
                self.class_resolution_flags = {}

            def get_style_code(self, sid): return self._styles.get(sid)
            def get_color_name(self, cid): return self._colors.get(cid)
            def get_style_name(self, sid): return self._style_names.get(sid)
            def get_swimmer_type_name(self, tid): return self._types.get(tid)

        swimmer = _make_swimmer(1, type_id=0)
        instructor = _make_instructor(1)
        data_loader = FullMockDataLoader()

        # Phase 2 — swimmer has no continuity history, goes straight to CP-SAT
        # compatibility_pass returns only the match list; unassigned is inferred externally
        matches = compatibility_pass(
            [swimmer], [instructor], scorer_nr, data_loader
        )

        assert len(matches) == 1, "Swimmer must be assigned in Phase 2"

        # Phase 3 — generate explanations and flags
        results = generate_explanations(
            matches, [instructor], [swimmer], scorer_nr, data_loader
        )

        assert len(results) == 1
        assert 'non_response_swimmer_type' in results[0]['flag_codes'], (
            "Phase 3 must attach non_response_swimmer_type to type_id=0 matches"
        )
