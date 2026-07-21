"""
Generate the tracked synthetic demonstration dataset in examples/demo/.

Produces schema-compatible, fully synthetic stand-ins for the private
operational files that are NOT tracked in git:

    data/source/instructors.csv  ->  examples/demo/database/instructors.csv
    data/source/pairings.csv     ->  examples/demo/database/pairings.csv

Never writes into data/source/. Deterministic for a given seed so the
committed fixtures can be reproduced exactly.

Usage:
    python data_generation/generate_demo_source.py             # seed 42
    python data_generation/generate_demo_source.py --seed 99
"""

import argparse
import csv
import os
import random

from faker import Faker

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(REPO_ROOT, "examples", "demo", "database")

COLOR_IDS = [1, 2, 3, 4]
STYLE_IDS = [1, 2, 3, 4, 5, 6]
SESSIONS = ["2024 Fall", "2025 Winter", "2025 Spring", "2025 Summer"]
LEVELS = [f"RSS {n}" for n in range(1, 13)] + ["Adapted", "Adult Learn to Swim"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
TIMES = ["9:00 am", "10:30 am", "4:00 pm", "4:30 pm", "5:00 pm", "6:15 pm"]


def _derived_profile_fields(row: dict) -> tuple[int, int]:
    """Mirror backend.db._derived_profile_fields for the four profile columns."""
    fields = (
        "primary_color_id",
        "secondary_color_id",
        "primary_style_id",
        "secondary_style_id",
    )
    filled = [row[f] not in (None, "") for f in fields]
    if all(filled):
        return 0, 0
    return 1, (2 if any(filled) else 1)


def generate_instructors(rng: random.Random, fake: Faker, count: int) -> list[dict]:
    rows = []
    for instructor_id in range(1, count + 1):
        profile_kind = rng.choices(["full", "partial", "empty"], weights=[80, 10, 10])[0]
        if profile_kind == "empty":
            colors = styles = [None, None]
        else:
            colors = rng.sample(COLOR_IDS, 2)
            styles = rng.sample(STYLE_IDS, 2)
            if profile_kind == "partial":
                colors[1] = None
        row = {
            "instructor_id": instructor_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "primary_color_id": colors[0],
            "secondary_color_id": colors[1],
            "primary_style_id": styles[0],
            "secondary_style_id": styles[1],
            "is_team_captain": 1 if rng.random() < 0.1 else 0,
            "can_teach_babies": 1 if rng.random() < 0.4 else 0,
            "can_teach_adults": 1 if rng.random() < 0.4 else 0,
            "can_teach_adapted": 1 if rng.random() < 0.25 else 0,
        }
        used_default, profile_source = _derived_profile_fields(row)
        row["used_default_profile"] = used_default
        row["profile_source"] = profile_source
        rows.append(row)
    return rows


def generate_pairings(
    rng: random.Random, instructors: list[dict], swimmer_count: int
) -> list[dict]:
    rows = []
    class_id = 5000
    for session in SESSIONS:
        enrolled = rng.sample(
            range(1001, 1001 + swimmer_count), k=int(swimmer_count * 0.6)
        )
        for swimmer_id in enrolled:
            instructor = rng.choice(instructors)
            class_id += 1
            level = rng.choice(LEVELS)
            class_name = f"{level} {rng.choice(DAYS)} {rng.choice(TIMES)}"
            rows.append(
                {
                    "swimmer_id": swimmer_id,
                    "class_id": class_id,
                    "instructor_id": instructor["instructor_id"],
                    "class_name": class_name,
                    "session": session,
                    "status": "archived" if session != SESSIONS[-1] else "active",
                }
            )
    return rows


def _write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})


def main(seed: int = 42) -> None:
    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)
    os.makedirs(DEMO_DIR, exist_ok=True)

    instructors = generate_instructors(rng, fake, count=25)
    pairings = generate_pairings(rng, instructors, swimmer_count=300)

    _write_csv(os.path.join(DEMO_DIR, "instructors.csv"), instructors)
    _write_csv(os.path.join(DEMO_DIR, "pairings.csv"), pairings)
    print(
        f"Wrote {len(instructors)} instructors and {len(pairings)} pairings "
        f"to {DEMO_DIR} (seed={seed})"
    )


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the synthetic examples/demo dataset"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    main(seed=parser.parse_args().seed)


if __name__ == "__main__":
    cli()
