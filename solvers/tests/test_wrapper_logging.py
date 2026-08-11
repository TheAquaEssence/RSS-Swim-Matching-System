import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


from core.aqua_logging import reset_logging_state


WORKSPACE = Path(__file__).resolve().parents[2]


def _load_wrapper(wrapper_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, wrapper_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read_records(log_root: Path, component: str):
    component_dir = log_root / component
    records = []
    for path in sorted(component_dir.glob("*.jsonl*")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _request_payload(job_id: str, tmp_path: Path):
    swimmers = tmp_path / "swimmers.csv"
    instructors = tmp_path / "instructors.csv"
    swimmers.write_text("swimmer_id,first_name,last_name\n1,Alice,Smith\n", encoding="utf-8")
    instructors.write_text("instructor_id,first_name,last_name\n10,Coach,One\n", encoding="utf-8")
    return {
        "job_id": job_id,
        "app_root": str(tmp_path),
        "data": {
            "classes": "",
            "swimmers": str(swimmers),
            "instructors": str(instructors),
            "historical_pairings": "",
            "reference": {},
        },
        "config": {"enable_continuity": True},
    }


def test_python_cpsat_wrapper_logs_success_and_failure(tmp_path, monkeypatch):
    success_log_root = tmp_path / "logs"
    monkeypatch.setenv("AQUA_LOG_DIR", str(success_log_root))
    reset_logging_state()

    module = _load_wrapper(
        WORKSPACE / "solvers/python_cpsat/solver_wrapper.py",
        "test_python_cpsat_wrapper_logging",
    )

    swimmer = SimpleNamespace(swimmer_id=1, name="Alice", skill_level=3, age=7.0, has_special_needs=False)
    instructor = SimpleNamespace(
        instructor_id=10,
        name="Coach One",
        can_teach_adapted=True,
        can_teach_babies=True,
        can_teach_adults=True,
    )
    loader = SimpleNamespace(
        classes={},
        historical_pairings=[],
        get_all_swimmers=lambda: [swimmer],
        get_all_instructors=lambda: [instructor],
        uses_fixed_class_rosters=lambda: False,
    )

    request_path = tmp_path / "request_python.json"
    result_path = tmp_path / "result_python.json"
    request_path.write_text(json.dumps(_request_payload("job_python", tmp_path)), encoding="utf-8")

    monkeypatch.setattr(module.DataLoader, "from_files", lambda **kwargs: loader)
    monkeypatch.setattr(module, "RankingLoader", lambda source_dir: SimpleNamespace(load_all=lambda: ({}, {})))
    monkeypatch.setattr(module, "CompatibilityScorer", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "continuity_pass", lambda swimmers, instructors, historical: ([], swimmers, instructors, set(), {}))
    monkeypatch.setattr(
        module,
        "compatibility_pass",
        lambda unmatched_swimmers, available_instructors, scorer, loader_arg, **kwargs: [
            {
                "type": "individual",
                "swimmer_id": swimmer.swimmer_id,
                "swimmer": swimmer,
                "instructor_id": instructor.instructor_id,
                "instructor_name": instructor.name,
                "confidence": 88.0,
                "compatibility_score": 91.0,
                "reason_summary": "Compatibility",
                "match_type": "compatibility",
                "explanation": "Compatibility",
            }
        ],
    )
    monkeypatch.setattr(module, "generate_explanations", lambda matches, *args, **kwargs: matches)
    monkeypatch.setattr(module, "generate_output_csv", lambda matches, classes, path, **kwargs: Path(path).write_text("ok", encoding="utf-8"))
    monkeypatch.setattr(module, "generate_summary_report", lambda *args, **kwargs: "summary")
    monkeypatch.setattr(module, "generate_pdf_report", None)
    validated_matches = []
    monkeypatch.setattr(
        module,
        "validate_hard_constraints",
        lambda matches, *args, **kwargs: validated_matches.extend(matches),
    )

    import core.profiles.profile_reader as profile_reader

    monkeypatch.setattr(
        profile_reader,
        "write_profiles_json",
        lambda **kwargs: Path(kwargs["output_path"]).write_text("{}", encoding="utf-8"),
    )
    monkeypatch.setattr(module.sys, "argv", ["solver_wrapper", str(request_path), str(result_path)])

    module.main()

    success_records = _read_records(success_log_root, "solver.python_cpsat")
    assert any(record["event"] == "wrapper_started" and record["job_id"] == "job_python" for record in success_records)
    assert any(record["event"] == "wrapper_completed" and record["job_id"] == "job_python" for record in success_records)
    assert any(record["event"] == "wrapper_result_written" and record["job_id"] == "job_python" for record in success_records)
    assert json.loads(result_path.read_text(encoding="utf-8"))["ok"] is True
    assert len(validated_matches) == 1
    assert validated_matches[0]["swimmer_id"] == 1

    reset_logging_state()
    failure_log_root = tmp_path / "logs_failure"
    monkeypatch.setenv("AQUA_LOG_DIR", str(failure_log_root))
    request_path.write_text(json.dumps(_request_payload("job_python_fail", tmp_path)), encoding="utf-8")
    monkeypatch.setattr(module, "compatibility_pass", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(module.sys, "argv", ["solver_wrapper", str(request_path), str(result_path)])

    module.main()

    failure_records = _read_records(failure_log_root, "solver.python_cpsat")
    failed = next(record for record in failure_records if record["event"] == "wrapper_failed")
    assert failed["job_id"] == "job_python_fail"
    assert failed["exception_type"] == "RuntimeError"
    assert json.loads(result_path.read_text(encoding="utf-8"))["ok"] is False
