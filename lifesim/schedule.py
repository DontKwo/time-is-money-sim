from datetime import date
from .config import ScheduleModel

WEEKDAYS = {
    'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6
}

import calendar

def should_fire(schedule: ScheduleModel, current_date: date, start_date: date) -> bool:
    if schedule.monthly is not None:
        _, last_day_of_month = calendar.monthrange(current_date.year, current_date.month)
        target_day = min(schedule.monthly, last_day_of_month)
        if current_date.day == target_day:
            return True

    if schedule.weekly is not None:
        day_str = schedule.weekly.lower()
        if day_str in WEEKDAYS:
            if current_date.weekday() == WEEKDAYS[day_str]:
                return True

    if schedule.yearly is not None:
        month = schedule.yearly.get('month')
        day = schedule.yearly.get('day')

        _, last_day_of_month = calendar.monthrange(current_date.year, month)
        target_day = min(day, last_day_of_month)

        if current_date.month == month and current_date.day == target_day:
            return True

    if schedule.once is not None:
        if not hasattr(schedule, "_once_date_parsed"):
            try:
                schedule._once_date_parsed = date.fromisoformat(schedule.once)
            except ValueError:
                schedule._once_date_parsed = None

        if schedule._once_date_parsed is not None and current_date == schedule._once_date_parsed:
            return True

    return False
