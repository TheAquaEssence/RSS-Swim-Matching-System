from scripts.check_commit_attribution import REQUIRED_TRAILERS, validate_message


def test_noreply_coauthors_are_absent_or_approved_exactly_once() -> None:
    trailers = "\n".join(
        f"Co-Authored-By: {value}" for value in sorted(REQUIRED_TRAILERS)
    )

    assert validate_message(f"Initial public release\n\n{trailers}\n") == []
    assert validate_message("Trailer-free public change") == []
    assert validate_message(f"Message\n\n{trailers}\n{trailers}\n")
    assert validate_message(
        f"Message\n\n{trailers}\nCo-Authored-By: Other <other@example.com>\n"
    )
