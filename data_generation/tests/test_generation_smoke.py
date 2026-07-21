"""Smoke tests for the data_generation pipeline (D5).

Runs the generator chain (swimmers → instructors → classes → historical
pairings) into a temp directory and checks the outputs are structurally
valid for the solver: files exist, required columns are present, and basic
invariants (ID references, age range, capability flags) hold.
"""

import pandas as pd
import pytest

from data_generation.generate_swimmers import generate_swimmers
from data_generation.generate_instructors import generate_instructors
from data_generation.generate_classes import generate_classes
from data_generation.generate_historical_pairings import generate_historical_pairings


@pytest.fixture(scope="module")
def generated_dir(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("generated"))
    generate_swimmers(d, num_swimmers=20)
    generate_instructors(d, seed=1, num_instructors=5)
    generate_classes(d, seed=1)  # rewrites swimmers.csv filtered to the chosen slot
    generate_historical_pairings(d)
    return d


def test_all_output_files_created(generated_dir):
    for name in ("swimmers.csv", "instructors.csv", "classes.csv", "historical_pairings.csv"):
        df = pd.read_csv(f"{generated_dir}/{name}")
        assert len(df) > 0, f"{name} has no data rows"


def test_swimmers_schema_and_invariants(generated_dir):
    df = pd.read_csv(f"{generated_dir}/swimmers.csv")
    required = {
        "swimmer_id", "first_name", "last_name", "swimmer_type_id",
        "skill_level", "age", "has_special_needs", "notes", "pair_id",
    }
    assert required.issubset(df.columns)
    assert df["swimmer_id"].is_unique
    assert df["age"].between(0, 100).all()
    assert df["skill_level"].between(1, 12).all()  # RSS levels 1-12


def test_instructors_schema_and_count(generated_dir):
    df = pd.read_csv(f"{generated_dir}/instructors.csv")
    required = {
        "instructor_id", "first_name", "last_name",
        "primary_color_id", "secondary_color_id",
        "primary_style_id", "secondary_style_id",
        "is_team_captain", "can_teach_NL",
        "can_teach_babies", "can_teach_adults", "can_teach_adapted",
    }
    assert required.issubset(df.columns)
    assert len(df) == 5
    assert df["instructor_id"].is_unique


def test_classes_reference_generated_instructors(generated_dir):
    # classes.csv is written in the partner format: instructors are referenced
    # by display name ("First L."), not by instructor_id.
    classes = pd.read_csv(f"{generated_dir}/classes.csv")
    instructors = pd.read_csv(f"{generated_dir}/instructors.csv")
    assert {"class_id", "instructor_name", "session", "start_time", "end_time"}.issubset(classes.columns)
    assert classes["class_id"].is_unique
    known_names = {
        f"{row.first_name} {str(row.last_name)[:1]}."
        for row in instructors.itertuples()
    }
    assert set(classes["instructor_name"].dropna()).issubset(known_names)


def test_historical_pairings_reference_generated_ids(generated_dir):
    pairings = pd.read_csv(f"{generated_dir}/historical_pairings.csv")
    swimmers = pd.read_csv(f"{generated_dir}/swimmers.csv")
    instructors = pd.read_csv(f"{generated_dir}/instructors.csv")
    assert {"swimmer_id", "instructor_id", "session", "num_sessions"}.issubset(pairings.columns)
    assert set(pairings["swimmer_id"]).issubset(set(swimmers["swimmer_id"]))
    assert set(pairings["instructor_id"]).issubset(set(instructors["instructor_id"]))


def test_paired_swimmers_satisfy_hc4(generated_dir):
    """Generated pre-pairs must respect HC-4: ≤1 RSS level and ≤2 years apart."""
    df = pd.read_csv(f"{generated_dir}/swimmers.csv")
    paired = df[df["pair_id"].notna() & (df["pair_id"].astype(str).str.strip() != "")]
    for _, group in paired.groupby("pair_id"):
        if len(group) < 2:
            continue
        assert group["skill_level"].max() - group["skill_level"].min() <= 1
        assert group["age"].max() - group["age"].min() <= 2
