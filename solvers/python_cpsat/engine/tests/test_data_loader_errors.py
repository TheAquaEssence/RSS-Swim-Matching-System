"""DataLoader error handling for malformed and empty CSV inputs (D5).

Pins the current failure behavior so regressions in the descriptive-error
contract (FileNotFoundError / ValueError from DataLoader._read_csv) are
caught. Where today's behavior is a raw KeyError, the test documents that
explicitly rather than asserting a friendlier error that doesn't exist yet.
"""

import os

import pandas as pd
import pytest

from solvers.python_cpsat.engine.data_loader import DataLoader


def build_valid_data_dir(tmpdir: str) -> tuple[str, str]:
    """Create the minimal valid source/ + generated/ CSV layout."""
    source = os.path.join(tmpdir, 'source')
    generated = os.path.join(tmpdir, 'generated')
    os.makedirs(source, exist_ok=True)
    os.makedirs(generated, exist_ok=True)

    pd.DataFrame({
        'color_id': [1, 2, 3, 4],
        'color_name': ['Blue', 'Orange', 'Green', 'Gold'],
        'traits': ['t'] * 4,
    }).to_csv(os.path.join(source, 'personality_colors.csv'), index=False)

    pd.DataFrame({
        'style_id': [1, 2, 3, 4, 5, 6],
        'style_code': ['NR', 'HE', 'TD', 'A', 'SS', 'DIA'],
        'style_name': ['New RSS', 'High Energy', 'Technique', 'Adapted', 'Soft-Spoken', 'Do-It-All'],
        'traits': ['t'] * 6,
        'expertise_area': ['e'] * 6,
    }).to_csv(os.path.join(source, 'instructor_styles.csv'), index=False)

    pd.DataFrame({
        'swimmer_type_id': [1, 8],
        'swimmer_type_name': ['The Nervous/New', 'Non-Response / Unknown'],
    }).to_csv(os.path.join(source, 'swimmer_types.csv'), index=False)

    pd.DataFrame({
        'swimmer_type_id': [1] * 4 + [8] * 4,
        'color_id': [1, 2, 3, 4, 1, 4, 3, 2],
        'rank': [1, 2, 3, 4, 1, 2, 3, 4],
    }).to_csv(os.path.join(source, 'swimmer_type_color_rankings.csv'), index=False)

    pd.DataFrame({
        'swimmer_type_id': [1] * 6 + [8] * 6,
        'style_id': [1, 2, 5, 4, 3, 6, 2, 3, 4, 5, 1, 6],
        'rank': [1, 2, 3, 4, 5, 6] * 2,
    }).to_csv(os.path.join(source, 'swimmer_type_style_rankings.csv'), index=False)

    pd.DataFrame({
        'instructor_id': [1],
        'first_name': ['Sarah'],
        'last_name': ['Chen'],
        'primary_color_id': [1],
        'secondary_color_id': [2],
        'primary_style_id': [1],
        'secondary_style_id': [2],
        'is_team_captain': [False],
        'can_teach_NL': [True],
        'can_teach_babies': [True],
        'can_teach_adults': [True],
        'can_teach_adapted': [True],
    }).to_csv(os.path.join(generated, 'instructors.csv'), index=False)

    pd.DataFrame({
        'swimmer_id': [1],
        'first_name': ['Emma'],
        'last_name': ['Wilson'],
        'swimmer_type_id': [1],
        'skill_level': [3],
        'age': [8.0],
        'has_special_needs': [False],
        'notes': [''],
        'pair_id': [''],
    }).to_csv(os.path.join(generated, 'swimmers.csv'), index=False)

    pd.DataFrame({
        'class_id': [1],
        'day_of_week': ['Monday'],
        'start_time': ['09:00'],
        'end_time': ['09:30'],
        'instructor_id': [1],
        'swimmer_1_id': [''],
        'swimmer_2_id': [''],
    }).to_csv(os.path.join(generated, 'classes.csv'), index=False)

    pd.DataFrame({
        'swimmer_id': [1],
        'instructor_id': [1],
        'session': ['Fall 2025'],
        'num_sessions': [3],
    }).to_csv(os.path.join(generated, 'historical_pairings.csv'), index=False)

    return source, generated


