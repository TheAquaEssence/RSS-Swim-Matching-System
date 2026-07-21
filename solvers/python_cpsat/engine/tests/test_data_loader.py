"""Tests for v2 DataLoader with ranking tables."""

import os
import pytest
import pandas as pd

from solvers.python_cpsat.engine.data_loader import DataLoader


@pytest.fixture
def data_dir(tmp_path):
    """Create a temp data directory with minimal valid CSVs."""
    tmpdir = str(tmp_path)
    source_dir = os.path.join(tmpdir, 'source')
    generated_dir = os.path.join(tmpdir, 'generated')
    os.makedirs(source_dir, exist_ok=True)
    os.makedirs(generated_dir, exist_ok=True)

    # Reference tables
    pd.DataFrame({
        'color_id': [1, 2, 3, 4],
        'color_name': ['Blue', 'Orange', 'Green', 'Gold'],
        'traits': ['t1', 't2', 't3', 't4']
    }).to_csv(os.path.join(source_dir, 'personality_colors.csv'), index=False)

    pd.DataFrame({
        'style_id': [1, 2, 3, 4, 5, 6],
        'style_code': ['NR', 'HE', 'TD', 'A', 'SS', 'DIA'],
        'style_name': ['New RSS', 'High Energy', 'Technique', 'Adapted', 'Soft-Spoken', 'Do-It-All'],
        'traits': ['t'] * 6,
        'expertise_area': ['e'] * 6
    }).to_csv(os.path.join(source_dir, 'instructor_styles.csv'), index=False)

    pd.DataFrame({
        'swimmer_type_id': [1, 8],
        'swimmer_type_name': ['The Nervous/New', 'Non-Response / Unknown']
    }).to_csv(os.path.join(source_dir, 'swimmer_types.csv'), index=False)

    # Ranking tables
    pd.DataFrame({
        'swimmer_type_id': [1, 1, 1, 1, 8, 8, 8, 8],
        'color_id': [1, 2, 3, 4, 1, 4, 3, 2],
        'rank': [1, 2, 3, 4, 1, 2, 3, 4]
    }).to_csv(os.path.join(source_dir, 'swimmer_type_color_rankings.csv'), index=False)

    pd.DataFrame({
        'swimmer_type_id': [1, 1, 1, 1, 1, 1, 8, 8, 8, 8, 8, 8],
        'style_id': [1, 2, 5, 4, 3, 6, 2, 3, 4, 5, 1, 6],
        'rank': [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6]
    }).to_csv(os.path.join(source_dir, 'swimmer_type_style_rankings.csv'), index=False)

    # Entity tables
    pd.DataFrame({
        'instructor_id': [1, 2],
        'first_name': ['Sarah', 'Mike'],
        'last_name': ['Chen', 'Park'],
        'primary_color_id': [1, 3],
        'secondary_color_id': [4, 2],
        'primary_style_id': [3, 6],
        'secondary_style_id': [5, 1],
        'is_team_captain': [False, True],
        'can_teach_NL': [True, True],
        'can_teach_babies': [False, True],
        'can_teach_adults': [True, False],
        'can_teach_adapted': [False, True],
    }).to_csv(os.path.join(generated_dir, 'instructors.csv'), index=False)

    pd.DataFrame({
        'swimmer_id': [1, 2, 3],
        'first_name': ['Emma', 'Liam', 'Ava'],
        'last_name': ['Wilson', 'Johnson', 'Brown'],
        'swimmer_type_id': [1, 1, 1],
        'skill_level': [3, 5, 4],
        'age': [8.0, 10.0, 9.0],
        'has_special_needs': [False, False, False],
        'notes': ['', '', ''],
        'pair_id': ['', '', '']
    }).to_csv(os.path.join(generated_dir, 'swimmers.csv'), index=False)

    pd.DataFrame({
        'class_id': [1, 2],
        'day_of_week': ['Monday', 'Monday'],
        'start_time': ['09:00', '09:30'],
        'end_time': ['09:30', '10:00'],
        'instructor_id': [1, 2],
        'swimmer_1_id': ['', ''],
        'swimmer_2_id': ['', '']
    }).to_csv(os.path.join(generated_dir, 'classes.csv'), index=False)

    pd.DataFrame({
        'swimmer_id': [1],
        'instructor_id': [1],
        'session': ['Fall 2025'],
        'num_sessions': [3]
    }).to_csv(os.path.join(generated_dir, 'historical_pairings.csv'), index=False)

    return tmpdir


