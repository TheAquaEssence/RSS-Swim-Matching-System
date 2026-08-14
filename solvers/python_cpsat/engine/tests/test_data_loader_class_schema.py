from pathlib import Path

import pytest

from solvers.python_cpsat.engine.data_loader import DataLoader as CpsatDataLoader


def _workspace_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "examples" / "demo" / "matching").is_dir():
            return parent
    raise RuntimeError("workspace root not found")


@pytest.fixture
def app_sample_paths():
    sample_dir = _workspace_root() / "examples" / "demo" / "matching"
    return {
        "swimmers": sample_dir / "swimmers.csv",
        "instructors": sample_dir / "instructors.csv",
        "historical": sample_dir / "historical_pairings.csv",
        "source": _workspace_root() / "data" / "source",
    }


@pytest.mark.parametrize(
    "loader_cls",
    [CpsatDataLoader],
)
def test_from_files_accepts_generated_classes_with_instructor_id(
    tmp_path, app_sample_paths, loader_cls
):
    classes_path = tmp_path / "classes.csv"
    classes_path.write_text(
        "class_id,day_of_week,start_time,end_time,instructor_id,swimmer_1_id,swimmer_2_id\n"
        "1,Wednesday,18:30,19:00,1,,\n",
        encoding="utf-8",
    )

    loader = loader_cls.from_files(
        classes_path=classes_path,
        swimmers_path=app_sample_paths["swimmers"],
        instructors_path=app_sample_paths["instructors"],
        historical_path=app_sample_paths["historical"],
        source_dir=app_sample_paths["source"],
    )

    assert loader.classes[1].instructor_id == "1"
    assert loader.classes[1].day_of_week == "Wednesday"
    assert loader.classes[1].start_time == "18:30"


@pytest.mark.parametrize(
    "loader_cls",
    [CpsatDataLoader],
)
def test_from_files_accepts_partner_export_classes_with_instructor_name(
    tmp_path, app_sample_paths, loader_cls
):
    classes_path = tmp_path / "classes.csv"
    classes_path.write_text(
        "class_id,start_time,end_time,day_of_week,instructor_name\n"
        "1,07:30 AM,08:00 AM,Mon,Danielle J.\n",
        encoding="utf-8",
    )

    loader = loader_cls.from_files(
        classes_path=classes_path,
        swimmers_path=app_sample_paths["swimmers"],
        instructors_path=app_sample_paths["instructors"],
        historical_path=app_sample_paths["historical"],
        source_dir=app_sample_paths["source"],
    )

    assert loader.classes[1].instructor_id == "1"
    assert loader.classes[1].day_of_week == "Monday"
    assert loader.classes[1].start_time == "07:30"


def test_cpsat_from_files_keeps_fixed_roster_mode_when_roster_columns_exist_but_are_blank(
    tmp_path, app_sample_paths
):
    classes_path = tmp_path / "classes.csv"
    classes_path.write_text(
        "class_id,day_of_week,start_time,end_time,instructor_name,swimmer_1_id,swimmer_2_id\n"
        "1,Mon,07:30 AM,08:00 AM,Danielle J.,,\n",
        encoding="utf-8",
    )

    loader = CpsatDataLoader.from_files(
        classes_path=classes_path,
        swimmers_path=app_sample_paths["swimmers"],
        instructors_path=app_sample_paths["instructors"],
        historical_path=app_sample_paths["historical"],
        source_dir=app_sample_paths["source"],
    )

    assert loader.uses_fixed_class_rosters() is True
    individuals, pairs = loader.get_fixed_class_entities()
    assert individuals == []
    assert pairs == []


def test_from_files_preserves_duplicate_class_id_instructor_assignments_and_zeroes(
    tmp_path, app_sample_paths
):
    classes_path = tmp_path / "classes.csv"
    classes_path.write_text(
        "class_id,day_of_week,start_time,end_time,instructor_id\n"
        "00021,Monday,16:00,16:30,1\n"
        "00021,Monday,16:00,16:30,2\n",
        encoding="utf-8",
    )

    loader = CpsatDataLoader.from_files(
        classes_path=classes_path,
        swimmers_path=app_sample_paths["swimmers"],
        instructors_path=app_sample_paths["instructors"],
        historical_path=app_sample_paths["historical"],
        source_dir=app_sample_paths["source"],
    )

    assert len(loader.classes) == 2
    assert [
        (class_obj.class_id, class_obj.instructor_id)
        for class_obj in loader.classes.values()
    ] == [("00021", "1"), ("00021", "2")]