@pytest.fixture
def data_dirs(tmp_path):
    source, generated = build_valid_data_dir(str(tmp_path))
    return str(tmp_path), source, generated


class TestMissingFiles:
    def test_missing_swimmers_csv_raises_descriptive_error(self, data_dirs):
        data_dir, _, generated = data_dirs
        os.remove(os.path.join(generated, 'swimmers.csv'))
        with pytest.raises(FileNotFoundError, match=r'Required CSV not found.*swimmers'):
            DataLoader(data_dir).load_all()

    def test_missing_historical_pairings_raises_descriptive_error(self, data_dirs):
        data_dir, _, generated = data_dirs
        os.remove(os.path.join(generated, 'historical_pairings.csv'))
        with pytest.raises(FileNotFoundError, match=r'Required CSV not found.*historical'):
            DataLoader(data_dir).load_all()

    def test_missing_reference_table_raises_descriptive_error(self, data_dirs):
        data_dir, source, _ = data_dirs
        os.remove(os.path.join(source, 'personality_colors.csv'))
        with pytest.raises(FileNotFoundError, match=r'Required CSV not found.*personality'):
            DataLoader(data_dir).load_all()


class TestEmptyAndMalformedFiles:
    def test_zero_byte_swimmers_csv_raises_value_error(self, data_dirs):
        data_dir, _, generated = data_dirs
        open(os.path.join(generated, 'swimmers.csv'), 'w').close()
        with pytest.raises(ValueError, match=r'Failed to parse.*swimmers'):
            DataLoader(data_dir).load_all()

    def test_zero_byte_reference_table_raises_value_error(self, data_dirs):
        data_dir, source, _ = data_dirs
        open(os.path.join(source, 'personality_colors.csv'), 'w').close()
        with pytest.raises(ValueError, match=r'Failed to parse.*personality'):
            DataLoader(data_dir).load_all()

    def test_header_only_swimmers_csv_fails_validation(self, data_dirs):
        # A header-only swimmers file parses to zero swimmers; the load then
        # fails in validation because historical pairings reference swimmer 1.
        data_dir, _, generated = data_dirs
        with open(os.path.join(generated, 'swimmers.csv'), 'w', encoding='utf-8') as f:
            f.write(
                'swimmer_id,first_name,last_name,swimmer_type_id,skill_level,'
                'age,has_special_needs,notes,pair_id\n'
            )
        with pytest.raises(ValueError, match=r'Data validation failed'):
            DataLoader(data_dir).load_all()

    def test_swimmers_csv_missing_columns_raises(self, data_dirs):
        # Current behavior: a raw KeyError on the first missing column, not a
        # descriptive ValueError. The test documents that contract; if loading
        # ever gains schema validation, update the expected exception here.
        data_dir, _, generated = data_dirs
        pd.DataFrame({'swimmer_id': [1]}).to_csv(
            os.path.join(generated, 'swimmers.csv'), index=False
        )
        with pytest.raises((KeyError, ValueError)):
            DataLoader(data_dir).load_all()

    def test_ragged_swimmers_csv_raises(self, data_dirs):
        data_dir, _, generated = data_dirs
        with open(os.path.join(generated, 'swimmers.csv'), 'w', encoding='utf-8') as f:
            f.write('swimmer_id,first_name\n1,A,EXTRA,EXTRA,5\n')
        with pytest.raises((KeyError, ValueError)):
            DataLoader(data_dir).load_all()


class TestValidBaseline:
    def test_unmodified_fixture_loads(self, data_dirs):
        """Guard: the fixture itself must be valid, or the error tests above
        would pass for the wrong reason."""
        data_dir, _, _ = data_dirs
        loader = DataLoader(data_dir)
        loader.load_all()
        assert len(loader.swimmers) == 1
        assert len(loader.instructors) == 1
        assert len(loader.classes) == 1
