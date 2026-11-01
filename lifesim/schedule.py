import calendar
from datetime import date, timedelta
from typing import Optional, Dict, List, Union, Set
import numpy as np
from .config import ScheduleModel

WEEKDAYS: Dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6
}
WEEKDAY_NAMES: List[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def resolve_day_of_month(year: int, month: int, day_spec: Union[int, str]) -> int:
    _, last_day = calendar.monthrange(year, month)
    if day_spec == -1 or str(day_spec).lower() == "last":
        return last_day
    day_int = int(day_spec)
    return max(1, min(day_int, last_day))


def _nth_weekday_of_month(year: int, month: int, target_weekday: int, nth: int) -> date:
    _, last_day = calendar.monthrange(year, month)
    matching = [
        date(year, month, day_number)
        for day_number in range(1, last_day + 1)
        if date(year, month, day_number).weekday() == target_weekday
    ]
    if nth == -1:
        return matching[-1]
    return matching[nth - 1]


def get_us_bank_holidays(year: int) -> Set[date]:
    holidays: Set[date] = set()
    fixed_dates = [(1, 1), (6, 19), (7, 4), (11, 11), (12, 25)]
    for month, day_num in fixed_dates:
        holiday_date = date(year, month, day_num)
        if holiday_date.weekday() == 5:
            holidays.add(holiday_date - timedelta(days=1))
        elif holiday_date.weekday() == 6:
            holidays.add(holiday_date + timedelta(days=1))
        else:
            holidays.add(holiday_date)

    next_year_jan1 = date(year + 1, 1, 1)
    if next_year_jan1.weekday() == 5:
        holidays.add(date(year, 12, 31))

    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))   # MLK Jr Day: 3rd Monday in Jan
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))   # Presidents Day: 3rd Monday in Feb
    holidays.add(_nth_weekday_of_month(year, 5, 0, -1))  # Memorial Day: Last Monday in May
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))   # Labor Day: 1st Monday in Sep
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))  # Columbus Day: 2nd Monday in Oct
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving: 4th Thursday in Nov

    return holidays


def is_us_bank_holiday(check_date: date) -> bool:
    return check_date in get_us_bank_holidays(check_date.year)


def is_non_business_day(check_date: date, respect_holidays: bool) -> bool:
    return check_date.weekday() >= 5 or (respect_holidays and is_us_bank_holiday(check_date))


def shift_date(raw_date: date, weekend_rule: str, respect_holidays: bool) -> date:
    if weekend_rule == "ignore":
        return raw_date
    step_days = -1 if weekend_rule == "before" else (1 if weekend_rule == "after" else 0)
    if step_days == 0:
        return raw_date
    shifted = raw_date
    while is_non_business_day(shifted, respect_holidays):
        shifted += timedelta(days=step_days)
    return shifted


