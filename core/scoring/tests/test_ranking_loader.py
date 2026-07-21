"""Tests for RankingLoader."""

import os
import tempfile
import pytest
from core.scoring.ranking_loader import RankingLoader


@pytest.fixture
def valid_source_dir():
    """Create a temp directory with valid ranking CSVs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Color rankings: 2 swimmer types × 4 colors
        with open(os.path.join(tmpdir, 'swimmer_type_color_rankings.csv'), 'w') as f:
            f.write('swimmer_type_id,color_id,rank\n')
            # Type 1: Blue(1)=1st, Orange(2)=2nd, Green(3)=3rd, Gold(4)=4th
            f.write('1,1,1\n1,2,2\n1,3,3\n1,4,4\n')
            # Type 2: Green(3)=1st, Gold(4)=2nd, Blue(1)=3rd, Orange(2)=4th
            f.write('2,3,1\n2,4,2\n2,1,3\n2,2,4\n')

        # Style rankings: 2 swimmer types × 6 styles
        with open(os.path.join(tmpdir, 'swimmer_type_style_rankings.csv'), 'w') as f:
            f.write('swimmer_type_id,style_id,rank\n')
            # Type 1: NR(1)=1st, HE(2)=2nd, SS(5)=3rd, A(4)=4th, TD(3)=5th, DIA(6)=6th
            f.write('1,1,1\n1,2,2\n1,5,3\n1,4,4\n1,3,5\n1,6,6\n')
            # Type 2: HE(2)=1st, TD(3)=2nd, SS(5)=3rd, A(4)=4th, NR(1)=5th, DIA(6)=6th
            f.write('2,2,1\n2,3,2\n2,5,3\n2,4,4\n2,1,5\n2,6,6\n')

        yield tmpdir


@pytest.fixture
def incomplete_source_dir():
    """Create a temp directory with incomplete ranking CSVs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Missing color rank for type 1, color 4
        with open(os.path.join(tmpdir, 'swimmer_type_color_rankings.csv'), 'w') as f:
            f.write('swimmer_type_id,color_id,rank\n')
            f.write('1,1,1\n1,2,2\n1,3,3\n')  # Missing color 4

        with open(os.path.join(tmpdir, 'swimmer_type_style_rankings.csv'), 'w') as f:
            f.write('swimmer_type_id,style_id,rank\n')
            f.write('1,1,1\n1,2,2\n1,5,3\n1,4,4\n1,3,5\n1,6,6\n')

        yield tmpdir


class TestRankingLoader:

    def test_load_color_rankings(self, valid_source_dir):
        loader = RankingLoader(valid_source_dir)
        color_rankings, _ = loader.load_all()

        # Type 1 ranks Blue as #1
        assert color_rankings[(1, 1)] == 1
        # Type 1 ranks Gold as #4
        assert color_rankings[(1, 4)] == 4
        # Type 2 ranks Green as #1
        assert color_rankings[(2, 3)] == 1

    def test_load_style_rankings(self, valid_source_dir):
        loader = RankingLoader(valid_source_dir)
        _, style_rankings = loader.load_all()

        # Type 1 ranks NR as #1
        assert style_rankings[(1, 1)] == 1
        # Type 1 ranks DIA as #6
        assert style_rankings[(1, 6)] == 6
        # Type 2 ranks HE as #1
        assert style_rankings[(2, 2)] == 1

    def test_correct_count(self, valid_source_dir):
        loader = RankingLoader(valid_source_dir)
        color_rankings, style_rankings = loader.load_all()

        assert len(color_rankings) == 8   # 2 types × 4 colors
        assert len(style_rankings) == 12  # 2 types × 6 styles

    def test_incomplete_data_raises(self, incomplete_source_dir):
        loader = RankingLoader(incomplete_source_dir)
        with pytest.raises(ValueError, match="Ranking validation failed"):
            loader.load_all()

    def test_missing_file_raises(self):
        loader = RankingLoader('/nonexistent/path')
        with pytest.raises(FileNotFoundError):
            loader.load_all()
