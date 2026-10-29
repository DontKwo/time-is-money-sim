from datetime import date
from .config import ScheduleModel

WEEKDAYS = {
    'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6
}

def should_fire(schedule: ScheduleModel, current_date: date, start_date: date) -> bool:
    if schedule.monthly is not None:
        return current_date.day == schedule.monthly
    if schedule.weekly is not None:
        day_str = schedule.weekly.lower()
        if day_str in WEEKDAYS:
            return current_date.weekday() == WEEKDAYS[day_str]
    if schedule.yearly is not None:
        month = schedule.yearly.get('month')
        day = schedule.yearly.get('day')
        return current_date.month == month and current_date.day == day
    if schedule.once is not None:
        # Assuming once is a string in YYYY-MM-DD format
        once_date = date.fromisoformat(schedule.once)
        return current_date == once_date
    return False