class TestDataLoader:

    def test_load_all_succeeds(self, data_dir):
        loader = DataLoader(data_dir)
        loader.load_all()
        assert len(loader.swimmers) == 3
        assert len(loader.instructors) == 2
        assert len(loader.classes) == 2

    def test_ranking_tables_loaded(self, data_dir):
        loader = DataLoader(data_dir)
        loader.load_all()
        assert len(loader.color_rankings) == 8  # 2 types × 4 colors
        assert len(loader.style_rankings) == 12   # 2 types × 6 styles

    def test_ranking_values_correct(self, data_dir):
        loader = DataLoader(data_dir)
        loader.load_all()
        # Type 1 ranks Blue (color 1) as #1
        assert loader.color_rankings[(1, 1)] == 1
        # Type 1 ranks Gold (color 4) as #4
        assert loader.color_rankings[(1, 4)] == 4

    def test_get_ranking_tables(self, data_dir):
        loader = DataLoader(data_dir)
        loader.load_all()
        tables = loader.get_ranking_tables()
        assert 'color' in tables
        assert 'style' in tables
        assert (1, 1) in tables['color']

    def test_style_code_lookup(self, data_dir):
        loader = DataLoader(data_dir)
        loader.load_all()
        assert loader.get_style_code(6) == 'DIA'
        assert loader.get_style_code(3) == 'TD'

    def test_historical_pairings(self, data_dir):
        loader = DataLoader(data_dir)
        loader.load_all()
        pairing = loader.get_historical_pairing(1)
        assert pairing is not None
        assert pairing.instructor_id == 1
        assert pairing.num_sessions == 3

    def test_no_compatibility_tables(self, data_dir):
        """v2 should NOT have compatibility tables."""
        loader = DataLoader(data_dir)
        loader.load_all()
        assert not hasattr(loader, 'color_compatibility')
        assert not hasattr(loader, 'style_compatibility')

    def test_missing_swimmer_type_defaults_to_non_response(self, data_dir):
        pd.DataFrame({
            'swimmer_id': [1],
            'first_name': ['Emma'],
            'last_name': ['Wilson'],
            'swimmer_type_id': [0],
            'skill_level': [3],
            'age': [8.0],
            'has_special_needs': [False],
            'notes': [''],
            'pair_id': ['']
        }).to_csv(os.path.join(data_dir, 'generated', 'swimmers.csv'), index=False)

        loader = DataLoader(data_dir)
        loader.load_all()
        assert loader.swimmers[1].swimmer_type_id == 8


class TestDataLoaderErrorHandling:

    def test_missing_csv_raises_descriptive_error(self, tmp_path):
        """Missing CSV should raise FileNotFoundError with the file name and regeneration hint."""
        source_dir = tmp_path / "source"
        generated_dir = tmp_path / "generated"
        source_dir.mkdir()
        generated_dir.mkdir()
        loader = DataLoader(str(tmp_path))
        with pytest.raises(FileNotFoundError, match="personality_colors.csv"):
            loader.load_all()

    def test_missing_csv_mentions_regeneration_command(self, tmp_path):
        """Error message should tell users how to regenerate data."""
        source_dir = tmp_path / "source"
        generated_dir = tmp_path / "generated"
        source_dir.mkdir()
        generated_dir.mkdir()
        loader = DataLoader(str(tmp_path))
        with pytest.raises(FileNotFoundError, match="run_all.py"):
            loader.load_all()


# =============================================================================
# Non-response swimmer type (type_id=0) — reference data presence checks
# These tests read the REAL data/source/ CSVs (the canonical reference tables)
# to confirm NON_RESPONSE_SWIMMER_TYPE_ID is registered with complete rankings.
# =============================================================================

class TestNonResponseTypeReferenceData:

    def test_non_response_type_exists_in_source_csv(self):
        import csv
        from pathlib import Path
        from core.swimmer_types import NON_RESPONSE_SWIMMER_TYPE_ID
        path = Path("data/source/swimmer_types.csv")
        ids = {int(row["swimmer_type_id"]) for row in csv.DictReader(path.open())}
        assert NON_RESPONSE_SWIMMER_TYPE_ID in ids, (
            f"swimmer_type_id={NON_RESPONSE_SWIMMER_TYPE_ID} must be registered for Jackrabbit non-response swimmers"
        )

    def test_non_response_color_rankings_complete(self):
        """NON_RESPONSE_SWIMMER_TYPE_ID must have ranks 1-4 assigned to all 4 color_ids."""
        import csv
        from pathlib import Path
        from core.swimmer_types import NON_RESPONSE_SWIMMER_TYPE_ID
        path = Path("data/source/swimmer_type_color_rankings.csv")
        ranks = {
            int(row["color_id"]): int(row["rank"])
            for row in csv.DictReader(path.open())
            if int(row["swimmer_type_id"]) == NON_RESPONSE_SWIMMER_TYPE_ID
        }
        assert set(ranks.keys()) == {1, 2, 3, 4}, (
            f"All 4 color_ids must have a rank for type_id={NON_RESPONSE_SWIMMER_TYPE_ID}"
        )
        assert set(ranks.values()) == {1, 2, 3, 4}, "Ranks must be a valid permutation 1-4"

    def test_non_response_style_rankings_complete(self):
        """NON_RESPONSE_SWIMMER_TYPE_ID must have ranks 1-6 assigned to all 6 style_ids."""
        import csv
        from pathlib import Path
        from core.swimmer_types import NON_RESPONSE_SWIMMER_TYPE_ID
        path = Path("data/source/swimmer_type_style_rankings.csv")
        ranks = {
            int(row["style_id"]): int(row["rank"])
            for row in csv.DictReader(path.open())
            if int(row["swimmer_type_id"]) == NON_RESPONSE_SWIMMER_TYPE_ID
        }
        assert set(ranks.keys()) == {1, 2, 3, 4, 5, 6}, (
            f"All 6 style_ids must have a rank for type_id={NON_RESPONSE_SWIMMER_TYPE_ID}"
        )
        assert set(ranks.values()) == {1, 2, 3, 4, 5, 6}, "Ranks must be a valid permutation 1-6"
