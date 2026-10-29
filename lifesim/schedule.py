from datetime import date
from .config import ScheduleModel

WEEKDAYS = {
    'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6
}

import calendar

# Precompute days in month. 0 is a placeholder for month 0.
DAYS_IN_MONTH = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

def get_last_day_of_month(year: int, month: int) -> int:
    ndays = DAYS_IN_MONTH[month]
    if month == 2 and calendar.isleap(year):
        return 29
    return ndays

def should_fire(schedule: ScheduleModel, current_date: date, start_date: date) -> bool:
    if schedule.monthly is not None:
        last_day_of_month = get_last_day_of_month(current_date.year, current_date.month)
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

        last_day_of_month = get_last_day_of_month(current_date.year, month)
        target_day = min(day, last_day_of_month)

        if current_date.month == month and current_date.day == target_day:
            return True

    if schedule.once is not None:
        try:
            once_date = date.fromisoformat(schedule.once)
            if current_date == once_date:
                return True
        except ValueError:
            pass

    return False
