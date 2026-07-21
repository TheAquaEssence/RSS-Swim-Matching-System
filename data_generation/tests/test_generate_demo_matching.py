from data_generation import generate_demo_matching


def test_demo_matching_seed_provenance(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(generate_demo_matching, "DEMO_DIR", tmp_path)
    monkeypatch.setattr(
        generate_demo_matching,
        "generate_instructors",
        lambda path, seed: calls.append(("instructors", path, seed)),
    )
    monkeypatch.setattr(
        generate_demo_matching,
        "generate_classes",
        lambda path, seed: calls.append(("classes", path, seed)),
    )
    monkeypatch.setattr(
        generate_demo_matching,
        "generate_historical_pairings",
        lambda path: calls.append(("historical", path)),
    )
    monkeypatch.setattr(
        generate_demo_matching.random,
        "seed",
        lambda seed: calls.append(("historical_seed", seed)),
    )

    generate_demo_matching.main(seed=42)

    expected_path = str(tmp_path)
    assert calls == [
        ("instructors", expected_path, 42),
        ("classes", expected_path, 1042),
        ("historical_seed", 42),
        ("historical", expected_path),
    ]


def test_committed_demo_matches_documented_seed(monkeypatch, tmp_path):
    committed_dir = (
        generate_demo_matching.REPO_ROOT / "examples" / "demo" / "matching"
    )
    generated_dir = tmp_path / "matching"
    monkeypatch.setattr(generate_demo_matching, "DEMO_DIR", generated_dir)

    generate_demo_matching.main(seed=42)

    for name in (
        "classes.csv",
        "swimmers.csv",
        "instructors.csv",
        "historical_pairings.csv",
    ):
        # Git normalizes the committed CSVs to LF while the csv module writes
        # CRLF, so compare with line endings normalized.
        generated = (generated_dir / name).read_bytes().replace(b"\r\n", b"\n")
        committed = (committed_dir / name).read_bytes().replace(b"\r\n", b"\n")
        assert generated == committed
