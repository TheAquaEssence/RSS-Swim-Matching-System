"""Reference generation must not overwrite existing canonical files by default."""
from data_generation.generate_reference_data import (
    generate_personality_colors,
    generate_swimmer_types,
)


def test_existing_reference_file_is_kept_by_default(tmp_path):
    target = tmp_path / "personality_colors.csv"
    target.write_text("color_id,color_name,traits\n99,Custom,Edited by hand\n", encoding="utf-8")

    generate_personality_colors(str(tmp_path))

    assert "Custom" in target.read_text(encoding="utf-8"), "existing file must be untouched"


def test_force_overwrites_existing_reference_file(tmp_path):
    target = tmp_path / "personality_colors.csv"
    target.write_text("color_id,color_name,traits\n99,Custom,Edited by hand\n", encoding="utf-8")

    generate_personality_colors(str(tmp_path), force=True)

    content = target.read_text(encoding="utf-8")
    assert "Custom" not in content
    assert "Blue" in content


def test_missing_reference_file_is_written(tmp_path):
    generate_swimmer_types(str(tmp_path))
    content = (tmp_path / "swimmer_types.csv").read_text(encoding="utf-8")
    assert content.startswith("swimmer_type_id,swimmer_type_name")
    assert "Non-Response / Unknown" in content
