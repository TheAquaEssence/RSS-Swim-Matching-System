"""
Generate instructor data for the swim matching system.
Creates 7-9 instructors with personality colors, teaching styles, and capability flags.

All generated instructors are assumed to be available for the time slot being matched.
"""

import csv
import os
import random
from faker import Faker


def ensure_data_dir():
    """Create generated data directory if it doesn't exist."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'generated')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def generate_instructors(data_dir, seed: int = 100, num_instructors: int | None = None):
    """
    Generate instructors.csv with either a requested count or the default 7-9.

    All instructors are assumed available for the time slot.
    Per README Section 2.3.1: "The number of classes in the file is between 7 and 9"

    Args:
        data_dir: Directory to write output file
        seed: Seed for random generation (default: 100)
        num_instructors: Exact instructor count to generate. If None,
            defaults to the legacy 7-9 random range.
    """
    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)

    # Preserve legacy behavior unless an exact count is requested.
    if num_instructors is None:
        num_instructors = random.randint(7, 9)

    if num_instructors <= 0:
        raise ValueError("num_instructors must be positive")

    # Available colors: Blue (1), Orange (2), Green (3), Gold (4)
    color_ids = [1, 2, 3, 4]

    # Available styles: NR (1), HE (2), TD (3), A (4), SS (5), DIA (6)
    style_ids = [1, 2, 3, 4, 5, 6]

    instructors = []

    # About 20% should be team captains
    num_team_captains = max(1, num_instructors // 5)

    for i in range(1, num_instructors + 1):
        first_name = fake.first_name()
        last_name = fake.last_name()

        is_team_captain = i <= num_team_captains

        # Select primary and secondary colors (must be different)
        primary_color = random.choice(color_ids)
        secondary_color = random.choice([c for c in color_ids if c != primary_color])

        # Select primary and secondary styles (must be different)
        primary_style = random.choice(style_ids)
        # Secondary style excludes primary and DIA (6) can only be primary
        available_secondary = [s for s in style_ids if s != primary_style and s != 6]
        secondary_style = random.choice(available_secondary)

        # Set capability flags
        if is_team_captain:
            # Team captains must have all capabilities
            can_teach_NL = True
            can_teach_babies = True
            can_teach_adults = True
            can_teach_adapted = True
        else:
            can_teach_NL = random.choice([True, False])
            can_teach_babies = random.choice([True, False])
            can_teach_adults = random.choice([True, False])
            can_teach_adapted = random.choice([True, False])

        instructors.append({
            'instructor_id': i,
            'first_name': first_name,
            'last_name': last_name,
            'primary_color_id': primary_color,
            'secondary_color_id': secondary_color,
            'primary_style_id': primary_style,
            'secondary_style_id': secondary_style,
            'is_team_captain': is_team_captain,
            'can_teach_NL': can_teach_NL,
            'can_teach_babies': can_teach_babies,
            'can_teach_adults': can_teach_adults,
            'can_teach_adapted': can_teach_adapted,
        })

    filepath = os.path.join(data_dir, 'instructors.csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'instructor_id', 'first_name', 'last_name',
            'primary_color_id', 'secondary_color_id',
            'primary_style_id', 'secondary_style_id',
            'is_team_captain', 'can_teach_NL',
            'can_teach_babies', 'can_teach_adults', 'can_teach_adapted'
        ])
        writer.writeheader()
        writer.writerows(instructors)

    return len(instructors)


def main(seed: int = 100):
    """
    Generate instructor data.

    Args:
        seed: Seed for random generation (default: 100)
    """
    data_dir = ensure_data_dir()
    count = generate_instructors(data_dir, seed=seed)

    print(f"Generated instructors.csv: {count} instructors")
    return count


if __name__ == '__main__':
    main()
