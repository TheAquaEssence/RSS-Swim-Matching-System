from backend import server


def test_default_instructor_safety_qualifications_fail_closed():
    profile = server.make_default_settings()["default_instructor_profile"]

    assert profile["can_teach_NL"] is True
    assert profile["can_teach_babies"] is False
    assert profile["can_teach_adults"] is False
    assert profile["can_teach_adapted"] is False


def test_provisioned_demo_history_is_ignored_with_external_inputs(
    monkeypatch, tmp_path
):
    app_root = tmp_path / "app"
    app_data_root = tmp_path / "user-data"
    matching_dir = app_root / "examples" / "demo" / "matching"
    matching_dir.mkdir(parents=True)
    provisioned_history = (
        app_data_root
        / "resources"
        / "examples"
        / "demo"
        / "matching"
        / "historical_pairings.csv"
    )
    provisioned_history.parent.mkdir(parents=True)
    provisioned_history.write_text("swimmer_id,instructor_id\n", encoding="utf-8")
    external_classes = tmp_path / "imports" / "classes.csv"
    external_classes.parent.mkdir()
    external_classes.write_text("class_id\n1\n", encoding="utf-8")

    monkeypatch.setattr(server, "APP_ROOT", app_root)
    monkeypatch.setattr(server, "APP_DATA_ROOT", app_data_root)
    monkeypatch.setitem(
        server.DEFAULT_FILE_PATHS,
        "historical_pairings",
        provisioned_history.as_posix(),
    )
    settings = server.make_default_settings()
    settings["last_selected_files"]["classes"] = external_classes.as_posix()

    assert server._should_default_to_empty_historical(settings)
