import math
from datetime import date
from typing import Optional, Dict
import numpy as np
from .config import AmountModel, FlowModel


def _sample_base_dollars(amount: AmountModel, active_rng: np.random.Generator) -> float:
    if amount.fixed is not None:
        return amount.fixed

    if amount.normal is not None and len(amount.normal) == 2:
        return float(active_rng.normal(amount.normal[0], amount.normal[1]))

    if amount.uniform is not None and len(amount.uniform) == 2:
        return float(active_rng.uniform(amount.uniform[0], amount.uniform[1]))

    if amount.lognormal is not None and len(amount.lognormal) == 2:
        return float(active_rng.lognormal(amount.lognormal[0], amount.lognormal[1]))

    if amount.lognormal_dollars is not None and len(amount.lognormal_dollars) == 2:
        median_dollars = max(0.01, amount.lognormal_dollars[0])
        sigma_val = amount.lognormal_dollars[1]
        return float(active_rng.lognormal(math.log(median_dollars), sigma_val))

    if amount.triangular is not None and len(amount.triangular) == 3:
        return float(active_rng.triangular(amount.triangular[0], amount.triangular[1], amount.triangular[2]))

    if amount.choice is not None and len(amount.choice) > 0:
        choices = [entry[0] for entry in amount.choice]
        weights = [entry[1] for entry in amount.choice]
        sum_weights = sum(weights)
        norm_weights = [item / sum_weights for item in weights]
        return float(active_rng.choice(choices, p=norm_weights))

    if amount.gas_estimate is not None:
        if amount.gas_estimate.mpg <= 0.0:
            gallons = 0.0
        else:
            gallons = amount.gas_estimate.miles_per_period / amount.gas_estimate.mpg
        return gallons * amount.gas_estimate.cost_per_gallon

    if amount.grocery_estimate is not None:
        return float(amount.grocery_estimate.people * amount.grocery_estimate.cost_per_person_per_period)

    if amount.hourly_pay is not None:
        hourly_spec = amount.hourly_pay
        if isinstance(hourly_spec.hours_per_period, (int, float)):
            hours_worked = float(hourly_spec.hours_per_period)
        else:
            mean_hours = hourly_spec.hours_per_period[0]
            sd_hours = hourly_spec.hours_per_period[1]
            hours_worked = max(0.0, float(active_rng.normal(mean_hours, sd_hours)))

        regular_hours = min(hours_worked, hourly_spec.overtime_threshold)
        overtime_hours = max(0.0, hours_worked - hourly_spec.overtime_threshold)
        regular_pay = regular_hours * hourly_spec.hourly_rate
        overtime_rate = hourly_spec.hourly_rate * hourly_spec.overtime_multiplier
        overtime_pay = overtime_hours * overtime_rate
        return regular_pay + overtime_pay

    return 0.0


def get_amount(amount: AmountModel, rng: Optional[np.random.Generator] = None) -> int:
    active_rng = rng if rng is not None else np.random.default_rng()
    dollar_amount = _sample_base_dollars(amount, active_rng)

    if amount.min_amount is not None:
        dollar_amount = max(amount.min_amount, dollar_amount)
    if amount.max_amount is not None:
        dollar_amount = min(amount.max_amount, dollar_amount)
    if amount.round_to is not None and amount.round_to > 0.0:
        dollar_amount = round(dollar_amount / amount.round_to) * amount.round_to

    return max(0, int(round(dollar_amount * 100.0)))


