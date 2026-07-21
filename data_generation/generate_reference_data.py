"""
Generate reference data for the swim matching system.
This includes personality colors, instructor styles, swimmer types, and ranking-based
preference tables for color and style compatibility.
"""

import argparse
import csv
import os
import random


NON_RESPONSE_SWIMMER_TYPE_ID = 8
NON_RESPONSE_SWIMMER_TYPE_NAME = "Non-Response / Unknown"
NON_RESPONSE_COLOR_ORDER = [1, 4, 3, 2]
NON_RESPONSE_STYLE_ORDER = [2, 3, 4, 5, 1, 6]


def ensure_data_dir():
    """Create source data directory if it doesn't exist."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'source')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _write_reference_csv(filepath, fieldnames, rows, force):
    """Write a reference CSV, refusing to overwrite an existing file unless forced.

    data/source/ is the canonical (tracked) reference data; regeneration is
    rare and must be an explicit choice, not a side effect of running the
    synthetic-data pipeline. Returns True when the file was written.
    """
    if os.path.exists(filepath) and not force:
        print(f"  kept existing (use --force to overwrite): {filepath}")
        return False
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return True


def generate_personality_colors(data_dir, force=False):
    """Generate personality_colors.csv"""
    colors = [
        {'color_id': 1, 'color_name': 'Blue', 'traits': 'Empathetic, Compassionate, Social, Caring'},
        {'color_id': 2, 'color_name': 'Orange', 'traits': 'Flexible, Fun, Open-Minded, Spontaneous'},
        {'color_id': 3, 'color_name': 'Green', 'traits': 'Logical, Calm, Analytical, Direct'},
        {'color_id': 4, 'color_name': 'Gold', 'traits': 'Organized, Structured, Efficient, Planner'},
    ]

    filepath = os.path.join(data_dir, 'personality_colors.csv')
    _write_reference_csv(filepath, ['color_id', 'color_name', 'traits'], colors, force)
    return len(colors)


def generate_instructor_styles(data_dir, force=False):
    """Generate instructor_styles.csv"""
    styles = [
        {'style_id': 1, 'style_code': 'NR', 'style_name': 'New RSS/Babies',
         'traits': 'Bubbly, Fun', 'expertise_area': 'RSS 1-5'},
        {'style_id': 2, 'style_code': 'HE', 'style_name': 'High Energy',
         'traits': 'Outgoing, Loud', 'expertise_area': 'RSS 1-5'},
        {'style_id': 3, 'style_code': 'TD', 'style_name': 'Technique Driven',
         'traits': 'Serious, Direct', 'expertise_area': 'RSS 6-12'},
        {'style_id': 4, 'style_code': 'A', 'style_name': 'Adapted',
         'traits': 'Comfortable, Authentic', 'expertise_area': 'Adapted/Adults'},
        {'style_id': 5, 'style_code': 'SS', 'style_name': 'Soft-Spoken',
         'traits': 'Calm, Trust-Building', 'expertise_area': 'Nervous Swimmers'},
        {'style_id': 6, 'style_code': 'DIA', 'style_name': 'Do-It-Alls',
         'traits': 'Knowledgeable, Experienced', 'expertise_area': 'Anything!'},
    ]

    filepath = os.path.join(data_dir, 'instructor_styles.csv')
    _write_reference_csv(filepath, ['style_id', 'style_code', 'style_name', 'traits', 'expertise_area'], styles, force)
    return len(styles)


def generate_swimmer_types(data_dir, force=False):
    """Generate swimmer_types.csv"""
    types = [
        {'swimmer_type_id': 1, 'swimmer_type_name': 'The Nervous/New'},
        {'swimmer_type_id': 2, 'swimmer_type_name': 'The Fearless/Energetic'},
        {'swimmer_type_id': 3, 'swimmer_type_name': 'The Hard Worker'},
        {'swimmer_type_id': 4, 'swimmer_type_name': 'The Socialite/Talker'},
        {'swimmer_type_id': 5, 'swimmer_type_name': 'The Natural'},
        {'swimmer_type_id': 6, 'swimmer_type_name': 'The Slow Progress'},
        {'swimmer_type_id': 7, 'swimmer_type_name': 'Not Used to No'},
        {'swimmer_type_id': NON_RESPONSE_SWIMMER_TYPE_ID, 'swimmer_type_name': NON_RESPONSE_SWIMMER_TYPE_NAME},
    ]

    filepath = os.path.join(data_dir, 'swimmer_types.csv')
    _write_reference_csv(filepath, ['swimmer_type_id', 'swimmer_type_name'], types, force)
    return len(types)


def generate_color_rankings(data_dir, force=False):
    """Generate swimmer_type_color_rankings.csv

    Each swimmer type ranks all 4 personality colors from most preferred (rank 1)
    to least preferred (rank 4). Rankings sourced from Aqua Essence domain data.
    """
    # Rankings: (swimmer_type_id, color_id, rank)
    # Colors: Blue=1, Orange=2, Green=3, Gold=4
    rankings = [
        # The Nervous/New (type 1): Blue > Orange > Green > Gold
        (1, 1, 1), (1, 2, 2), (1, 3, 3), (1, 4, 4),
        # The Fearless/Energetic (type 2): Green > Gold > Blue > Orange
        (2, 3, 1), (2, 4, 2), (2, 1, 3), (2, 2, 4),
        # The Hard Worker (type 3): Gold > Green > Blue > Orange
        (3, 4, 1), (3, 3, 2), (3, 1, 3), (3, 2, 4),
        # The Socialite/Talker (type 4): Blue > Gold > Green > Orange
        (4, 1, 1), (4, 4, 2), (4, 3, 3), (4, 2, 4),
        # The Natural (type 5): Gold > Green > Orange > Blue
        (5, 4, 1), (5, 3, 2), (5, 2, 3), (5, 1, 4),
        # The Slow Progress (type 6): Blue > Orange > Gold > Green
        (6, 1, 1), (6, 2, 2), (6, 4, 3), (6, 3, 4),
        # Not Used to No (type 7): Orange > Blue > Green > Gold
        (7, 2, 1), (7, 1, 2), (7, 3, 3), (7, 4, 4),
        # Non-Response / Unknown (type 8): Blue > Gold > Green > Orange
        *[
            (NON_RESPONSE_SWIMMER_TYPE_ID, color_id, rank)
            for rank, color_id in enumerate(NON_RESPONSE_COLOR_ORDER, start=1)
        ],
    ]

    rows = [{'swimmer_type_id': st, 'color_id': c, 'rank': r} for st, c, r in rankings]

    filepath = os.path.join(data_dir, 'swimmer_type_color_rankings.csv')
    _write_reference_csv(filepath, ['swimmer_type_id', 'color_id', 'rank'], rows, force)
    return len(rows)


def generate_style_rankings(data_dir, force=False):
    """Generate swimmer_type_style_rankings.csv

    Each swimmer type ranks all 6 teaching styles from most preferred (rank 1)
    to least preferred (rank 6). Rankings sourced from Aqua Essence domain data.
    DIA (Do-It-Alls) is ranked 6th for all types as it is handled via special
    scoring rules (universal bonus + enhanced secondary style weight).
    """
    # Rankings: (swimmer_type_id, style_id, rank)
    # Styles: NR=1, HE=2, TD=3, A=4, SS=5, DIA=6
    rankings = [
        # The Nervous/New (type 1): NR > HE > SS > A > TD > DIA
        (1, 1, 1), (1, 2, 2), (1, 5, 3), (1, 4, 4), (1, 3, 5), (1, 6, 6),
        # The Fearless/Energetic (type 2): HE > TD > SS > A > NR > DIA
        (2, 2, 1), (2, 3, 2), (2, 5, 3), (2, 4, 4), (2, 1, 5), (2, 6, 6),
        # The Hard Worker (type 3): TD > HE > SS > A > NR > DIA
        (3, 3, 1), (3, 2, 2), (3, 5, 3), (3, 4, 4), (3, 1, 5), (3, 6, 6),
        # The Socialite/Talker (type 4): TD > SS > HE > A > NR > DIA
        (4, 3, 1), (4, 5, 2), (4, 2, 3), (4, 4, 4), (4, 1, 5), (4, 6, 6),
        # The Natural (type 5): TD > SS > HE > A > NR > DIA
        (5, 3, 1), (5, 5, 2), (5, 2, 3), (5, 4, 4), (5, 1, 5), (5, 6, 6),
        # The Slow Progress (type 6): A > TD > HE > SS > NR > DIA
        (6, 4, 1), (6, 3, 2), (6, 2, 3), (6, 5, 4), (6, 1, 5), (6, 6, 6),
        # Not Used to No (type 7): A > HE > NR > TD > SS > DIA
        (7, 4, 1), (7, 2, 2), (7, 1, 3), (7, 3, 4), (7, 5, 5), (7, 6, 6),
        # Non-Response / Unknown (type 8): HE > TD > A > SS > NR > DIA
        *[
            (NON_RESPONSE_SWIMMER_TYPE_ID, style_id, rank)
            for rank, style_id in enumerate(NON_RESPONSE_STYLE_ORDER, start=1)
        ],
    ]

    rows = [{'swimmer_type_id': st, 'style_id': s, 'rank': r} for st, s, r in rankings]

    filepath = os.path.join(data_dir, 'swimmer_type_style_rankings.csv')
    _write_reference_csv(filepath, ['swimmer_type_id', 'style_id', 'rank'], rows, force)
    return len(rows)


def main(force=False):
    """Generate all reference data files.

    Existing files in data/source/ are kept unless force=True — the canonical
    reference tables must never be replaced as a side effect of data generation.
    """
    random.seed(42)

    data_dir = ensure_data_dir()

    counts = {}
    counts['personality_colors'] = generate_personality_colors(data_dir, force=force)
    counts['instructor_styles'] = generate_instructor_styles(data_dir, force=force)
    counts['swimmer_types'] = generate_swimmer_types(data_dir, force=force)
    counts['swimmer_type_color_rankings'] = generate_color_rankings(data_dir, force=force)
    counts['swimmer_type_style_rankings'] = generate_style_rankings(data_dir, force=force)

    print("Reference data processed:")
    for name, count in counts.items():
        print(f"  {name}.csv: {count} rows")

    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate reference data CSVs in data/source/')
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing reference CSVs (default: keep existing files)',
    )
    main(force=parser.parse_args().force)
