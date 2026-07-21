"""CLI tool to generate profiles.json from a solver request.json.

Called by the C++ backend after any solver finishes, so that profile
lookups work regardless of which solver produced the result.

Usage:
    python -m core.profiles.generate_profiles <request.json> <output_dir>
"""

import json
import sys
import traceback
from pathlib import Path

from core.aqua_logging import configure_component_logger, install_uncaught_exception_logging, with_log_context
from core.profiles.profile_reader import write_profiles_json

COMPONENT = "core.profiles.generate_profiles"


def main() -> int:
    logger = configure_component_logger(COMPONENT)
    install_uncaught_exception_logging(logger, COMPONENT)

    if len(sys.argv) < 3:
        logger.error("Invalid CLI arguments", extra={"event": "usage_error"})
        print("Usage: python -m core.profiles.generate_profiles <request.json> <output_dir>", file=sys.stderr)
        return 1

    request_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not request_path.exists():
        logger.error(
            "request.json not found",
            extra={"event": "request_missing"},
        )
        print(f"request.json not found: {request_path}", file=sys.stderr)
        return 2

    with open(request_path, encoding="utf-8") as f:
        request = json.load(f)

    job_id = request.get("job_id")

    data = request.get("data", {})
    reference = data.get("reference", {})

    # Paths in request.json are relative to the application root.
    # The backend cd's into the app root before calling this script,
    # so relative paths resolve from CWD. As a fallback, also try
    # resolving from request.json's grandparent (jobs/<id>/../../).
    def resolve(rel: str) -> Path | None:
        if not rel:
            return None
        p = Path(rel)
        if p.is_absolute():
            return p
        # Try CWD first (backend sets this)
        from_cwd = Path.cwd() / p
        if from_cwd.exists():
            return from_cwd.resolve()
        # Fallback: relative to request.json grandparent (jobs/<id>/../../)
        from_request = (request_path.parent / ".." / ".." / p).resolve()
        return from_request

    swimmers_path = resolve(data.get("swimmers", ""))
    instructors_path = resolve(data.get("instructors", ""))
    colors_path = resolve(reference.get("personality_colors", ""))
    styles_path = resolve(reference.get("instructor_styles", ""))
    types_path = resolve(reference.get("swimmer_types", ""))

    with with_log_context(job_id=job_id):
        logger.info("Profile generation started", extra={"event": "profiles_generation_started"})

        if swimmers_path is None or not swimmers_path.exists():
            logger.error(
                "Swimmers CSV not found",
                extra={"event": "profiles_input_missing", "exception": "swimmers CSV not found"},
            )
            print(f"swimmers CSV not found: {swimmers_path}", file=sys.stderr)
            return 3
        if instructors_path is None or not instructors_path.exists():
            logger.error(
                "Instructors CSV not found",
                extra={"event": "profiles_input_missing", "exception": "instructors CSV not found"},
            )
            print(f"instructors CSV not found: {instructors_path}", file=sys.stderr)
            return 3

        output_path = output_dir / "profiles.json"
        try:
            write_profiles_json(
                output_path=output_path,
                swimmers_path=swimmers_path,
                instructors_path=instructors_path,
                colors_path=colors_path if colors_path is not None and colors_path.is_file() else None,
                styles_path=styles_path if styles_path is not None and styles_path.is_file() else None,
                types_path=types_path if types_path is not None and types_path.is_file() else None,
            )
        except Exception as exc:
            logger.error(
                "Profile generation failed",
                extra={
                    "event": "profiles_generation_failed",
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "stacktrace": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                },
            )
            raise

        logger.info("Profile generation completed", extra={"event": "profiles_generation_completed"})
        return 0


if __name__ == "__main__":
    sys.exit(main())
