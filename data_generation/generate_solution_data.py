"""
Generate denormalized solution data for the swim matching system.

This script reads the normalized CSVs from data/ and produces
denormalized (joined) CSVs in data_solution/:
  - instructors.csv: instructors joined with personality colors and teaching styles
  - swimmers.csv: swimmers joined with swimmer types
  - classes.csv: copied as-is from data/
"""

import csv
import os
import shutil


def get_source_dir():
    """Return path to the data/source/ directory (reference/business data)."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'source')


def get_generated_dir():
    """Return path to the data/generated/ directory (synthetic data)."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'generated')


def get_solution_dir():
    """Create and return path to the data_solution/ directory."""
    solution_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data_solution')
    os.makedirs(solution_dir, exist_ok=True)
    return solution_dir


def read_csv_as_dict(filepath, key_column):
    """Read a CSV file and return a dict keyed by the given column."""
    lookup = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lookup[row[key_column]] = dict(row)
    return lookup


def generate_denormalized_instructors(source_dir, generated_dir, solution_dir):
    """
    Join instructors with personality_colors and instructor_styles,
    then write to data_solution/instructors.csv.
    """
    colors = read_csv_as_dict(os.path.join(source_dir, 'personality_colors.csv'), 'color_id')
    styles = read_csv_as_dict(os.path.join(source_dir, 'instructor_styles.csv'), 'style_id')

    instructors_path = os.path.join(generated_dir, 'instructors.csv')
    output_path = os.path.join(solution_dir, 'instructors.csv')

    fieldnames = [
        'instructor_id', 'first_name', 'last_name',
        'primary_color_id', 'primary_color_name', 'primary_color_traits',
        'secondary_color_id', 'secondary_color_name', 'secondary_color_traits',
        'primary_style_id', 'primary_style_code', 'primary_style_name',
        'primary_style_traits', 'primary_style_expertise_area',
        'secondary_style_id', 'secondary_style_code', 'secondary_style_name',
        'secondary_style_traits', 'secondary_style_expertise_area',
        'is_team_captain', 'can_teach_NL', 'can_teach_babies',
        'can_teach_adults', 'can_teach_adapted',
    ]

    rows = []
    with open(instructors_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pri_color = colors[row['primary_color_id']]
            sec_color = colors[row['secondary_color_id']]
            pri_style = styles[row['primary_style_id']]
            sec_style = styles[row['secondary_style_id']]

            rows.append({
                'instructor_id': row['instructor_id'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'primary_color_id': row['primary_color_id'],
                'primary_color_name': pri_color['color_name'],
                'primary_color_traits': pri_color['traits'],
                'secondary_color_id': row['secondary_color_id'],
                'secondary_color_name': sec_color['color_name'],
                'secondary_color_traits': sec_color['traits'],
                'primary_style_id': row['primary_style_id'],
                'primary_style_code': pri_style['style_code'],
                'primary_style_name': pri_style['style_name'],
                'primary_style_traits': pri_style['traits'],
                'primary_style_expertise_area': pri_style['expertise_area'],
                'secondary_style_id': row['secondary_style_id'],
                'secondary_style_code': sec_style['style_code'],
                'secondary_style_name': sec_style['style_name'],
                'secondary_style_traits': sec_style['traits'],
                'secondary_style_expertise_area': sec_style['expertise_area'],
                'is_team_captain': row['is_team_captain'],
                'can_teach_NL': row['can_teach_NL'],
                'can_teach_babies': row['can_teach_babies'],
                'can_teach_adults': row['can_teach_adults'],
                'can_teach_adapted': row['can_teach_adapted'],
            })

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Written {len(rows)} instructors to data_solution/instructors.csv")
    return len(rows)


def generate_denormalized_swimmers(source_dir, generated_dir, solution_dir):
    """
    Join swimmers with swimmer_types,
    then write to data_solution/swimmers.csv.
    """
    swimmer_types = read_csv_as_dict(
        os.path.join(source_dir, 'swimmer_types.csv'), 'swimmer_type_id'
    )

    swimmers_path = os.path.join(generated_dir, 'swimmers.csv')
    output_path = os.path.join(solution_dir, 'swimmers.csv')

    fieldnames = [
        'swimmer_id', 'first_name', 'last_name',
        'swimmer_type_id', 'swimmer_type_name',
        'skill_level', 'age', 'has_special_needs', 'notes', 'pair_id',
    ]

    rows = []
    with open(swimmers_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stype = swimmer_types[row['swimmer_type_id']]

            rows.append({
                'swimmer_id': row['swimmer_id'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'swimmer_type_id': row['swimmer_type_id'],
                'swimmer_type_name': stype['swimmer_type_name'],
                'skill_level': row['skill_level'],
                'age': row['age'],
                'has_special_needs': row['has_special_needs'],
                'notes': row['notes'],
                'pair_id': row['pair_id'],
            })

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Written {len(rows)} swimmers to data_solution/swimmers.csv")
    return len(rows)


def copy_classes(generated_dir, solution_dir):
    """Copy classes.csv as-is to data_solution/."""
    src = os.path.join(generated_dir, 'classes.csv')
    dst = os.path.join(solution_dir, 'classes.csv')
    shutil.copy2(src, dst)
    print("  Copied classes.csv to data_solution/classes.csv")


def main():
    """Generate all denormalized solution data files."""
    source_dir = get_source_dir()
    generated_dir = get_generated_dir()
    solution_dir = get_solution_dir()

    print("Generating denormalized solution data...")
    generate_denormalized_instructors(source_dir, generated_dir, solution_dir)
    generate_denormalized_swimmers(source_dir, generated_dir, solution_dir)
    copy_classes(generated_dir, solution_dir)
    print("Done.")


if __name__ == '__main__':
    main()
