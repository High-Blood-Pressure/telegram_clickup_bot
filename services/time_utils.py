from typing import Optional

def parse_time_input(time_str: str) -> Optional[int]:
    try:
        total_minutes = 0

        if 'h' in time_str:
            hours_part = time_str.split('h')[0]
            hours = float(hours_part)
            total_minutes += hours * 60

        if 'm' in time_str:
            minutes_part = time_str.split('m')[0]
            if 'h' in minutes_part:
                minutes_part = minutes_part.split('h')[-1]
            minutes = float(minutes_part)
            total_minutes += minutes

        if 'h' not in time_str and 'm' not in time_str:
            total_minutes = float(time_str)

        return int(total_minutes * 60 * 1000)
    except ValueError:
        return None