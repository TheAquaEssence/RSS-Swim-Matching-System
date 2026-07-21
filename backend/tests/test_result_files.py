from backend.services.result_files import expose_result_files


def test_expose_result_files_replaces_solver_paths_with_job_urls(tmp_path):
    job_dir = tmp_path / "job_0123456789abcdef0123456789abcdef"
    job_dir.mkdir()
    (job_dir / "classes_filled.csv").write_text("class_id\n", encoding="utf-8")
    (job_dir / "matching_report.pdf").write_bytes(b"%PDF-test")
    original = {
        "ok": True,
        "result_files": {
            "classes_filled": "../../private/jobs/classes_filled.csv",
            "pdf": r"C:\\private\\jobs\\matching_report.pdf",
            "unknown": "secrets.txt",
        },
    }

    exposed = expose_result_files(original, job_dir)

    base = "/jobs/job_0123456789abcdef0123456789abcdef"
    assert exposed["result_files"] == {
        "classes_filled": f"{base}/classes_filled.csv",
        "pdf": f"{base}/matching_report.pdf",
        "filled_classes_export": f"{base}/classes_filled.csv",
    }
    assert original["result_files"]["pdf"].startswith("C:")


def test_expose_result_files_omits_missing_and_invalid_entries(tmp_path):
    job_dir = tmp_path / "job_empty"
    job_dir.mkdir()

    assert expose_result_files({"result_files": {"pdf": "anything"}}, job_dir)[
        "result_files"
    ] == {}
    assert expose_result_files({"result_files": "not-an-object"}, job_dir)[
        "result_files"
    ] == {}
