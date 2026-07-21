"""
Generate swimmer data for the swim matching system.
Creates a pool of swimmers with types, skill levels, and special needs flags.
The pair_id column is initially NULL - pairing is done by generate_classes.py.
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


def generate_swimmers(data_dir, num_swimmers=30):
    """
    Generate swimmers.csv - a pool of swimmers.

    The pair_id column is left empty (NULL) here. Pre-pairing is handled
    by generate_classes.py which creates the final filtered swimmers.csv
    with pair assignments for the selected time slot.
    """
    fake = Faker()
    Faker.seed(42)  # For reproducible names

    # Swimmer types: 1-7
    # Use weighted distribution - Nervous/New (1) and Slow Progress (6) are more common
    swimmer_type_weights = {
        1: 3,  # The Nervous/New (more common)
        2: 2,  # The Fearless/Energetic
        3: 2,  # The Hard Worker
        4: 2,  # The Socialite/Talker
        5: 2,  # The Natural
        6: 3,  # The Slow Progress (more common)
        7: 2,  # Not Used to No
    }

    # Create a weighted list for random selection
    swimmer_type_pool = []
    for type_id, weight in swimmer_type_weights.items():
        swimmer_type_pool.extend([type_id] * weight)

    # Pool of realistic notes
    notes_pool = [
        "nervous around deep water",
        "parent requests patient instructor",
        "ADHD - needs adapted instructor",
        "autism - routine and structure important",
        "working on back float",
        "had a bad experience previously",
        "parent does not want instructor X",
        "very social, loves to chat",
        "needs encouragement"
    ]

    swimmers = []

    for i in range(1, num_swimmers + 1):
        # Generate fake first and last names (swimmers are children/teens)
        first_name = fake.first_name()
        last_name = fake.last_name()

        # Select swimmer type from weighted pool
        swimmer_type_id = random.choice(swimmer_type_pool)

        # Skill level: RSS 1-12
        skill_level = random.randint(1, 12)

        # Generate age based on skill level (float with 1 decimal)
        if skill_level <= 3:
            # RSS 1-3: babies/toddlers/young children (0.5 to 5.0 years)
            age = round(random.uniform(0.5, 5.0), 1)
        elif skill_level <= 8:
            # RSS 4-8: older children (5.0 to 14.0 years)
            age = round(random.uniform(5.0, 14.0), 1)
        else:
            # RSS 9-12: teens (14.0 to 18.0 years)
            age = round(random.uniform(14.0, 18.0), 1)

        # Notes: ~40% of swimmers have notes
        notes = ""
        if random.random() < 0.4:
            notes = random.choice(notes_pool)

        # Special needs: True only if notes contain "ADHD" or "autism"
        has_special_needs = "ADHD" in notes or "autism" in notes

        swimmers.append({
            'swimmer_id': i,
            'first_name': first_name,
            'last_name': last_name,
            'swimmer_type_id': swimmer_type_id,
            'skill_level': skill_level,
            'age': age,
            'has_special_needs': has_special_needs,
            'notes': notes,
            'pair_id': '',  # NULL - pairing handled by generate_classes.py
        })

    filepath = os.path.join(data_dir, 'swimmers.csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'swimmer_id', 'first_name', 'last_name',
            'swimmer_type_id', 'skill_level', 'age',
            'has_special_needs', 'notes', 'pair_id'
        ])
        writer.writeheader()
        writer.writerows(swimmers)

    return len(swimmers)


def main():
    """Generate swimmer data."""
    random.seed(42)

    data_dir = ensure_data_dir()
    count = generate_swimmers(data_dir)

    print(f"Generated swimmers.csv: {count} swimmers")
    return count


if __name__ == '__main__':
    main()