def _matches_deterministic_rule(schedule: ScheduleModel, raw_date: date, sim_start: date) -> bool:
    if schedule.daily:
        return True

    if schedule.every_n_days is not None:
        anchor_date = schedule.anchor or schedule.start or sim_start
        days_diff = (raw_date - anchor_date).days
        if days_diff >= 0 and days_diff % schedule.every_n_days == 0:
            return True

    if schedule.biweekly is not None:
        effective_anchor = schedule.anchor or schedule.start or sim_start
        anchor_monday = effective_anchor - timedelta(days=effective_anchor.weekday())
        candidate_monday = raw_date - timedelta(days=raw_date.weekday())
        weeks_elapsed = (candidate_monday - anchor_monday).days // 7
        target_weekday = WEEKDAYS[schedule.biweekly.lower()]
        anchor_satisfied = True if schedule.anchor is None else raw_date >= schedule.anchor
        if weeks_elapsed >= 0 and weeks_elapsed % 2 == 0 and raw_date.weekday() == target_weekday and anchor_satisfied:
            return True

    if schedule.every_n_weeks is not None:
        week_spec = schedule.every_n_weeks
        effective_anchor = week_spec.anchor or schedule.anchor or schedule.start or sim_start
        anchor_monday = effective_anchor - timedelta(days=effective_anchor.weekday())
        candidate_monday = raw_date - timedelta(days=raw_date.weekday())
        weeks_elapsed = (candidate_monday - anchor_monday).days // 7
        allowed_weekdays = {WEEKDAYS[item.lower()] for item in week_spec.weekdays}
        if weeks_elapsed >= 0 and weeks_elapsed % week_spec.n == 0 and raw_date.weekday() in allowed_weekdays:
            return True

    if schedule.weekly is not None:
        if isinstance(schedule.weekly, str):
            if raw_date.weekday() == WEEKDAYS[schedule.weekly.lower()]:
                return True
        elif isinstance(schedule.weekly, list):
            allowed_weekdays = {WEEKDAYS[item.lower()] for item in schedule.weekly}
            if raw_date.weekday() in allowed_weekdays:
                return True

    if schedule.semimonthly is not None:
        resolved_days = {resolve_day_of_month(raw_date.year, raw_date.month, item) for item in schedule.semimonthly}
        if raw_date.day in resolved_days:
            return True

    if schedule.monthly is not None:
        if isinstance(schedule.monthly, (int, str)):
            if raw_date.day == resolve_day_of_month(raw_date.year, raw_date.month, schedule.monthly):
                return True
        elif isinstance(schedule.monthly, list):
            resolved_days = {resolve_day_of_month(raw_date.year, raw_date.month, item) for item in schedule.monthly}
            if raw_date.day in resolved_days:
                return True

    if schedule.nth_weekday is not None:
        spec = schedule.nth_weekday
        if spec.months is None or raw_date.month in spec.months:
            target_weekday = WEEKDAYS[spec.weekday.lower()]
            _, last_day = calendar.monthrange(raw_date.year, raw_date.month)
            matching_dates = [
                date(raw_date.year, raw_date.month, day_number)
                for day_number in range(1, last_day + 1)
                if date(raw_date.year, raw_date.month, day_number).weekday() == target_weekday
            ]
            if spec.nth == -1 and matching_dates and raw_date == matching_dates[-1]:
                return True
            if 1 <= spec.nth <= len(matching_dates) and raw_date == matching_dates[spec.nth - 1]:
                return True

    if schedule.quarterly is not None:
        quarterly_spec = schedule.quarterly
        if raw_date.month in quarterly_spec.months:
            if raw_date.day == resolve_day_of_month(raw_date.year, raw_date.month, quarterly_spec.day):
                return True

    if schedule.every_n_months is not None:
        month_spec = schedule.every_n_months
        anchor_year = month_spec.anchor_year or (schedule.start or sim_start).year
        anchor_month = month_spec.anchor_month or (schedule.start or sim_start).month
        months_elapsed = (raw_date.year - anchor_year) * 12 + (raw_date.month - anchor_month)
        if months_elapsed >= 0 and months_elapsed % month_spec.n == 0:
            if raw_date.day == resolve_day_of_month(raw_date.year, raw_date.month, month_spec.day):
                return True

    if schedule.yearly is not None:
        yearly_specs = [schedule.yearly] if isinstance(schedule.yearly, dict) else schedule.yearly
        for yearly_entry in yearly_specs:
            target_month = int(yearly_entry["month"])
            if raw_date.month == target_month:
                if raw_date.day == resolve_day_of_month(raw_date.year, raw_date.month, yearly_entry["day"]):
                    return True

    if schedule.once is not None:
        once_target = schedule.once if isinstance(schedule.once, date) else date.fromisoformat(str(schedule.once))
        if raw_date == once_target:
            return True

    if schedule.dates is not None:
        if raw_date in schedule.dates:
            return True

    if schedule.date_range is not None:
        range_spec = schedule.date_range
        if range_spec.start <= raw_date <= range_spec.end:
            if range_spec.mode in ("daily", "spread_evenly"):
                return True
            if range_spec.mode == "first_day" and raw_date == range_spec.start:
                return True
            if range_spec.mode == "last_day" and raw_date == range_spec.end:
                return True

    return False


