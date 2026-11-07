from datetime import date
from typing import Dict
import numpy as np
import pytest
from lifesim.config import (
    ScheduleModel,
    EveryNWeeksSpec,
    EveryNMonthsSpec,
    NthWeekdaySpec,
    QuarterlySpec,
    DateRangeSpec,
)
from lifesim.schedule import (
    build_fire_counts,
    resolve_day_of_month,
    shift_date,
    is_us_bank_holiday,
    should_fire,
)


def test_resolve_day_of_month() -> None:
    assert resolve_day_of_month(2024, 2, "last") == 29
    assert resolve_day_of_month(2025, 2, -1) == 28
    assert resolve_day_of_month(2026, 4, 31) == 30
    assert resolve_day_of_month(2026, 4, 15) == 15


def test_schedule_daily_and_every_n_days() -> None:
    sim_start = date(2026, 1, 1)
    sim_end = date(2026, 1, 31)

    daily_schedule = ScheduleModel(daily=True)
    counts_daily = build_fire_counts(daily_schedule, sim_start, sim_end)
    assert len(counts_daily) == 31
    assert sum(counts_daily.values()) == 31

    interval_schedule = ScheduleModel(every_n_days=14, anchor=date(2026, 1, 1))
    counts_interval = build_fire_counts(interval_schedule, sim_start, sim_end)
    expected_dates = {date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29)}
    assert set(counts_interval.keys()) == expected_dates


def test_schedule_biweekly_across_year_boundary() -> None:
    # 2025-12-26 is a Friday. Next biweekly Friday is 2026-01-09.
    schedule = ScheduleModel(biweekly="fri", anchor=date(2025, 12, 26))
    sim_start = date(2025, 12, 20)
    sim_end = date(2026, 1, 31)
    counts = build_fire_counts(schedule, sim_start, sim_end)
    expected_fridays = {
        date(2025, 12, 26),
        date(2026, 1, 9),
        date(2026, 1, 23),
    }
    assert set(counts.keys()) == expected_fridays


def test_schedule_weekly_list() -> None:
    schedule = ScheduleModel(weekly=["mon", "wed", "fri"])
    sim_start = date(2026, 1, 5)  # Monday
    sim_end = date(2026, 1, 11)   # Sunday
    counts = build_fire_counts(schedule, sim_start, sim_end)
    expected = {date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 9)}
    assert set(counts.keys()) == expected


def test_schedule_semimonthly_and_month_end_clamping() -> None:
    schedule = ScheduleModel(semimonthly=[15, "last"])
    counts_leap = build_fire_counts(schedule, date(2024, 2, 1), date(2024, 2, 29))
    assert set(counts_leap.keys()) == {date(2024, 2, 15), date(2024, 2, 29)}

    counts_non_leap = build_fire_counts(schedule, date(2025, 2, 1), date(2025, 2, 28))
    assert set(counts_non_leap.keys()) == {date(2025, 2, 15), date(2025, 2, 28)}

    # Clamping list [30, 31] in 28-day February fires once on Feb 28
    schedule_clamp = ScheduleModel(monthly=[30, 31])
    counts_clamp = build_fire_counts(schedule_clamp, date(2025, 2, 1), date(2025, 2, 28))
    assert set(counts_clamp.keys()) == {date(2025, 2, 28)}
    assert counts_clamp[date(2025, 2, 28)] == 1


def test_schedule_nth_weekday() -> None:
    # 2nd Tuesday of January 2026 is Jan 13
    schedule_2nd_tue = ScheduleModel(nth_weekday=NthWeekdaySpec(nth=2, weekday="tue"))
    counts_tue = build_fire_counts(schedule_2nd_tue, date(2026, 1, 1), date(2026, 1, 31))
    assert set(counts_tue.keys()) == {date(2026, 1, 13)}

    # Last Friday of January 2026 is Jan 30
    schedule_last_fri = ScheduleModel(nth_weekday=NthWeekdaySpec(nth=-1, weekday="fri"))
    counts_fri = build_fire_counts(schedule_last_fri, date(2026, 1, 1), date(2026, 1, 31))
    assert set(counts_fri.keys()) == {date(2026, 1, 30)}


def test_schedule_quarterly_and_every_n_months() -> None:
    quarterly = ScheduleModel(quarterly=QuarterlySpec(day=15, months=[1, 4, 7, 10]))
    counts_q = build_fire_counts(quarterly, date(2026, 1, 1), date(2026, 12, 31))
    expected_q = {
        date(2026, 1, 15),
        date(2026, 4, 15),
        date(2026, 7, 15),
        date(2026, 10, 15),
    }
    assert set(counts_q.keys()) == expected_q

    semiannual = ScheduleModel(every_n_months=EveryNMonthsSpec(n=6, day=15, anchor_year=2026, anchor_month=1))
    counts_semi = build_fire_counts(semiannual, date(2026, 1, 1), date(2026, 12, 31))
    assert set(counts_semi.keys()) == {date(2026, 1, 15), date(2026, 7, 15)}


def test_weekend_rule_and_us_holidays() -> None:
    # 2026-03-01 is Sunday. Shifting "before" yields Friday 2026-02-27.
    shifted_before = shift_date(date(2026, 3, 1), "before", False)
    assert shifted_before == date(2026, 2, 27)

    # 2026-08-01 is Saturday. Shifting "after" yields Monday 2026-08-03.
    shifted_after = shift_date(date(2026, 8, 1), "after", False)
    assert shifted_after == date(2026, 8, 3)

    # July 4 2026 is Saturday -> observed holiday is Friday July 3
    assert is_us_bank_holiday(date(2026, 7, 3)) == True
    shifted_holiday = shift_date(date(2026, 7, 4), "before", True)
    assert shifted_holiday == date(2026, 7, 2)  # skips Friday July 3 holiday


def test_schedule_stochastic_distributions() -> None:
    sim_start = date(2026, 1, 1)
    sim_end = date(2026, 12, 31)
    test_rng = np.random.default_rng(12345)

    schedule_prob = ScheduleModel(daily_prob=0.5)
    counts_prob = build_fire_counts(schedule_prob, sim_start, sim_end, test_rng)
    total_prob_fires = sum(counts_prob.values())
    # ~365 * 0.5 = ~182 fires
    assert 150 <= total_prob_fires <= 215

    # 2 events per week with Friday/Saturday weighting
    weights = {"fri": 3.0, "sat": 3.0, "sun": 1.0}
    schedule_poisson = ScheduleModel(
        random_per_week=2.0,
        weekday_weights=weights,
    )
    counts_poisson = build_fire_counts(schedule_poisson, sim_start, sim_end, test_rng)
    total_poisson_fires = sum(counts_poisson.values())
    # ~52 weeks * 2 = ~104 events
    assert 80 <= total_poisson_fires <= 130


def test_schedule_date_range_and_weekdays_only() -> None:
    range_schedule = ScheduleModel(
        date_range=DateRangeSpec(
            start=date(2026, 6, 1),
            end=date(2026, 6, 5),
            mode="daily",
        ),
        weekdays_only=True,
    )
    counts = build_fire_counts(range_schedule, date(2026, 5, 1), date(2026, 6, 30))
    expected = {
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 3),
        date(2026, 6, 4),
        date(2026, 6, 5),
    }
    assert set(counts.keys()) == expected

