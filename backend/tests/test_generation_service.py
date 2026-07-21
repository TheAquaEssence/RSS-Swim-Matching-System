import json
from pathlib import Path
from unittest.mock import Mock

from backend.services.generation_service import GenerationDependencies, GenerationService


def _settings(classes: Path | None = None) -> dict:
    values = {
        "classes": str(classes) if classes else "",
        "swimmers": "",
        "instructors": "",
        "historical_pairings": "",
        "swimmer_type_color_rankings": "",
        "swimmer_type_style_rankings": "",
        "personality_colors": "",
        "instructor_styles": "",
        "swimmer_types": "",
    }
    return {
        "default_files": dict(values),
        "last_selected_files": dict(values),
        "default_instructor_profile": {},
        "use_db_instructors": False,
    }


def _dependencies(tmp_path, *, run_solver, set_last_job_dir=lambda _path: None, save_session=lambda *_a, **_k: 1):
    solver = tmp_path / "solvers" / "python_cpsat" / "solver_wrapper.py"
    solver.parent.mkdir(parents=True)
    solver.write_text("# test solver", encoding="utf-8")
    jobs = tmp_path / "jobs"
    logger = Mock()

    return GenerationDependencies(
        app_root=tmp_path,
        jobs_dir=jobs,
        solvers_dir=tmp_path / "solvers",
        logger=logger,
        generate_job_id=lambda: "job_service_test",
        resolve_from_root=lambda value: Path(value),
        sanitize_instructor_profile=lambda value: value or {},
        input_file_problem=lambda path: None if path.exists() else "missing",
        read_csv_id_set=lambda _path, _column: None,
        filter_historical_pairings=lambda text, _swimmers, _instructors: (text, 0, 0),
        should_default_to_empty_historical=lambda _settings: True,
        write_empty_historical_pairings=lambda path: path.write_text(
            "swimmer_id,instructor_id,session,num_sessions\n",
            encoding="utf-8",
        ),
        normalize_swimmers=lambda *_args: 0,
        normalize_instructors=lambda *_args: (0, []),
        build_request_json=lambda settings, job_id: json.dumps(
            {"job_id": job_id, "settings": settings}
        ),
        run_solver=run_solver,
        read_solver_result=lambda path: path.read_text(encoding="utf-8"),
        parse_solver_result=json.loads,
        annotate_non_response_flags=lambda *_args: None,
        annotate_default_instructor_flags=lambda *_args: None,
        db_count_instructors=lambda: 0,
        db_export_instructors_csv=lambda: "",
        db_load_historical_csv=lambda **_kwargs: (
            "swimmer_id,instructor_id,session,num_sessions\n"
        ),
        db_save_session=save_session,
        set_last_job_dir=set_last_job_dir,
    )


def test_generation_service_reports_missing_input_without_fastapi(tmp_path):
    missing_classes = tmp_path / "missing.csv"
    deps = _dependencies(tmp_path, run_solver=lambda *_args: None)

    result = GenerationService(deps).generate(_settings(missing_classes))

    assert result.status_code == 400
    assert result.payload["error_kind"] == "missing_input_file"
    assert result.job_id == "job_service_test"


def test_generation_service_runs_solver_persists_job_and_returns_payload(tmp_path):
    classes = tmp_path / "classes.csv"
    classes.write_text("class_id\n1\n", encoding="utf-8")
    last_jobs: list[str] = []
    saved_sessions: list[tuple[list[dict], str]] = []

    def run_solver(_solver, _request, result_path):
        result_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "result_files": {"classes_filled": "classes_filled.csv"},
                    "summary": {},
                    "matches": [],
                    "unassigned": [],
                }
            ),
            encoding="utf-8",
        )
        (result_path.parent / "profiles.json").write_text("{}", encoding="utf-8")
        (result_path.parent / "classes_filled.csv").write_text(
            "class_id\n1\n", encoding="utf-8"
        )

    def save_session(matches, *, label):
        saved_sessions.append((matches, label))
        return 1

    deps = _dependencies(
        tmp_path,
        run_solver=run_solver,
        set_last_job_dir=last_jobs.append,
        save_session=save_session,
    )

    result = GenerationService(deps).generate(
        _settings(classes),
        request_id="request-service-test",
    )

    assert result.status_code == 200
    assert result.payload["ok"] is True
    assert result.payload["result_files"] == {
        "classes_filled": "/jobs/job_service_test/classes_filled.csv",
        "filled_classes_export": "/jobs/job_service_test/classes_filled.csv",
    }
    assert result.job_id == "job_service_test"
    assert last_jobs == [str(tmp_path / "jobs" / "job_service_test")]
    assert saved_sessions and saved_sessions[0][0] == []
    assert (tmp_path / "jobs" / "job_service_test" / "request.json").is_file()
