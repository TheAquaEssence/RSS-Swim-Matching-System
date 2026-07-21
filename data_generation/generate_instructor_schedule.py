"""
Generate instructor schedule data for the swim matching system.
Each instructor works 2-4 days per week with shift ranges (e.g., 4:00pm-9:00pm).
"""

import csv
import os
import random
from datetime import time


def ensure_data_dir():
    """Create generated data directory if it doesn't exist."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'generated')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def read_instructors(data_dir):
    """Read instructor IDs from instructors.csv"""
    filepath = os.path.join(data_dir, 'instructors.csv')
    instructor_ids = []

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            instructor_ids.append(int(row['instructor_id']))

    return instructor_ids


def time_to_str(t):
    """Convert time object to string in HH:MM format."""
    return t.strftime('%H:%M')


def generate_schedule(data_dir):
    """Generate instructor_schedule.csv"""
    instructor_ids = read_instructors(data_dir)

    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Define possible shift patterns
    # Morning shifts (8am start)
    morning_shifts = [
        (time(8, 0), time(12, 0)),   # 8am-12pm
        (time(8, 0), time(13, 0)),   # 8am-1pm
        (time(9, 0), time(13, 0)),   # 9am-1pm
    ]

    # Afternoon/Evening shifts (most classes happen 4:30 PM onward)
    evening_shifts = [
        (time(16, 0), time(20, 0)),  # 4pm-8pm
        (time(16, 0), time(21, 0)),  # 4pm-9pm
        (time(16, 30), time(20, 30)),  # 4:30pm-8:30pm
        (time(16, 30), time(21, 0)),  # 4:30pm-9pm
        (time(17, 0), time(21, 0)),  # 5pm-9pm
    ]

    # All-day shifts (for some variety)
    allday_shifts = [
        (time(8, 0), time(21, 0)),   # 8am-9pm
        (time(10, 0), time(20, 0)),  # 10am-8pm
    ]

    schedules = []

    for instructor_id in instructor_ids:
        # Each instructor works 2-4 days per week
        num_days = random.randint(2, 4)

        # Randomly select which days they work
        work_days = random.sample(days_of_week, num_days)

        # Determine if this instructor leans morning, evening, or mixed
        # Weighted toward evening since most classes happen 4:30 PM onward
        preference = random.choices(
            ['morning', 'evening', 'mixed'],
            weights=[1, 4, 2],  # 57% evening, 29% mixed, 14% morning
            k=1
        )[0]

        for day in work_days:
            # Select shift based on preference
            if preference == 'morning':
                shift_start, shift_end = random.choice(morning_shifts)
            elif preference == 'evening':
                shift_start, shift_end = random.choice(evening_shifts)
            else:  # mixed
                all_shifts = morning_shifts + evening_shifts + allday_shifts
                shift_start, shift_end = random.choice(all_shifts)

            schedules.append({
                'instructor_id': instructor_id,
                'day_of_week': day,
                'shift_start': time_to_str(shift_start),
                'shift_end': time_to_str(shift_end),
            })

    filepath = os.path.join(data_dir, 'instructor_schedule.csv')
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['instructor_id', 'day_of_week', 'shift_start', 'shift_end'])
        writer.writeheader()
        writer.writerows(schedules)

    return len(schedules)


def main():
    """Generate instructor schedule data."""
    random.seed(42)

    data_dir = ensure_data_dir()
    count = generate_schedule(data_dir)

    print(f"Generated instructor_schedule.csv: {count} schedule entries")
    return count


if __name__ == '__main__':
    main()
