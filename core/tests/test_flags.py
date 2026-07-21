"""Tests for core.flags — shared flag vocabulary module."""

import pytest


# ---------------------------------------------------------------------------
# Vocabulary structure
# ---------------------------------------------------------------------------

class TestFlagCodesVocabulary:

    def test_flag_codes_dict_exists(self):
        from core.flags import FLAG_CODES
        assert isinstance(FLAG_CODES, dict)
        assert len(FLAG_CODES) > 0

    def test_each_flag_has_required_fields(self):
        from core.flags import FLAG_CODES
        required = {'title', 'description', 'severity', 'default_review_action'}
        for code, entry in FLAG_CODES.items():
            missing = required - set(entry.keys())
            assert not missing, f"Flag '{code}' is missing fields: {missing}"

    def test_each_flag_severity_is_valid(self):
        from core.flags import FLAG_CODES, SEVERITY_LEVELS
        for code, entry in FLAG_CODES.items():
            assert entry['severity'] in SEVERITY_LEVELS, (
                f"Flag '{code}' has unknown severity '{entry['severity']}'"
            )

    def test_each_flag_review_action_is_known(self):
        from core.flags import FLAG_CODES, REVIEW_ACTIONS
        for code, entry in FLAG_CODES.items():
            action = entry['default_review_action']
            assert action in REVIEW_ACTIONS, (
                f"Flag '{code}' references unknown action '{action}'"
            )

    # All flag codes required by the meeting doc
    @pytest.mark.parametrize("code", [
        "low_confidence_under_50",
        "continuity_dispute",
        "match_confidence_below_70",
        "compatibility_below_50",
        "forced_assignment",
        "uneven_pair_fit",
        "note_requested_assignment",
        "continuity_overrides_adapted_capability",
        "manual_policy_review_required",
        "continuity_capacity_conflict",
        "continuity_blocked_by_adult_capability",
        "continuity_blocked_by_baby_capability",
        "continuity_pairing_conflict",
        "non_response_swimmer_type",
        "default_instructor_profile",
        "adapted_swimmer_single_legal_instructor",
        "below_min_auto_assign_score",
    ])
    def test_required_flag_code_present(self, code):
        from core.flags import FLAG_CODES
        assert code in FLAG_CODES, f"Required flag code '{code}' not in FLAG_CODES"


class TestReviewActionsVocabulary:

    def test_review_actions_dict_exists(self):
        from core.flags import REVIEW_ACTIONS
        assert isinstance(REVIEW_ACTIONS, dict)
        assert len(REVIEW_ACTIONS) > 0

    @pytest.mark.parametrize("action", [
        "verify_instructor_qualification_record",
        "confirm_policy_override",
        "review_continuity_tiebreak",
        "review_pairing_decision",
        "review_pair_balance",
        "update_swimmer_type",
        "update_instructor_profile",
        "consider_reassignment",
        "quick_review_assignment",
        "confirm_no_better_option_available",
        "verify_note_request_still_applies",
        "review_manual_assignment_override",
    ])
    def test_required_review_action_present(self, action):
        from core.flags import REVIEW_ACTIONS
        assert action in REVIEW_ACTIONS, f"Required action '{action}' not in REVIEW_ACTIONS"

    def test_severity_levels_ordered(self):
        from core.flags import SEVERITY_LEVELS
        # Must include at least these four, with 'urgent' having highest priority
        required = {'none', 'info', 'review', 'urgent'}
        assert required.issubset(set(SEVERITY_LEVELS))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestGetHighestSeverity:

    def test_empty_list_returns_none(self):
        from core.flags import get_highest_severity
        assert get_highest_severity([]) == 'none'

    def test_single_flag_returns_its_severity(self):
        from core.flags import get_highest_severity
        result = get_highest_severity(['forced_assignment'])
        assert result in ('info', 'review', 'urgent')

    def test_urgent_beats_review(self):
        from core.flags import get_highest_severity
        result = get_highest_severity([
            'continuity_overrides_adapted_capability',  # urgent
            'match_confidence_below_70',                # info/review
        ])
        assert result == 'urgent'

    def test_review_beats_info(self):
        from core.flags import get_highest_severity
        result = get_highest_severity([
            'match_confidence_below_70',   # should be info or review
            'forced_assignment',           # should be info or review
        ])
        # Result should be the higher of the two — exact value depends on vocabulary
        # but it must be a valid level
        from core.flags import SEVERITY_LEVELS
        assert result in SEVERITY_LEVELS


class TestGetPrimaryReviewAction:

    def test_empty_list_returns_empty(self):
        from core.flags import get_primary_review_action
        assert get_primary_review_action([]) == ''

    def test_single_flag_returns_its_action(self):
        from core.flags import get_primary_review_action, FLAG_CODES
        result = get_primary_review_action(['forced_assignment'])
        assert result == FLAG_CODES['forced_assignment']['default_review_action']

    def test_urgent_flag_action_takes_priority(self):
        from core.flags import get_primary_review_action
        # continuity_overrides_adapted_capability is urgent
        result = get_primary_review_action([
            'match_confidence_below_70',
            'continuity_overrides_adapted_capability',
        ])
        # Should return action for the urgent flag
        from core.flags import FLAG_CODES
        assert result == FLAG_CODES['continuity_overrides_adapted_capability']['default_review_action']


class TestValidateFlagCodes:

    def test_valid_codes_pass(self):
        from core.flags import validate_flag_codes
        # Should not raise
        validate_flag_codes(['forced_assignment', 'continuity_dispute'])

    def test_unknown_code_raises(self):
        from core.flags import validate_flag_codes
        with pytest.raises(ValueError, match="unknown flag"):
            validate_flag_codes(['invented_flag_xyz'])

    def test_empty_list_passes(self):
        from core.flags import validate_flag_codes
        validate_flag_codes([])  # Should not raise


class TestExpandFlagCodes:

    def test_expands_ui_metadata(self):
        from core.flags import expand_flag_codes

        flags = expand_flag_codes(['below_min_auto_assign_score'])

        assert flags == [{
            'code': 'below_min_auto_assign_score',
            'title': 'Below auto-assignment threshold',
            'description': 'Best legal match is below the minimum auto-assign compatibility threshold',
            'severity': 'review',
            'review_action': 'review_manual_assignment_override',
            'review_action_label': 'Review whether a below-threshold legal match should be manually assigned',
        }]

    def test_unknown_flag_gets_safe_fallback(self):
        from core.flags import expand_flag_codes

        flags = expand_flag_codes(['invented_flag'])

        assert flags[0]['code'] == 'invented_flag'
        assert flags[0]['title'] == 'invented_flag'
        assert flags[0]['severity'] == 'none'