def resolve_flow_amount_cents(
    flow: FlowModel,
    current_date: date,
    sim_start: date,
    rng: Optional[np.random.Generator] = None,
    last_executed_flow_cents: Optional[Dict[str, int]] = None,
    balances: Optional[Dict[str, int]] = None,
    macro_inflation_index: float = 1.0,
) -> int:
    active_rng = rng if rng is not None else np.random.default_rng()

    # 1. Step selection
    active_amount = flow.amount
    if flow.steps:
        matching_steps = [
            step for step in flow.steps
            if step.start <= current_date and (step.end is None or current_date <= step.end)
        ]
        if matching_steps:
            latest_step = max(matching_steps, key=lambda item: item.start)
            active_amount = latest_step.amount

    # 2. Base dollar draw
    if active_amount.percent_of_flow is not None:
        flow_name = active_amount.percent_of_flow.flow
        prev_cents = (last_executed_flow_cents or {}).get(flow_name, 0)
        dollar_amount = (prev_cents / 100.0) * active_amount.percent_of_flow.pct
    elif active_amount.percent_of_account is not None:
        acc_name = active_amount.percent_of_account.account
        acc_cents = max(0, (balances or {}).get(acc_name, 0))
        pct_value = active_amount.percent_of_account.pct
        divisor_val = active_amount.percent_of_account.divisor
        dollar_amount = (acc_cents / 100.0) * (pct_value / divisor_val)
    else:
        dollar_amount = _sample_base_dollars(active_amount, active_rng)

    # 3. Seasonal multiplier
    if flow.seasonality is not None:
        season_spec = flow.seasonality
        month_num = current_date.month
        if season_spec.monthly and month_num in season_spec.monthly:
            seasonal_multiplier = season_spec.monthly[month_num]
        elif month_num in (12, 1, 2):
            seasonal_multiplier = season_spec.winter
        elif month_num in (3, 4, 5):
            seasonal_multiplier = season_spec.spring
        elif month_num in (6, 7, 8):
            seasonal_multiplier = season_spec.summer
        else:
            seasonal_multiplier = season_spec.fall
        dollar_amount *= seasonal_multiplier

    # 4. Inflation and annual escalation
    if flow.inflation_adjusted:
        dollar_amount *= macro_inflation_index

    if flow.annual_escalation_rate != 0.0:
        rate = flow.annual_escalation_rate
        anchor_date = flow.schedule.start or sim_start
        if flow.escalation_mode == "anniversary":
            anchor_tuple = (anchor_date.month, anchor_date.day)
            current_tuple = (current_date.month, current_date.day)
            year_adjustment = 1 if current_tuple < anchor_tuple else 0
            years_elapsed = current_date.year - anchor_date.year - year_adjustment
            escalation_multiplier = (1.0 + rate) ** max(0, years_elapsed)
        elif flow.escalation_mode == "jan_1":
            years_elapsed = max(0, current_date.year - sim_start.year)
            escalation_multiplier = (1.0 + rate) ** years_elapsed
        else:
            days_elapsed = max(0, (current_date - anchor_date).days)
            escalation_multiplier = (1.0 + rate) ** (days_elapsed / 365.25)
        dollar_amount *= escalation_multiplier

    # 5. Share split, clamp, convert, and date_range spread
    dollar_amount *= flow.share_fraction
    if active_amount.min_amount is not None:
        dollar_amount = max(active_amount.min_amount, dollar_amount)
    if active_amount.max_amount is not None:
        dollar_amount = min(active_amount.max_amount, dollar_amount)
    if active_amount.round_to is not None and active_amount.round_to > 0.0:
        dollar_amount = round(dollar_amount / active_amount.round_to) * active_amount.round_to

    cents = max(0, int(round(dollar_amount * 100.0)))

    has_spread = (
        flow.date_range_total
        and flow.schedule.date_range is not None
        and flow.schedule.date_range.mode == "spread_evenly"
    )
    if has_spread:
        range_spec = flow.schedule.date_range
        total_range_days = (range_spec.end - range_spec.start).days + 1
        if total_range_days > 0:
            base_daily_cents = cents // total_range_days
            remainder_cents = cents % total_range_days
            day_index_in_range = (current_date - range_spec.start).days
            extra_cent = 1 if day_index_in_range < remainder_cents else 0
            cents = base_daily_cents + extra_cent

    return cents