def _is_date_allowed(schedule: ScheduleModel, check_date: date) -> bool:
    if schedule.start is not None and check_date < schedule.start:
        return False
    if schedule.end is not None and check_date > schedule.end:
        return False
    for window in schedule.pause_windows:
        if window.start <= check_date <= window.end:
            return False
    if schedule.excluded_dates and check_date in schedule.excluded_dates:
        return False
    if schedule.weekdays_only and check_date.weekday() >= 5:
        return False
    if schedule.weekends_only and check_date.weekday() < 5:
        return False
    if schedule.allowed_weekdays:
        allowed = {WEEKDAYS[item.lower()] for item in schedule.allowed_weekdays}
        if check_date.weekday() not in allowed:
            return False
    return True


def build_fire_counts(
    schedule: ScheduleModel,
    sim_start: date,
    sim_end: date,
    rng: Optional[np.random.Generator] = None,
) -> Dict[date, int]:
    counts: Dict[date, int] = {}
    active_rng = rng if rng is not None else np.random.default_rng()

    # Pre-calculate active weekdays for Poisson weight normalization
    active_weekdays = [
        item for item in WEEKDAY_NAMES
        if not (schedule.weekdays_only and item in ("sat", "sun"))
        and not (schedule.weekends_only and item not in ("sat", "sun"))
        and (schedule.allowed_weekdays is None or item in schedule.allowed_weekdays)
    ]
    if schedule.weekday_weights:
        weights = [schedule.weekday_weights.get(item, 1.0) for item in active_weekdays]
        average_weight = sum(weights) / max(1, len(weights))
    else:
        average_weight = 1.0

    total_days = (sim_end - sim_start).days + 15
    for day_offset in range(-7, total_days - 7):
        candidate_date = sim_start + timedelta(days=day_offset)
        if not _is_date_allowed(schedule, candidate_date):
            continue

        if _matches_deterministic_rule(schedule, candidate_date, sim_start):
            exec_date = shift_date(candidate_date, schedule.weekend_rule, schedule.respect_us_holidays)
            if sim_start <= exec_date <= sim_end:
                counts[exec_date] = counts.get(exec_date, 0) + 1

        # Stochastic evaluations only trigger within simulation horizon
        if sim_start <= candidate_date <= sim_end:
            if schedule.daily_prob is not None:
                if float(active_rng.uniform(0.0, 1.0)) < schedule.daily_prob:
                    exec_date = shift_date(candidate_date, schedule.weekend_rule, schedule.respect_us_holidays)
                    if sim_start <= exec_date <= sim_end:
                        counts[exec_date] = counts.get(exec_date, 0) + 1

            has_poisson = (
                schedule.random_per_week is not None
                or schedule.random_per_month is not None
                or schedule.random_per_year is not None
            )
            if has_poisson:
                if schedule.random_per_week is not None:
                    base_rate = schedule.random_per_week / 7.0
                elif schedule.random_per_month is not None:
                    base_rate = schedule.random_per_month / 30.4375
                else:
                    base_rate = float(schedule.random_per_year) / 365.25

                weekday_name = WEEKDAY_NAMES[candidate_date.weekday()]
                weight_val = schedule.weekday_weights.get(weekday_name, 1.0) if schedule.weekday_weights else 1.0
                normalized_weight = weight_val / max(1e-6, average_weight)
                daily_lambda = base_rate * normalized_weight
                events_drawn = int(active_rng.poisson(daily_lambda))
                if not schedule.allow_multiple_per_day:
                    events_drawn = min(1, events_drawn)
                if events_drawn > 0:
                    exec_date = shift_date(candidate_date, schedule.weekend_rule, schedule.respect_us_holidays)
                    if sim_start <= exec_date <= sim_end:
                        counts[exec_date] = counts.get(exec_date, 0) + events_drawn

    return counts


def should_fire(schedule: ScheduleModel, current_date: date, start_date: date) -> bool:
    if not _is_date_allowed(schedule, current_date):
        return False
    return _matches_deterministic_rule(schedule, current_date, start_date)
