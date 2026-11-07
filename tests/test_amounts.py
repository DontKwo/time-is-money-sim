from datetime import date
import numpy as np
from lifesim.amounts import resolve_flow_amount_cents, get_amount
from lifesim.macro import convert_currency
from lifesim.config import (
    AmountModel,
    FlowModel,
    FlowStepModel,
    ScheduleModel,
    HourlyPayEstimate,
    DateRangeSpec,
)


def test_step_override_transition_and_reversion() -> None:
    flow = FlowModel(
        name="Rent",
        type="expense",
        schedule=ScheduleModel(monthly=1),
        amount=AmountModel(fixed=1200.0),
        steps=[
            FlowStepModel(
                start=date(2026, 6, 1),
                end=date(2026, 8, 31),
                amount=AmountModel(fixed=1500.0),
            )
        ],
    )
    sim_start = date(2026, 1, 1)

    # Before step start
    cents_may = resolve_flow_amount_cents(flow, date(2026, 5, 1), sim_start)
    assert cents_may == 120_000

    # During step
    cents_june = resolve_flow_amount_cents(flow, date(2026, 6, 1), sim_start)
    assert cents_june == 150_000
    cents_aug = resolve_flow_amount_cents(flow, date(2026, 8, 31), sim_start)
    assert cents_aug == 150_000

    # After step end -> reverts to base
    cents_sep = resolve_flow_amount_cents(flow, date(2026, 9, 1), sim_start)
    assert cents_sep == 120_000


def test_anniversary_escalation() -> None:
    flow = FlowModel(
        name="Rent",
        type="expense",
        schedule=ScheduleModel(start=date(2026, 3, 1), monthly=1),
        amount=AmountModel(fixed=1000.0),
        annual_escalation_rate=0.05,
        escalation_mode="anniversary",
    )
    sim_start = date(2026, 1, 1)

    # Year 0: before anniversary
    cents_feb = resolve_flow_amount_cents(flow, date(2027, 2, 28), sim_start)
    assert cents_feb == 100_000

    # Year 1: on/after anniversary (2027-03-01)
    cents_mar = resolve_flow_amount_cents(flow, date(2027, 3, 1), sim_start)
    assert cents_mar == 105_000


def test_hourly_pay_overtime_calculation() -> None:
    amount = AmountModel(
        hourly_pay=HourlyPayEstimate(
            hourly_rate=30.0,
            hours_per_period=45.0,
            overtime_threshold=40.0,
            overtime_multiplier=1.5,
        )
    )
    cents = get_amount(amount)
    # 40 * 30 + 5 * 45 = 1200 + 225 = 1425.00 -> 142500 cents
    assert cents == 142_500


def test_date_range_spread_evenly() -> None:
    flow = FlowModel(
        name="Vacation",
        type="expense",
        schedule=ScheduleModel(
            date_range=DateRangeSpec(
                start=date(2026, 7, 1),
                end=date(2026, 7, 3),
                mode="spread_evenly",
            )
        ),
        amount=AmountModel(fixed=1000.0),
        date_range_total=True,
    )
    sim_start = date(2026, 1, 1)

    day1_cents = resolve_flow_amount_cents(flow, date(2026, 7, 1), sim_start)
    day2_cents = resolve_flow_amount_cents(flow, date(2026, 7, 2), sim_start)
    day3_cents = resolve_flow_amount_cents(flow, date(2026, 7, 3), sim_start)

    assert day1_cents == 33_334
    assert day2_cents == 33_333
    assert day3_cents == 33_333
    assert day1_cents + day2_cents + day3_cents == 100_000


def test_convert_currency() -> None:
    # Same currency
    assert convert_currency(100_00, "USD", "USD", 1.2) == 100_00

    # Different currency
    assert convert_currency(100_00, "USD", "EUR", 0.85) == 85_00
    assert convert_currency(100_00, "EUR", "USD", 1.18) == 118_00

    # Rounding check
    assert convert_currency(100, "USD", "EUR", 0.855) == 86
