"""
Generate historical pairing data for the swim matching system.
About 60% of swimmers have a previous instructor from the last session (2024-Winter).
"""

import csv
import os
import random


def ensure_data_dir():
    """Create generated data directory if it doesn't exist."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'generated')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def read_swimmers(data_dir):
    """Read swimmer IDs from swimmers.csv"""
    filepath = os.path.join(data_dir, 'swimmers.csv')
    swimmer_ids = []

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            swimmer_ids.append(int(row['swimmer_id']))

    return swimmer_ids


def read_instructors(data_dir):
    """Read instructor IDs from instructors.csv"""
    filepath = os.path.join(data_dir, 'instructors.csv')
    instructor_ids = []

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            instructor_ids.append(int(row['instructor_id']))

    return instructor_ids


def generate_historical_pairings(data_dir):
    """Generate historical_pairings.csv"""
    swimmer_ids = read_swimmers(data_dir)
    instructor_ids = read_instructors(data_dir)

    # About 60% of swimmers have a previous pairing
    num_pairings = int(len(swimmer_ids) * 0.6)

    # Randomly select which swimmers have previous pairings
    swimmers_with_history = random.sample(swimmer_ids, num_pairings)

    pairings = []

    for swimmer_id in swimmers_with_history:
        # Each swimmer has at most one past instructor
        instructor_id = random.choice(instructor_ids)

        # num_sessions: random integer 1-4 (tracks consecutive sessions together)
        num_sessions = random.randint(1, 4)

        pairings.append({
            'swimmer_id': swimmer_id,
            'instructor_id': instructor_id,
            'session': '2024-Winter',
            'num_sessions': num_sessions,
        })

    filepath = os.path.join(data_dir, 'historical_pairings.csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['swimmer_id', 'instructor_id', 'session', 'num_sessions'])
        writer.writeheader()
        writer.writerows(pairings)

    return len(pairings)


def main(seed: int = 42):
    """
    Generate historical pairing data.

    Args:
        seed: Seed for random generation (default: 42)
    """
    random.seed(seed)

    data_dir = ensure_data_dir()
    count = generate_historical_pairings(data_dir)

    print(f"Generated historical_pairings.csv: {count} pairings")
    return count


if __name__ == '__main__':
    main()
