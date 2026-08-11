"""DataLoader error handling for malformed and unsafe CSV inputs."""

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


class TestFailSafeInputValidation:
    @staticmethod
    def _csv(generated: str, name: str) -> str:
        return os.path.join(generated, f'{name}.csv')

    def test_missing_instructor_qualifications_default_false(self, data_dirs):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'instructors')
        frame = pd.read_csv(path).drop(columns=[
            'can_teach_NL',
            'can_teach_babies',
            'can_teach_adults',
            'can_teach_adapted',
        ])
        frame.to_csv(path, index=False)

        loader = DataLoader(data_dir)
        loader.load_all()

        instructor = loader.instructors[1]
        assert instructor.can_teach_NL is True
        assert instructor.can_teach_babies is False
        assert instructor.can_teach_adults is False
        assert instructor.can_teach_adapted is False

    def test_blank_reference_metadata_is_allowed(self, data_dirs):
        data_dir, source, _ = data_dirs
        colors_path = os.path.join(source, 'personality_colors.csv')
        colors = pd.read_csv(colors_path)
        colors['traits'] = ''
        colors.to_csv(colors_path, index=False)
        styles_path = os.path.join(source, 'instructor_styles.csv')
        styles = pd.read_csv(styles_path)
        styles[['style_code', 'traits', 'expertise_area']] = ''
        styles.to_csv(styles_path, index=False)

        loader = DataLoader(data_dir)
        loader.load_all()

        assert loader.personality_colors[1].traits == ''
        assert loader.instructor_styles[1].style_code == ''
        assert loader.instructor_styles[1].expertise_area == ''

    def test_explicit_instructor_boolean_strings_are_parsed(self, data_dirs):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'instructors')
        frame = pd.read_csv(path)
        frame = frame.astype({
            'can_teach_babies': 'object',
            'can_teach_adults': 'object',
            'can_teach_adapted': 'object',
        })
        frame.loc[0, 'can_teach_babies'] = 'false'
        frame.loc[0, 'can_teach_adults'] = '0'
        frame.loc[0, 'can_teach_adapted'] = 'yes'
        frame.to_csv(path, index=False)

        loader = DataLoader(data_dir)
        loader.load_all()

        instructor = loader.instructors[1]
        assert instructor.can_teach_babies is False
        assert instructor.can_teach_adults is False
        assert instructor.can_teach_adapted is True

    def test_invalid_instructor_boolean_is_rejected(self, data_dirs):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'instructors')
        frame = pd.read_csv(path)
        frame['can_teach_adapted'] = frame['can_teach_adapted'].astype('object')
        frame.loc[0, 'can_teach_adapted'] = 'maybe'
        frame.to_csv(path, index=False)

        with pytest.raises(ValueError, match=r'can_teach_adapted must be one of'):
            DataLoader(data_dir).load_all()

    @pytest.mark.parametrize('age', ['nan', 'inf', -1, 101])
    def test_non_finite_or_out_of_range_age_is_rejected(self, data_dirs, age):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'swimmers')
        frame = pd.read_csv(path)
        frame['age'] = frame['age'].astype('object')
        frame.loc[0, 'age'] = age
        frame.to_csv(path, index=False)

        with pytest.raises(ValueError, match=r'age (is required|must be finite|must be)'):
            DataLoader(data_dir).load_all()

    @pytest.mark.parametrize('skill_level', [0, 13, 2.5, 'inf'])
    def test_invalid_skill_level_is_rejected(self, data_dirs, skill_level):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'swimmers')
        frame = pd.read_csv(path)
        frame['skill_level'] = frame['skill_level'].astype('object')
        frame.loc[0, 'skill_level'] = skill_level
        frame.to_csv(path, index=False)

        with pytest.raises(ValueError, match=r'skill_level must be'):
            DataLoader(data_dir).load_all()

    @pytest.mark.parametrize(
        ('filename', 'key'),
        [
            ('instructors', 'instructor_id'),
            ('swimmers', 'swimmer_id'),
            ('classes', 'class_id'),
            ('historical_pairings', 'swimmer_id'),
        ],
    )
    def test_duplicate_entity_keys_are_rejected(
        self, data_dirs, filename, key
    ):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, filename)
        frame = pd.read_csv(path)
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        frame.to_csv(path, index=False)

        with pytest.raises(ValueError, match=rf'duplicate key.*{key}'):
            DataLoader(data_dir).load_all()

    def test_singleton_pair_is_rejected(self, data_dirs):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'swimmers')
        frame = pd.read_csv(path)
        frame.loc[0, 'pair_id'] = 10
        frame.to_csv(path, index=False)

        with pytest.raises(ValueError, match=r'Pair 10 has 1 swimmers'):
            DataLoader(data_dir).load_all()

    @pytest.mark.parametrize(
        ('second_age', 'second_level', 'message'),
        [
            (8, 5, 'maximum skill-level difference'),
            (11, 3, 'maximum age difference'),
        ],
    )
    def test_pair_hard_constraint_violations_are_rejected(
        self, data_dirs, second_age, second_level, message
    ):
        data_dir, _, generated = data_dirs
        path = self._csv(generated, 'swimmers')
        frame = pd.read_csv(path)
        frame.loc[0, 'pair_id'] = 10
        second = frame.iloc[0].copy()
        second['swimmer_id'] = 2
        second['first_name'] = 'Noah'
        second['pair_id'] = 10
        second['age'] = second_age
        second['skill_level'] = second_level
        frame = pd.concat([frame, second.to_frame().T], ignore_index=True)
        frame.to_csv(path, index=False)

        with pytest.raises(ValueError, match=message):
            DataLoader(data_dir).load_all()

    def test_from_files_uses_same_strict_validation(self, data_dirs):
        _, source, generated = data_dirs
        swimmers_path = self._csv(generated, 'swimmers')
        swimmers = pd.read_csv(swimmers_path)
        swimmers.loc[0, 'skill_level'] = 0
        swimmers.to_csv(swimmers_path, index=False)

        with pytest.raises(ValueError, match=r'skill_level must be at least 1'):
            DataLoader.from_files(
                classes_path=self._csv(generated, 'classes'),
                swimmers_path=swimmers_path,
                instructors_path=self._csv(generated, 'instructors'),
                historical_path=self._csv(generated, 'historical_pairings'),
                source_dir=source,
            )
