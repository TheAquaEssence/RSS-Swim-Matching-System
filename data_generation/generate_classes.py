"""
Generate class template and swimmer data for the swim matching system.

This script:
1. Reads instructors.csv (all instructors assumed available)
2. Creates one class per instructor for a single evening time slot
3. Generates swimmers with some pre-paired (satisfying HC-4)
4. Ensures the number of swimmer sets (individuals + pairs) == number of classes

Per README: All instructors are assumed available for the time slot.
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


def read_instructors(data_dir):
    """Read all instructors from instructors.csv."""
    filepath = os.path.join(data_dir, 'instructors.csv')
    instructors = []

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            instructors.append(dict(row))

    return instructors


def check_hc4_compatible(swimmer1, swimmer2):
    """
    Check if two swimmers satisfy HC-4 pairing compatibility.

    HC-4: At most 1 RSS level apart and at most 2 years of age apart.
    """
    level_diff = abs(int(swimmer1['skill_level']) - int(swimmer2['skill_level']))
    age_diff = abs(float(swimmer1['age']) - float(swimmer2['age']))

    return level_diff <= 1 and age_diff <= 2.0


def generate_swimmers_for_slot(num_classes, seed: int = 42):
    """
    Generate swimmers for the time slot such that swimmer sets == num_classes.

    A swimmer set is either an individual swimmer or a pair sharing a pair_id.
    After generation and pairing, excess unpaired swimmers are trimmed so that
    the total number of swimmer sets exactly matches num_classes.

    Args:
        num_classes: Number of classes (determines number of swimmer sets)
        seed: Seed for random generation (default: 42)
    """
    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)

    # Number of swimmers: between N and 2×N
    min_swimmers = num_classes
    max_swimmers = 2 * num_classes
    num_swimmers = random.randint(min_swimmers, max_swimmers)

    # Swimmer type weights
    swimmer_type_pool = [1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 6, 7, 7]

    # Notes pool
    notes_pool = [
        "nervous around deep water",
        "parent requests patient instructor",
        "ADHD - needs adapted instructor",
        "autism - routine and structure important",
        "working on back float",
        "had a bad experience previously",
        "very social, loves to chat",
        "needs encouragement"
    ]

    swimmers = []

    for i in range(1, num_swimmers + 1):
        first_name = fake.first_name()
        last_name = fake.last_name()
        swimmer_type_id = random.choice(swimmer_type_pool)
        skill_level = random.randint(1, 12)

        # Generate age based on skill level
        if skill_level <= 3:
            age = round(random.uniform(0.5, 5.0), 1)
        elif skill_level <= 8:
            age = round(random.uniform(5.0, 14.0), 1)
        else:
            age = round(random.uniform(14.0, 18.0), 1)

        # Notes: ~30% of swimmers have notes
        notes = ""
        if random.random() < 0.3:
            notes = random.choice(notes_pool)

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
            'pair_id': '',  # Will be assigned below for pairs
        })

    # Create some pre-pairs (about 1/6 of swimmers will be in pairs)
    unpaired_indices = list(range(len(swimmers)))
    random.shuffle(unpaired_indices)

    pair_id = 1
    paired_count = 0
    target_pairs = max(1, num_swimmers // 6)

    i = 0
    while i < len(unpaired_indices) - 1 and paired_count < target_pairs:
        idx1 = unpaired_indices[i]
        swimmer1 = swimmers[idx1]

        # Try to find a compatible partner
        for j in range(i + 1, len(unpaired_indices)):
            idx2 = unpaired_indices[j]
            swimmer2 = swimmers[idx2]

            if check_hc4_compatible(swimmer1, swimmer2):
                # Found a compatible pair
                swimmers[idx1]['pair_id'] = pair_id
                swimmers[idx2]['pair_id'] = pair_id
                pair_id += 1
                paired_count += 1

                # Remove both from unpaired list
                unpaired_indices.remove(idx1)
                unpaired_indices.remove(idx2)
                break
        else:
            # No compatible partner found, move to next
            i += 1
            continue

    # Ensure swimmer sets == num_classes
    # Each pair counts as 1 set (2 swimmers), each unpaired swimmer counts as 1 set
    # So: swimmer_sets = total_swimmers - paired_count
    num_swimmer_sets = len(swimmers) - paired_count

    if num_swimmer_sets > num_classes:
        excess = num_swimmer_sets - num_classes
        # Remove excess unpaired swimmers (those without a pair_id)
        unpaired_indices = [i for i, s in enumerate(swimmers) if s['pair_id'] == '']
        indices_to_remove = unpaired_indices[-excess:]
        for idx in sorted(indices_to_remove, reverse=True):
            swimmers.pop(idx)
        # Renumber swimmer_ids sequentially
        for i, s in enumerate(swimmers):
            s['swimmer_id'] = i + 1

    num_swimmers = len(swimmers)
    print(f"  Generated {num_swimmers} swimmers with {paired_count} pre-paired groups "
          f"({num_swimmers - paired_count} swimmer sets)")

    return swimmers


def generate_classes(data_dir, seed: int = 42):
    """
    Generate classes.csv and swimmers.csv for a single time slot.

    All instructors from instructors.csv are assumed available.
    Creates one class per instructor.

    Args:
        data_dir: Directory to write output files
        seed: Seed for random generation (default: 42)
    """
    # Read instructors (all assumed available)
    instructors = read_instructors(data_dir)
    num_classes = len(instructors)

    if num_classes == 0:
        print("Error: No instructors found in instructors.csv")
        return 0

    # Use a fixed evening time slot
    day = "Wednesday"
    start_time = "18:30"
    end_time = "19:00"

    print(f"  Time slot: {day} {start_time}-{end_time}")
    print(f"  Number of classes: {num_classes}")

    # Generate swimmers for this slot
    swimmers = generate_swimmers_for_slot(num_classes, seed=seed)

    # Write swimmers.csv
    swimmers_path = os.path.join(data_dir, 'swimmers.csv')
    with open(swimmers_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'swimmer_id', 'first_name', 'last_name',
            'swimmer_type_id', 'skill_level', 'age',
            'has_special_needs', 'notes', 'pair_id'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(swimmers)

    print(f"  Generated swimmers.csv: {len(swimmers)} swimmers")

    # Create classes - one per instructor, using real partner export format
    classes = []
    for i, inst in enumerate(instructors):
        last_initial = inst['last_name'][0] if inst.get('last_name') else '?'
        instructor_name = f"{inst['first_name']} {last_initial}."
        classes.append({
            'class_id': i + 1,
            'start_time': '06:30 PM',
            'end_time': '07:00 PM',
            'day_of_week': 'Wed',
            'location': 'Pool A',
            'class_name': f"RSS {i + 1} {day} {start_time} 2:1",
            'session': '2026 Spring',
            'instructor_name': instructor_name,
            'open': 2,
            'size': 2,
            'status': 'Active',
            'cat_1': 'RSS Spring',
            'cat_2': '',
            'start_date': '2026-04-27',
            'end_date': '2026-06-15',
        })

    # Write classes.csv
    classes_path = os.path.join(data_dir, 'classes.csv')
    with open(classes_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'class_id', 'start_time', 'end_time', 'day_of_week',
            'location', 'class_name', 'session', 'instructor_name',
            'open', 'size', 'status', 'cat_1', 'cat_2',
            'start_date', 'end_date',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(classes)

    return len(classes)


def main(seed: int = 42):
    """
    Generate class template and swimmer data.

    Args:
        seed: Seed for random generation (default: 42)
    """
    data_dir = ensure_data_dir()
    count = generate_classes(data_dir, seed=seed)

    print(f"Generated classes.csv: {count} classes")
    return count


if __name__ == '__main__':
    main()
