from pathlib import Path

import pandas as pd

from data_generation.generate_sized import generate_sized_dataset


class TestGenerateSizedDataset:
    def test_small_creates_expected_files(self, tmp_path):
        generate_sized_dataset(
            num_instructors=5,
            seed=42,
            output_dir=str(tmp_path),
            source_dir="data/source",
        )

        assert (tmp_path / "swimmers.csv").exists()
        assert (tmp_path / "instructors.csv").exists()
        assert (tmp_path / "classes.csv").exists()
        assert (tmp_path / "historical_pairings.csv").exists()

    def test_instructor_count_matches_requested(self, tmp_path):
        generate_sized_dataset(
            num_instructors=10,
            seed=42,
            output_dir=str(tmp_path),
            source_dir="data/source",
        )

        df = pd.read_csv(tmp_path / "instructors.csv")
        assert len(df) == 10

    def test_swimmer_count_between_n_and_2n(self, tmp_path):
        generate_sized_dataset(
            num_instructors=20,
            seed=42,
            output_dir=str(tmp_path),
            source_dir="data/source",
        )

        instructors = pd.read_csv(tmp_path / "instructors.csv")
        swimmers = pd.read_csv(tmp_path / "swimmers.csv")
        n = len(instructors)

        assert n <= len(swimmers) <= 2 * n

    def test_seed_reproducibility(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        generate_sized_dataset(
            num_instructors=8,
            seed=99,
            output_dir=str(dir_a),
            source_dir="data/source",
        )
        generate_sized_dataset(
            num_instructors=8,
            seed=99,
            output_dir=str(dir_b),
            source_dir="data/source",
        )

        for filename in ("swimmers.csv", "instructors.csv", "classes.csv"):
            df_a = pd.read_csv(dir_a / filename)
            df_b = pd.read_csv(dir_b / filename)
            pd.testing.assert_frame_equal(df_a, df_b)

    def test_different_seeds_produce_different_data(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        generate_sized_dataset(
            num_instructors=8,
            seed=1,
            output_dir=str(dir_a),
            source_dir="data/source",
        )
        generate_sized_dataset(
            num_instructors=8,
            seed=2,
            output_dir=str(dir_b),
            source_dir="data/source",
        )

        df_a = pd.read_csv(dir_a / "swimmers.csv")
        df_b = pd.read_csv(dir_b / "swimmers.csv")

        assert not df_a["first_name"].equals(df_b["first_name"])

    def test_rejects_non_positive_instructor_count(self, tmp_path):
        output_dir = Path(tmp_path)

        try:
            generate_sized_dataset(
                num_instructors=0,
                seed=42,
                output_dir=str(output_dir),
                source_dir="data/source",
            )
        except ValueError as exc:
            assert "num_instructors" in str(exc)
        else:
            raise AssertionError("Expected ValueError for num_instructors=0")

