# Life money simulator implementation plan

A daily-tick, event-driven personal finance simulator in Python. Every inflow, paycheck, retirement deferral, employer match, expense, transfer, account return, credit card cycle, loan, automation rule, life event, tax rule, and goal is modular and controlled by YAML configuration. Any item can be added, disabled, bounded by `start` and `end` dates, or scheduled on custom calendar frequencies by editing one block.

This document is an engineering specification written for coding agents. All architectural decisions, data models, accounting sign conventions, mathematical formulas, execution ordering, and edge-case rules are resolved here. Implementing agents follow the tasks in section 12 sequentially without inventing schemas or changing invariants.

## 1. Purpose, baseline inventory, and agent rules

### 1.1 Simulator goals

- Daily calendar accuracy: step forward one calendar `datetime.date` at a time across leap years, month ends, weekends, and bank holidays.
- Universal date and frequency control: every flow, paycheck, deduction, rate schedule, policy, and event accepts `enabled`, `start`, `end`, and flexible recurrence rules (days of week, days of month, nth weekday, biweekly anchors, intervals, date ranges, and Poisson random rates).
- Real-world personal finance mechanics: gross-to-net paychecks, 401(k) employee deferrals (Traditional and Roth), configurable tiered or flat employer 401(k) matching with IRS annual caps and year-end true-up, HSA employee and employer contributions, ESPP, RSU vesting, HYSA interest, stochastic and deterministic investment returns with dividends and cost-basis tracking, credit card statement cycles with grace periods and cashback rewards, amortized loans and mortgages with PMI drop, automated cashflow waterfalls, snowball and avalanche debt payoff, inflation, taxes, Monte Carlo simulation, scenario comparison, and parameter sensitivity charts.
- Zero mandatory clutter: a minimal file with one `checking` account and two flows runs directly. Every advanced block is optional with sensible defaults.
- Deterministic reproducibility: identical YAML plus identical `seed` produces identical cent-exact outputs. Adding or removing one flow never alters random draws for other flows, accounts, or events.

### 1.2 Current repository baseline

Implementing agents start from these existing files in the repository:

- `lifesim/config.py`: Pydantic v2 models (`AccountModel`, `GasEstimate`, `GroceryEstimate`, `AmountModel`, `ScheduleModel`, `AutoTransferModel`, `FlowModel`, `ScenarioModel`) and `load_scenario(path: str) -> ScenarioModel` with `include` merging, `exclude` filtering by flow name, and duplicate flow name suffixing (`_2`, `_3`).
- `lifesim/schedule.py`: `should_fire(schedule: ScheduleModel, current_date: date, start_date: date) -> bool` supporting `start`, `end`, `monthly` (month-end clamped), `weekly` (`mon`..`sun`), `yearly` (month-end clamped), and `once` (cached ISO date).
- `lifesim/amounts.py`: `get_amount(amount: AmountModel, rng: np.random.Generator) -> int` returning non-negative integer cents for `fixed`, `normal`, `uniform`, `lognormal`, `gas_estimate`, and `grocery_estimate`.
- `lifesim/engine.py`: `run(scenario: ScenarioModel) -> Ledger` with SHA-256 per-flow seeded `np.random.Generator` instances, integer-cent `balances`, daily income-first sorting, `auto_transfers` shortfall sweeps before expenses, overdraft limit skipping, overdraft fees, and daily compounding `annual_growth_rate` with fractional-cent `growth_remainders`.
- `lifesim/ledger.py`: `Ledger` class storing transaction dictionaries (`date`, `flow`, `amount`, `account`, `balance`) and `to_df() -> pd.DataFrame`.
- `lifesim/plots.py`: `plot_balances(df: pd.DataFrame, filename: str)` generating step plots per account.
- `lifesim/cli.py` and `lifesim/__main__.py`: CLI accepting positional `scenario`, `--out-ledger`, and `--out-plot`.
- `defaults/`: `food.yaml`, `housing.yaml`, `income.yaml`, `transport.yaml`.
- `scenarios/`: `example_mvp.yaml`, `example_transfer.yaml`.
- `tests/`: `test_engine.py`, `test_cli.py`, `test_duplicates.py`, `test_ledger.py`, `test_plots.py`.

All existing public signatures (`load_scenario`, `should_fire`, `get_amount`, `run`, `Ledger.append`, `Ledger.to_df`, `plot_balances`, and `python -m lifesim <scenario.yaml>`) and all existing tests in `tests/` must continue passing.

### 1.3 Mandatory coding rules for implementing agents

1. **Explicit type annotations**: every function and method signature must annotate all parameters (excluding `self`) and the return type.
2. **Integer cents internally**: represent all balances, transaction amounts, credit limits, loan principals, cost bases, fees, and year-to-date accumulators as `int` cents. Convert config dollar floats at input boundaries via `int(round(dollars * 100.0))`. Store fractional daily compounding, interest, and reward remainders in `dict[str, float]` accumulators so daily integer rounding preserves exact annual rates.
3. **Unified account sign invariant**:
   - Asset accounts (`checking`, `savings`, `hysa`, `cd`, `investment`, `traditional_401k`, `roth_401k`, `traditional_ira`, `roth_ira`, `hsa`, `529`) hold positive `int` cents when funded and negative `int` cents only when overdrawn.
   - Liability accounts (`credit_card`, `loan`, `mortgage`, `student_loan`, `auto_loan`) hold `0` when debt-free and negative `int` cents when money is owed (for example, an `$18,000.00` loan has internal balance `-1_800_000` cents). Users may specify positive `principal: 18000` or `initial_debt: 18000` in YAML; the loader initializes internal balance to `-int(round(principal * 100.0))`.
   - Charging `$50.00` to a credit card subtracts `5000` cents (`0 -> -5000`). Paying `$50.00` from `checking` to that card subtracts `5000` from `checking` and adds `5000` to the card (`-5000 -> 0`). Total financial net worth across accounts is always `sum(balances.values())` plus any tracked physical equity (`home_value_cents`, `vehicle_value_cents`), and transfers conserve net worth automatically.
4. **RNG stream isolation**: create every random generator with `derive_rng(base_seed: int, namespace: str, name: str) -> np.random.Generator` using `int(hashlib.sha256(f"{base_seed}:{namespace}:{name}".encode("utf-8")).hexdigest(), 16) % (2**32)`. Keep existing flow namespace `f"{base_seed}_{flow.name}"` for flow skip/amount draws so existing deterministic flow sequences remain identical, and use separate namespaces (`"schedule"`, `"account"`, `"event"`, `"macro"`, `"paycheck"`) for all new stochastic features.
5. **Code style and linter rules**:
   - Put all imports at the top of each file. Never import inside functions or `try`/`except` blocks.
   - Use `is None` and `is not None`. Use f-strings for formatting.
   - Never use mutable default arguments (`list` or `dict` literals in signatures); use `None` sentinels in functions and `Field(default_factory=list)` in Pydantic models.
   - Never use single-letter or vague variable names (`val`, `tmp`, `temp`, `ret`, `foo`, `bar`, `baz`, `dummy`, `stuff`, `thing`). Use clear domain identifiers (`amount_cents`, `daily_rate`, `matched_pct`, `owed_cents`).
   - Decompose equations with 4 or more binary operations into named intermediate variables (`growth_factor`, `numerator`, `denominator`) before returning. Keep single expressions under 140 characters on one line without artificial line splits.
   - Keep comments to 2 lines or fewer and state only current behavior. Never write `Args:` / `Returns:` multi-line docstrings on short helper functions.
   - Never call `print()` inside library modules (`lifesim/cli.py` is the sole module allowed to write terminal output; use `logging` elsewhere).
6. **Verification commands**:
   - Run unit tests via `uv run --python "<venv_python>" python -m pytest`.
   - Run strict lint checks via `uv run python <path_to_claudemd_linter.py> . --level strict` and resolve all reported issues before finishing any task.

## 2. Target repository architecture

Organize modules in a strict acyclic dependency order (top-down imports only, zero circular dependencies):

```text
lifesim/
  __init__.py
  __main__.py
  rng.py           # derive_rng helper for isolated deterministic RNG streams
  config.py        # Pydantic v2 models, YAML loader, include/exclude merge, --set overrides
  macro.py         # daily inflation index, stochastic inflation, annual IRS limit indexing
  schedule.py      # calendar arithmetic, business-day/holiday shifts, precomputed fire counts
  amounts.py       # distributions, estimators, steps, seasonality, escalation, clamping
  accounts.py      # savings/HYSA/CD, investments (GBM, dividends, basis), credit cards, loans/mortgages
  taxes.py         # FICA, progressive brackets, capital gains brackets, April 15 true-up
  payroll.py       # gross-to-net paychecks, 401k/Roth deferrals, employer match, true-up, HSA, ESPP, RSU
  policies.py      # shortfall cover, payday skims, excess sweeps, IRA overflow, snowball/avalanche, rebalancing
  events.py        # scripted life events, flow/rate mutations, job transitions, Poisson shocks
  goals.py         # financial milestones (emergency fund, down payment, debt-free, CoastFIRE, FI)
  ledger.py        # transaction records, daily balance snapshots, summary metadata
  engine.py        # 12-step daily simulation loop orchestrating all subsystems
  analysis.py      # single-run metrics, unclaimed 401k match detector, cash-crunch warnings, rollups
  montecarlo.py    # N-trial runner, percentile fan bands, goal and overdraft probabilities
  compare.py       # multi-scenario diffing and one-at-a-time parameter sensitivity sweeps
  plots.py         # balance, net worth stack, cashflow, compounding, Monte Carlo fan, tornado charts
  cli.py           # CLI entry point supporting single run, --set overrides, --monte-carlo, --compare, --sensitivity
defaults/
  income.yaml
  housing.yaml
  transport.yaml
  food.yaml
  subscriptions.yaml
  health.yaml
  lifestyle.yaml
  retirement_401k.yaml
  debt.yaml
  shocks.yaml
scenarios/
  example_mvp.yaml
  example_transfer.yaml
  example_401k_match.yaml
  example_credit_and_hysa.yaml
  example_debt_payoff.yaml
  example_fire_lifecycle.yaml
tests/
  test_schedule.py
  test_amounts.py
  test_payroll.py
  test_accounts.py
  test_policies.py
  test_events_and_taxes.py
  test_analysis_and_mc.py
  test_engine.py
  test_cli.py
  test_duplicates.py
  test_ledger.py
  test_plots.py
```

Dependency DAG (each layer may import only from layers listed above it):

1. `rng.py` (imports stdlib + `numpy`)
2. `config.py` (imports stdlib + `yaml` + `pydantic`)
3. `macro.py`, `schedule.py`, `ledger.py` (import `config`, `rng`)
4. `amounts.py`, `taxes.py`, `goals.py` (import `config`, `macro`, `ledger`)
5. `accounts.py`, `payroll.py`, `policies.py`, `events.py` (import `config`, `schedule`, `amounts`, `taxes`, `macro`, `ledger`, `rng`)
6. `engine.py` (imports all domain modules above)
7. `analysis.py`, `montecarlo.py`, `compare.py`, `plots.py` (import `engine`, `ledger`, `config`)
8. `cli.py`, `__main__.py` (import top-level runners, exporters, and plotters)

## 3. Universal schedule and date system

Every recurring or bounded object in the config (`FlowModel`, `PaycheckModel`, `PolicyModel`, `RateStepModel`, `AmountStepModel`) supports `enabled: bool = True`, `start: Optional[date] = None`, and `end: Optional[date] = None`.

### 3.1 Scenario date horizon

In `ScenarioModel` (`lifesim/config.py`):

- `start: date` (required)
- `days: Optional[int] = None`
- `end: Optional[date] = None`
- Add a Pydantic `@model_validator(mode="after")` ensuring at least one of `days` or `end` is provided. If `days is None` and `end is not None`, set `days = (end - start).days + 1` (raise `ValueError` if `days < 1`). If `days is not None` and `end is None`, set `end = start + timedelta(days=days - 1)`.

### 3.2 Complete ScheduleModel schema

Extend `ScheduleModel` in `lifesim/config.py` with these fields:

```python
class NthWeekdaySpec(BaseModel):
    nth: int  # 1, 2, 3, 4, 5, or -1 for last occurrence in month
    weekday: str  # mon..sun
    months: Optional[List[int]] = None  # 1..12; None means every month

class EveryNWeeksSpec(BaseModel):
    n: int  # >= 1
    weekdays: List[str]  # e.g. ["mon", "thu"]
    anchor: Optional[date] = None

class EveryNMonthsSpec(BaseModel):
    n: int  # >= 1, e.g. 6 for semiannual auto insurance
    day: Union[int, str] = 1  # 1..31, -1, or "last"
    anchor_year: Optional[int] = None
    anchor_month: Optional[int] = None

class QuarterlySpec(BaseModel):
    day: Union[int, str] = 1
    months: List[int] = Field(default_factory=lambda: [1, 4, 7, 10])

class YearlySpec(BaseModel):
    month: int  # 1..12
    day: Union[int, str]  # 1..31, -1, or "last"

class DateWindowSpec(BaseModel):
    start: date
    end: date

class DateRangeSpec(BaseModel):
    start: date
    end: date
    mode: Literal["daily", "spread_evenly", "first_day", "last_day"] = "daily"

class ScheduleModel(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None
    pause_windows: List[DateWindowSpec] = Field(default_factory=list)  # skip firing inside any [start, end] window
    daily: bool = False
    every_n_days: Optional[int] = None
    biweekly: Optional[str] = None  # mon..sun
    anchor: Optional[date] = None  # anchor date for every_n_days or biweekly
    weekly: Optional[Union[str, List[str]]] = None  # "fri" or ["mon", "wed", "fri"]
    every_n_weeks: Optional[EveryNWeeksSpec] = None
    semimonthly: Optional[List[Union[int, str]]] = None  # e.g. [1, 15] or [15, "last"]
    monthly: Optional[Union[int, str, List[Union[int, str]]]] = None  # 1, "last", -1, or [1, 15]
    nth_weekday: Optional[NthWeekdaySpec] = None
    quarterly: Optional[QuarterlySpec] = None
    every_n_months: Optional[EveryNMonthsSpec] = None
    yearly: Optional[Union[Dict[str, Union[int, str]], List[Dict[str, Union[int, str]]]]] = None
    once: Optional[Union[str, date]] = None
    dates: Optional[List[date]] = None
    date_range: Optional[DateRangeSpec] = None
    daily_prob: Optional[float] = None  # 0.0..1.0
    random_per_week: Optional[float] = None
    random_per_month: Optional[float] = None
    random_per_year: Optional[float] = None
    weekday_weights: Optional[Dict[str, float]] = None  # e.g. {"fri": 2.5, "sat": 3.0}
    allow_multiple_per_day: bool = False
    weekdays_only: bool = False
    weekends_only: bool = False
    allowed_weekdays: Optional[List[str]] = None
    excluded_dates: Optional[List[date]] = None
    weekend_rule: Literal["ignore", "before", "after"] = "ignore"
    respect_us_holidays: bool = False
```

### 3.3 Exact schedule resolution algorithms

Implement these helpers in `lifesim/schedule.py`:

1. **Day-of-month resolver** `resolve_day_of_month(year: int, month: int, day_spec: Union[int, str]) -> int`:
   - Find `_, last_day = calendar.monthrange(year, month)`.
   - If `day_spec == -1` or `str(day_spec).lower() == "last"`, return `last_day`.
   - Convert `day_int = int(day_spec)`. Clamp with `return max(1, min(day_int, last_day))`.
   - When `monthly` or `semimonthly` supplies a list of day specs (for example `[30, 31]` in February), collect resolved integers into a `set[int]` so clamping `[30, 31]` in a 28-day month fires once on day 28.

2. **Biweekly and every-N-weeks anchor math**:
   - Let `effective_anchor = schedule.anchor or schedule.start or sim_start`.
   - Compute Monday of the anchor week: `anchor_monday = effective_anchor - timedelta(days=effective_anchor.weekday())`.
   - Compute Monday of `candidate_date`: `candidate_monday = candidate_date - timedelta(days=candidate_date.weekday())`.
   - `weeks_elapsed = (candidate_monday - anchor_monday).days // 7`.
   - For `biweekly`: matches when `weeks_elapsed >= 0`, `weeks_elapsed % 2 == 0`, and `candidate_date.weekday() == WEEKDAYS[schedule.biweekly.lower()]` (and `candidate_date >= effective_anchor` if `schedule.anchor` was explicitly set).
   - For `every_n_weeks`: matches when `weeks_elapsed >= 0`, `weeks_elapsed % spec.n == 0`, and `candidate_date.weekday()` is in `{WEEKDAYS[d.lower()] for d in spec.weekdays}`.

3. **Nth weekday of month math**:
   - If `spec.months is not None` and `candidate_date.month not in spec.months`, return `False`.
   - Target weekday integer `target_wd = WEEKDAYS[spec.weekday.lower()]`.
   - Build all matching dates in `(candidate_date.year, candidate_date.month)` by iterating `day_num` from `1` to `last_day`.
   - If `spec.nth == -1`, check `candidate_date == matching_dates[-1]`.
   - If `1 <= spec.nth <= len(matching_dates)`, check `candidate_date == matching_dates[spec.nth - 1]`. Otherwise return `False`.

4. **Every-N-months math**:
   - Let `anchor_y = spec.anchor_year or (schedule.start or sim_start).year` and `anchor_m = spec.anchor_month or (schedule.start or sim_start).month`.
   - `months_elapsed = (candidate_date.year - anchor_y) * 12 + (candidate_date.month - anchor_m)`.
   - Matches when `months_elapsed >= 0`, `months_elapsed % spec.n == 0`, and `candidate_date.day == resolve_day_of_month(candidate_date.year, candidate_date.month, spec.day)`.

5. **US federal holiday observer** `is_us_bank_holiday(check_date: date) -> bool`:
   - Implement pure-Python checks (no external package required) for the 11 standard Federal Reserve holidays with Friday/Monday weekend observance rules: New Year's Day (Jan 1), MLK Jr. Day (3rd Mon Jan), Presidents' Day (3rd Mon Feb), Memorial Day (last Mon May), Juneteenth (Jun 19), Independence Day (Jul 4), Labor Day (1st Mon Sep), Columbus Day (2nd Mon Oct), Veterans Day (Nov 11), Thanksgiving (4th Thu Nov), Christmas Day (Dec 25).
   - `is_non_business_day(check_date: date, respect_holidays: bool) -> bool` returns `True` if `check_date.weekday() >= 5` or (`respect_holidays` and `is_us_bank_holiday(check_date)`).

6. **Business-day shift and precomputed fire map**:
   - `shift_date(raw_date: date, weekend_rule: str, respect_holidays: bool) -> date`:
     - If `weekend_rule == "ignore"`, return `raw_date`.
     - Step `delta = -1` for `"before"` or `+1` for `"after"` while `is_non_business_day(shifted, respect_holidays)` is `True`.
   - `build_fire_counts(schedule: ScheduleModel, sim_start: date, sim_end: date, rng: Optional[np.random.Generator] = None) -> Dict[date, int]`:
     - Scan `raw_date` from `sim_start - timedelta(days=7)` to `sim_end + timedelta(days=7)` (7-day buffer captures shifts across simulation start/end boundaries, such as Sunday Jan 1 shifting `"before"` to Friday Dec 30).
     - Check `schedule.start` and `schedule.end` bounds against `raw_date`, skip any `raw_date` falling inside `schedule.pause_windows` (`win.start <= raw_date <= win.end`, useful for sabbaticals or employment gaps without splitting flows), and apply `excluded_dates`, `weekdays_only`, `weekends_only`, and `allowed_weekdays`.
     - For deterministic rules, if `raw_date` matches, compute `exec_date = shift_date(raw_date, schedule.weekend_rule, schedule.respect_us_holidays)`. If `sim_start <= exec_date <= sim_end`, increment `counts[exec_date] += 1`.
     - For stochastic Poisson schedules (`random_per_week`, `random_per_month`, `random_per_year`):
       - Base daily lambda: `random_per_week / 7.0`, `random_per_month / 30.4375`, or `random_per_year / 365.25`.
       - Normalize `weekday_weights` across allowed weekdays so the mean weight across active weekdays equals `1.0`.
       - Draw `events_today = int(rng.poisson(daily_lambda * weight_for_weekday))`. If `not schedule.allow_multiple_per_day`, clamp `events_today = min(1, events_today)`.
   - Keep `should_fire(schedule: ScheduleModel, current_date: date, start_date: date) -> bool` working directly for unit tests and unshifted deterministic checks.

## 4. Dynamic amounts, escalations, steps, and estimators

### 4.1 Extended AmountModel schema

Extend `AmountModel` in `lifesim/config.py`:

```python
class HourlyPayEstimate(BaseModel):
    hourly_rate: float
    hours_per_period: Union[float, List[float]]  # fixed float or [mean, sd]
    overtime_threshold: float = 40.0
    overtime_multiplier: float = 1.5

class PercentOfFlowSpec(BaseModel):
    flow: str
    pct: float  # e.g. 0.10 for 10%

class PercentOfAccountSpec(BaseModel):
    account: str
    pct: float  # e.g. 0.04 for 4% annual withdrawal
    divisor: float = 1.0  # set 12.0 for monthly 1/12th of 4%

class SeasonalitySpec(BaseModel):
    monthly: Optional[Dict[int, float]] = None  # {1: 1.35, 7: 1.40, ...}
    winter: float = 1.0  # Dec, Jan, Feb
    spring: float = 1.0  # Mar, Apr, May
    summer: float = 1.0  # Jun, Jul, Aug
    fall: float = 1.0    # Sep, Oct, Nov

class AmountModel(BaseModel):
    fixed: Optional[float] = None
    normal: Optional[List[float]] = None
    uniform: Optional[List[float]] = None
    lognormal: Optional[List[float]] = None          # [mu_log, sigma_log]
    lognormal_dollars: Optional[List[float]] = None  # [median_dollars, sigma_log]
    triangular: Optional[List[float]] = None         # [low, mode, high]
    choice: Optional[List[List[float]]] = None       # [[amount, weight], ...]
    gas_estimate: Optional[GasEstimate] = None
    grocery_estimate: Optional[GroceryEstimate] = None
    hourly_pay: Optional[HourlyPayEstimate] = None
    percent_of_flow: Optional[PercentOfFlowSpec] = None
    percent_of_account: Optional[PercentOfAccountSpec] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    round_to: Optional[float] = None  # e.g. 1.0 rounds to whole dollars
```

Add scheduled overrides and escalation fields onto `FlowModel`:

- `enabled: bool = True`
- `share_fraction: float = 1.0` (for example `0.5` for a 50/50 split expense with a partner or roommate so users enter the full receipt or rent amount and adjust their personal share in one field)
- `inflation_adjusted: bool = False`
- `annual_escalation_rate: float = 0.0` (for example `0.04` for 4% annual rent renewal increase)
- `escalation_mode: Literal["anniversary", "jan_1", "smooth_daily"] = "anniversary"`
- `seasonality: Optional[SeasonalitySpec] = None`
- `steps: List[FlowStepModel] = Field(default_factory=list)` where `FlowStepModel` has `start: date`, `end: Optional[date] = None`, `amount: AmountModel`.
- `date_range_total: bool = False` (when `schedule.date_range.mode == "spread_evenly"`, divides sampled amount evenly across the `N` inclusive days in the range, distributing integer-cent remainder `+1` cent to the first `rem` days so exact total cents match).

### 4.2 Exact modifier pipeline in amounts.py

Evaluate `resolve_flow_amount_cents` in this exact sequence:

1. **Step selection**: inspect `flow.steps`. Filter steps where `step.start <= current_date` and (`step.end is None` or `current_date <= step.end`). If any match, select the matching step with the latest `step.start` and use `step.amount`; otherwise use `flow.amount`.
2. **Base dollar draw**:
   - `lognormal_dollars: [median_d, sigma]`: draw `rng.lognormal(math.log(max(0.01, median_d)), sigma)`.
   - `triangular: [low, mode, high]`: draw `rng.triangular(low, mode, high)`.
   - `choice`: normalize weights `weights / sum(weights)` and draw with `rng.choice`.
   - `hourly_pay`: sample `hours` (fixed or `max(0.0, rng.normal(mean_h, sd_h))`). Compute `regular_hours = min(hours, overtime_threshold)` and `overtime_hours = max(0.0, hours - overtime_threshold)`. Dollar amount is `regular_hours * rate + overtime_hours * rate * overtime_multiplier`.
   - `percent_of_flow`: look up `last_executed_flow_cents[spec.flow]` (0 if never fired) and multiply by `spec.pct / 100.0` to dollars.
   - `percent_of_account`: look up `max(0, balances[spec.account]) / 100.0 * (spec.pct / spec.divisor)`.
3. **Seasonal multiplier**: if `flow.seasonality` is set, multiply by `monthly[current_date.month]` if present, otherwise the season multiplier (`winter` for months `12, 1, 2`; `spring` for `3, 4, 5`; `summer` for `6, 7, 8`; `fall` for `9, 10, 11`).
4. **Inflation and escalation**:
   - If `flow.inflation_adjusted` is `True`, multiply by `macro_state.inflation_index` (`1.0` on `scenario.start`).
   - If `flow.annual_escalation_rate != 0.0`:
     - Anchor date `anchor = flow.schedule.start or scenario.start`.
     - For `"anniversary"`: `years_elapsed = current_date.year - anchor.year - (1 if (current_date.month, current_date.day) < (anchor.month, anchor.day) else 0)`. Multiplier is `(1.0 + rate) ** max(0, years_elapsed)`.
     - For `"jan_1"`: `years_elapsed = max(0, current_date.year - scenario.start.year)`. Multiplier is `(1.0 + rate) ** years_elapsed`.
     - For `"smooth_daily"`: `days_elapsed = max(0, (current_date - anchor).days)`. Multiplier is `(1.0 + rate) ** (days_elapsed / 365.25)`.
5. **Share split, clamp, and convert**:
   - Multiply `dollars *= flow.share_fraction`.
   - If `min_amount is not None`: `dollars = max(min_amount, dollars)`.
   - If `max_amount is not None`: `dollars = min(max_amount, dollars)`.
   - If `round_to is not None and round_to > 0`: `dollars = round(dollars / round_to) * round_to`.
   - Return `max(0, int(round(dollars * 100.0)))`.

Keep `get_amount(amount: AmountModel, rng: Optional[np.random.Generator] = None) -> int` intact as the base sampler used by both existing callers and `resolve_flow_amount_cents`.

## 5. Paychecks, 401(k) matching, HSA, ESPP, RSU, and taxes

Users frequently want to model gross salaries, raises, bonuses, employee 401(k) contributions (for example `6%` of gross pay), employer 401(k) match formulas, IRS annual deferral limits, year-end employer match true-ups, HSAs, ESPPs, and paycheck withholding without writing 15 separate flows. Create `lifesim/payroll.py` and `lifesim/taxes.py`.

### 5.1 YAML configuration for paychecks and 401(k) matching

Support a top-level `paychecks: List[PaycheckModel]` list on `ScenarioModel`. Every paycheck has `name`, `enabled`, `schedule` (including `start` and `end` dates and any frequency such as `weekly: fri`, `biweekly: fri`, `semimonthly: [1, 15]`, or `monthly: "last"`), compensation rules, retirement rules, benefit deductions, and deposit routing:

```yaml
paychecks:
  - name: "Primary Engineering Job"
    enabled: true
    schedule:
      biweekly: fri
      anchor: 2026-01-02
      start: 2026-01-01
      end: 2030-12-31
      weekend_rule: before
      respect_us_holidays: true
    annual_salary: 120000.0          # or gross_per_period: {fixed: 4615.38}, or hourly_pay: {...}
    pay_periods_per_year: 26         # auto-inferred from schedule if omitted (weekly=52, biweekly=26, semimonthly=24, monthly=12)
    annual_raise_pct: 0.035          # 3.5% annual merit raise
    raise_month: 3                   # March 1 each year
    raise_day: 1
    salary_steps:                    # promotions or role changes on exact dates
      - {start: 2028-06-01, annual_salary: 145000.0}
    bonuses:                         # supports sign-on (once) and recurring annual bonuses
      - name: "Sign-On Bonus"
        enabled: true
        schedule: {once: "2026-01-30"}
        gross_amount: {fixed: 15000.0}
        supplemental_federal_rate: 0.22
        apply_401k: false
      - name: "Annual Performance Bonus"
        enabled: true
        schedule: {yearly: {month: 3, day: 15}}
        target_pct_of_salary: 0.10
        multiplier: {normal: [1.0, 0.15], min_amount: 0.0, max_amount: 2.0}
        supplemental_federal_rate: 0.22
        apply_401k: true
    retirement_401k:
      enabled: true
      traditional_pct: 0.06          # employee pre-tax contribution % (e.g. 6%)
      roth_pct: 0.02                 # employee post-tax Roth 401k % (e.g. 2%)
      after_tax_roth_pct: 0.0        # Mega-Backdoor Roth after-tax 401k auto-converted up to 415(c) cap
      traditional_fixed: 0.0         # optional fixed dollar per paycheck
      roth_fixed: 0.0
      auto_escalate_pct_per_year: 0.01  # optional +1%/yr auto-increase on Jan 1
      auto_escalate_max_pct: 0.15
      traditional_account: traditional_401k
      roth_account: roth_401k
      employer_match:
        enabled: true
        # Simple flat match: 100% match up to 6% of gross pay
        match_rate: 1.0
        up_to_pct: 0.06
        # Optional multi-tier match (overrides match_rate/up_to_pct when non-empty):
        # tiers:
        #   - {match_rate: 1.0, band_pct: 0.03}   # 100% on first 3%
        #   - {match_rate: 0.5, band_pct: 0.02}   # 50% on next 2% (4% max match on 5% deferral)
        employer_fixed_pct: 0.0      # non-elective company contribution regardless of employee %
        annual_true_up: true         # deposits missed match on Dec 31 if employee hit IRS cap early
        to_account: traditional_401k
        vesting:
          kind: graded               # immediate | cliff | graded
          hire_date: 2026-01-01
          cliff_months: 12
          graded_schedule: {12: 0.25, 24: 0.50, 36: 0.75, 48: 1.0}
      annual_employee_limit: 23500.0
      catch_up_limit: 0.0            # e.g. 7500.0 if age >= 50
      annual_total_limit: 70000.0    # IRS 415(c) employee + employer combined cap
    hsa:
      enabled: true
      to_account: hsa
      employee_per_period: 125.0     # or employee_pct: 0.03
      employer_per_period: 25.0
      employer_annual_seed: 500.0    # lump sum deposited on first paycheck of each calendar year
      annual_limit: 4300.0           # IRS combined employee + employer HSA cap
    pretax_deductions_per_period: 140.0   # medical + dental + vision premiums
    posttax_deductions_per_period: 0.0
    espp:
      enabled: false
      contribution_pct: 0.10         # deducted post-tax into escrow
      discount_pct: 0.15             # 15% purchase discount -> value multiplier 1 / (1 - 0.15)
      purchase_months: [6, 12]       # purchases on last day of June and December
      annual_irs_limit: 25000.0
      to_account: brokerage
    withholding:
      mode: brackets                 # brackets | effective_rate | none
      effective_federal_rate: 0.14
      effective_state_rate: 0.05
      local_tax_rate: 0.0
      include_fica: true
    direct_deposit:
      - {to: savings, fixed: 400.0}  # optional split direct deposit rules evaluated in order
      - {to: checking, remainder: true}
    tags: [payday, salary]
```

Also allow a lightweight `match` block directly on any `transfer` flow for users modeling net paychecks who still want a 4-line 401(k) transfer with employer match:

```yaml
flows:
  - name: "401k Contribution"
    type: transfer
    from: checking
    to: traditional_401k
    schedule: {biweekly: fri, start: 2026-01-02}
    amount: {fixed: 300}
    employer_match_multiplier: 1.0   # credits an extra 100% ($300) from employer into `to` account
    employer_match_cap_per_event: 300.0
```

### 5.2 Exact step-by-step paycheck math

Maintain a `PaycheckYTDState` dictionary keyed by calendar year (resetting on January 1 while keeping the prior year's record until April 15 tax settlement):

- `ytd_gross_cents: int`
- `ytd_fica_wages_cents: int`
- `ytd_taxable_ordinary_cents: int`
- `ytd_emp_401k_cents: int` (shared across all jobs in the calendar year per IRS rules)
- `ytd_total_401k_by_job_cents: Dict[str, int]` (415(c) cap is per-employer)
- `ytd_employer_match_by_job_cents: Dict[str, int]`
- `ytd_hsa_cents: int`
- `ytd_fed_withheld_cents: int`, `ytd_state_withheld_cents: int`, `ytd_fica_withheld_cents: int`

When a `PaycheckModel` fires on `current_date`, compute all lines in integer cents:

1. **Gross pay (`gross_cents`)**:
   - Determine base salary: apply latest matching `salary_steps` where `step.start <= current_date`, else `annual_salary`. Apply annual raises (`(1 + annual_raise_pct) ** raise_count`) for each `(raise_month, raise_day)` passed since paycheck start/step start.
   - Divide `active_salary_dollars / pay_periods_per_year` (or sample `gross_per_period` / `hourly_pay`). Convert to `gross_cents = int(round(gross_dollars * 100.0))`.
   - Record `ytd_gross_cents += gross_cents`.

2. **Pre-tax medical & HSA (`pretax_benefit_cents`, `emp_hsa_cents`, `er_hsa_cents`)**:
   - `pretax_med_cents = int(round(pretax_deductions_per_period * 100.0))` (clamped so deductions never exceed `gross_cents`).
   - If `hsa.enabled`:
     - Remaining annual HSA room: `hsa_room = max(0, hsa_limit_cents - ytd_hsa_cents)`.
     - On first paycheck of calendar year, include `employer_annual_seed_cents`.
     - Employer HSA contribution `er_hsa_cents = min(hsa_room, desired_er_hsa_cents)`. Update `hsa_room -= er_hsa_cents`.
     - Employee HSA contribution `emp_hsa_cents = min(hsa_room, min(gross_cents - pretax_med_cents, desired_emp_hsa_cents))`.
     - Update `ytd_hsa_cents += er_hsa_cents + emp_hsa_cents`.
     - Credit `emp_hsa_cents` and `er_hsa_cents` to `hsa.to_account` and log separate ledger entries (`"{name} HSA Employee"` and `"{name} HSA Employer"`).

3. **Employee 401(k) Traditional & Roth deferrals (`trad_401k_cents`, `roth_401k_cents`)**:
   - Compute active `trad_pct` (adding `years_elapsed * auto_escalate_pct_per_year`, capped at `auto_escalate_max_pct`).
   - `desired_trad_cents = int(round(gross_cents * active_trad_pct)) + int(round(traditional_fixed * 100.0))`.
   - `desired_roth_cents = int(round(gross_cents * roth_pct)) + int(round(roth_fixed * 100.0))`.
   - IRS employee elective deferral cap: `emp_cap_cents = int(round((annual_employee_limit + catch_up_limit) * 100.0))`.
   - `emp_401k_room = max(0, emp_cap_cents - ytd_emp_401k_cents)`.
   - Also cap against `total_415c_room = max(0, total_limit_cents - ytd_total_401k_by_job_cents[job_name])`.
   - Effective room `allowed_emp_401k = min(emp_401k_room, total_415c_room, gross_cents - pretax_med_cents - emp_hsa_cents)`.
   - `trad_401k_cents = min(desired_trad_cents, allowed_emp_401k)`.
   - `roth_401k_cents = min(desired_roth_cents, allowed_emp_401k - trad_401k_cents)`.
   - Update `ytd_emp_401k_cents` and `ytd_total_401k_by_job_cents[job_name]`.
   - Credit `trad_401k_cents` to `traditional_account` and `roth_401k_cents` to `roth_account` with ledger entries.

4. **Employer 401(k) match & non-elective contribution (`er_match_cents`, `er_fixed_cents`)**:
   - Build effective `tiers`: if `employer_match.tiers` is non-empty, use it; otherwise use `[MatchTier(match_rate=employer_match.match_rate, band_pct=employer_match.up_to_pct)]`.
   - Compute employee deferral fraction on this paycheck:
     `actual_emp_pct = (trad_401k_cents + roth_401k_cents) / gross_cents` (if `gross_cents > 0`, else `0.0`).
   - Compute matched percentage and maximum possible match percentage:
     ```python
     remaining_pct = actual_emp_pct
     matched_pct = 0.0
     max_possible_match_pct = 0.0
     for tier in tiers:
         max_possible_match_pct += tier.band_pct * tier.match_rate
         band_used = min(remaining_pct, tier.band_pct)
         matched_pct += band_used * tier.match_rate
         remaining_pct = max(0.0, remaining_pct - band_used)
     ```
   - `raw_match_cents = int(round(gross_cents * matched_pct))`
   - `max_match_cents = int(round(gross_cents * max_possible_match_pct))`
   - Track `unclaimed_401k_match_cents += max(0, max_match_cents - raw_match_cents)` in payroll analytics so the summary report tells the user the exact dollar amount of free employer match missed.
   - `raw_fixed_er_cents = int(round(gross_cents * employer_fixed_pct))`
   - Clamp `er_total_cents = min(raw_match_cents + raw_fixed_er_cents, remaining_415c_room)`.
   - Credit `er_total_cents` to `employer_match.to_account`, add to `ytd_employer_match_by_job_cents[job_name]`, and record in `unvested_match_tracker[job_name]` according to the vesting schedule.
   - **December 31 True-Up**: on `Dec 31` (or `paycheck.schedule.end` if earlier in the year), if `annual_true_up` is `True` and `ytd_gross_by_job > 0`, evaluate the exact same `tiers` loop on `annual_emp_pct = ytd_emp_401k_by_job / ytd_gross_by_job`. Compute `entitled_annual_match = int(round(ytd_gross_by_job * annual_matched_pct))`. If `entitled_annual_match > ytd_employer_match_by_job`, deposit `true_up_cents = min(entitled_annual_match - ytd_employer_match_by_job, remaining_415c_room)` into `employer_match.to_account` with ledger entry `"{name} 401k Employer True-Up"` and reduce `unclaimed_401k_match_cents` accordingly.

5. **FICA and income tax withholding**:
   - Note US payroll law: Section 125 medical premiums and HSA payroll deductions reduce both FICA wages and income-taxable wages, whereas Traditional 401(k) reduces Federal/State income-taxable wages only (Traditional 401(k) remains subject to FICA Social Security and Medicare).
   - `fica_wages_cents = max(0, gross_cents - pretax_med_cents - emp_hsa_cents)`.
   - **Social Security (`6.2%`)**: `ss_taxable_room = max(0, ss_wage_base_cents - ytd_fica_wages_cents)`. `ss_tax_cents = int(round(min(fica_wages_cents, ss_taxable_room) * 0.062))`.
   - **Medicare (`1.45%` + `0.9%` Additional Medicare above `$200,000`)**:
     - Base Medicare: `int(round(fica_wages_cents * 0.0145))`.
     - Additional Medicare: compute overlap of `[ytd_fica_wages_cents, ytd_fica_wages_cents + fica_wages_cents]` above `20_000_000` cents (`$200,000.00`) and multiply by `0.009`.
   - Update `ytd_fica_wages_cents += fica_wages_cents`.
   - **Federal and State income withholding**:
     - `taxable_period_wages_cents = max(0, fica_wages_cents - trad_401k_cents)`.
     - If `withholding.mode == "effective_rate"`: multiply `taxable_period_wages_cents` by `effective_federal_rate`, `effective_state_rate`, and `local_tax_rate`.
     - If `withholding.mode == "brackets"`: annualize `annual_proj_wages = taxable_period_wages_cents * pay_periods_per_year`, subtract `standard_deduction_cents`, apply progressive brackets in `taxes.py`, and divide annual tax by `pay_periods_per_year`.

6. **Post-tax deductions, Mega-Backdoor Roth, & Net Direct Deposit**:
   - If `after_tax_roth_pct > 0`: compute `desired_after_tax = int(round(gross_cents * after_tax_roth_pct))`, clamp against remaining IRS 415(c) `total_limit_cents` room (after employee elective deferrals + employer match), and credit directly to `roth_account` with ledger entry `"{name} Mega-Backdoor Roth 401k"`.
   - Deduct `roth_401k_cents`, `after_tax_roth_cents`, `espp_cents` (capped at `annual_irs_limit * (1 - discount_pct)` out-of-pocket contribution), and `posttax_deductions_cents`.
   - `net_pay_cents = max(0, gross_cents - pretax_med_cents - emp_hsa_cents - trad_401k_cents - total_taxes_cents - roth_401k_cents - after_tax_roth_cents - espp_cents - posttax_ded_cents)`.
   - Route `net_pay_cents` through `direct_deposit` splits in order (`fixed` or `pct` of net pay, with the final `remainder: true` target receiving all remaining cents; default is `100%` to `checking`).

### 5.3 RSU vesting schedules

Support optional `rsu_grants: List[RSUGrantModel]` on `ScenarioModel`:

- Fields: `name`, `enabled`, `schedule` (with `start`, `end`, e.g., `quarterly` after a 1-year cliff), `gross_vest_amount: AmountModel` (or `shares_per_vest * initial_share_price` compounded with an equity return rate), `withhold_tax_rate: float = 0.30` (sell-to-cover tax withholding), `to_account: str = "brokerage"`, `auto_sell_to_account: Optional[str] = None` (diversify immediately into cash/index fund if set).
- On vest date: `net_vest_cents = int(round(gross_vest_cents * (1.0 - withhold_tax_rate)))`. Add `gross_vest_cents` to `ytd_taxable_ordinary_cents`, add `gross_vest_cents - net_vest_cents` to `ytd_fed_withheld_cents`, and deposit `net_vest_cents` (setting `cost_basis += net_vest_cents`) into `to_account`.

## 6. Multi-account engine: HYSA, investments, credit cards, loans, and mortgages

Extend `AccountModel` in `lifesim/config.py` and implement account mechanics in `lifesim/accounts.py`.

### 6.1 Unified AccountModel fields

```python
class RateStepModel(BaseModel):
    start: date
    end: Optional[date] = None
    rate: float
    volatility: Optional[float] = None

class CardAutopaySpec(BaseModel):
    enabled: bool = True
    from_account: str = "checking"
    mode: Literal["statement_balance", "minimum_due", "full_balance", "fixed"] = "statement_balance"
    fixed_amount: float = 0.0

class AccountModel(BaseModel):
    kind: Literal[
        "checking", "savings", "hysa", "cd",
        "investment", "traditional_401k", "roth_401k",
        "traditional_ira", "roth_ira", "hsa", "529",
        "credit_card", "loan", "mortgage", "student_loan", "auto_loan"
    ] = "checking"
    balance: float = 0.0
    principal: Optional[float] = None          # convenience positive debt initializer for loans/cards
    initial_cost_basis: Optional[float] = None # defaults to initial balance for taxable investment
    # Checking & overdraft
    overdraft_limit: Optional[float] = None
    overdraft_fee: Optional[float] = 0.0
    max_overdraft_fees_per_day: int = 3
    min_balance_for_fee_waiver: float = 0.0
    monthly_maintenance_fee: float = 0.0
    # Savings / HYSA / CD / Investment return rates
    annual_growth_rate: float = 0.0            # deterministic annual effective return / APY
    apy: Optional[float] = None                # alias synced with annual_growth_rate if set
    expected_return: Optional[float] = None    # total expected annual return (supports GBM when volatility > 0)
    volatility: float = 0.0                    # annualized volatility (e.g. 0.16 for equities, 0.0 deterministic)
    expense_ratio: float = 0.0                 # annual fund fee (e.g. 0.0003 or 0.0065)
    dividend_yield: float = 0.0                # annual dividend yield (e.g. 0.015)
    dividend_schedule: Literal["monthly", "quarterly"] = "quarterly"
    drip: bool = True                          # reinvest dividends into same account if True, else sweep
    dividend_to_account: Optional[str] = None
    return_includes_dividends: bool = True
    interest_posting: Literal["daily", "monthly"] = "daily"
    rate_steps: List[RateStepModel] = Field(default_factory=list)
    cd_maturity_date: Optional[date] = None
    cd_penalty_days_interest: int = 90
    annual_contribution_limit: Optional[float] = None  # e.g. 7000.0 for Roth/Traditional IRA
    # Credit card fields
    apr: float = 0.0
    promo_apr: Optional[float] = None
    promo_end: Optional[date] = None
    credit_limit: Optional[float] = None
    statement_day: int = 25
    due_day: int = 20
    min_payment_pct: float = 0.02
    min_payment_floor: float = 25.0
    late_fee: float = 35.0
    annual_fee: float = 0.0
    annual_fee_month: int = 1
    cashback_pct: float = 0.0                  # flat reward rate e.g. 0.02 for 2% card
    category_cashback: Dict[str, float] = Field(default_factory=dict)  # e.g. {"dining": 0.04, "groceries": 0.03}
    rewards_to_account: Optional[str] = None   # None = statement credit on statement_day
    autopay: Optional[CardAutopaySpec] = None
    # Loan & mortgage fields
    term_months: Optional[int] = None
    monthly_payment: Optional[float] = None    # auto-computed from principal, apr, term_months if None
    payment_day: int = 1
    payment_from_account: Optional[str] = None
    payment_start: Optional[date] = None
    payment_end: Optional[date] = None
    extra_monthly_principal: float = 0.0
    # Physical asset & mortgage escrow fields
    asset_value: float = 0.0                   # e.g. 450000.0 home value or 28000.0 car value
    asset_appreciation_rate: float = 0.0       # e.g. 0.035 for house, -0.12 for depreciating car
    property_tax_annual_pct: float = 0.0       # % of current asset_value paid monthly via escrow
    home_insurance_annual: float = 0.0
    pmi_annual_pct: float = 0.0                # e.g. 0.006 of initial loan; auto-drops when LTV <= pmi_drop_ltv
    pmi_drop_ltv: float = 0.78
```

### 6.2 Exact return, interest, dividend, and cost-basis formulas

1. **Active annual rate lookup**:
   - Check `account.rate_steps` for the latest step with `step.start <= current_date` and (`step.end is None` or `current_date <= step.end`).
   - Otherwise resolve `base_rate = account.expected_return if account.expected_return is not None else (account.apy if account.apy is not None else account.annual_growth_rate)`.

2. **Savings, HYSA, and Checking interest (`volatility == 0.0`, no dividends)**:
   - `daily_rate = (1.0 + active_rate) ** (1.0 / 365.0) - 1.0`.
   - Only accrue when `balances[name] > 0` and `active_rate != 0.0`.
   - If `interest_posting == "daily"`:
     - `exact_growth = balances[name] * daily_rate + growth_remainders[name]`
     - `growth_cents = int(round(exact_growth))`
     - `growth_remainders[name] = exact_growth - growth_cents`
     - Add `growth_cents` to `balances[name]` and append ledger entry `f"{name} Investment Growth"` (preserving the exact ledger string expected by `test_account_growth_compounds_to_annual_rate` when `kind` is default or investment with daily posting).
   - If `interest_posting == "monthly"`:
     - Accumulate `monthly_unposted_interest[name] += balances[name] * daily_rate`.
     - On the last calendar day of each month, compute `posted_cents = int(round(monthly_unposted_interest[name]))`, subtract `posted_cents` from `monthly_unposted_interest[name]`, credit `balances[name] += posted_cents`, add to `ytd_taxable_interest_cents`, and append ledger entry `f"{name} Monthly Interest"`.

3. **Investment & Retirement returns (`investment`, `401k`, `ira`, `hsa`, `529`)**:
   - Compute price appreciation annual target:
     `div_deduction = account.dividend_yield if account.return_includes_dividends else 0.0`
     `net_annual_return = active_rate - account.expense_ratio - div_deduction`
   - **Deterministic mode (`active_volatility == 0.0`)**:
     `daily_rate = (1.0 + net_annual_return) ** (1.0 / 365.0) - 1.0`, using `growth_remainders[name]` identically to above.
   - **Stochastic GBM mode (`active_volatility > 0.0`)**:
     Use the account's dedicated `account_rng` so draws are independent of flows:
     ```python
     log_expected = math.log(max(1e-6, 1.0 + net_annual_return))
     variance_drag = 0.5 * (active_volatility ** 2)
     daily_drift = (log_expected - variance_drag) / 365.0
     daily_sigma = active_volatility / math.sqrt(365.0)
     daily_log_return = float(account_rng.normal(daily_drift, daily_sigma))
     daily_rate = math.exp(daily_log_return) - 1.0
     ```
     Note: subtracting `0.5 * sigma^2` ensures expected arithmetic annual return $E[S_{365}/S_0] - 1$ equals `net_annual_return` while median compounding reflects real volatility drag.
   - **Dividends**:
     - If `dividend_yield > 0` and `balances[name] > 0`, fire on the last calendar day of every month (`period_yield = dividend_yield / 12.0`) or last day of months `3, 6, 9, 12` (`period_yield = dividend_yield / 4.0`).
     - `div_cents = int(round(balances[name] * period_yield))`.
     - If `drip` is `True`: `balances[name] += div_cents`, `cost_basis_cents[name] += div_cents` (reinvested dividends establish new cost basis), ledger `f"{name} Dividend Reinvestment"`.
     - If `drip` is `False`: credit `div_cents` to `dividend_to_account or default_checking_account` with ledger entry `f"{name} Cash Dividend"`. If account `kind == "investment"`, add `div_cents` to `ytd_qualified_dividends_cents`.
   - **Average-Cost Basis on Withdrawals** (when `kind == "investment"`):
     - On deposit `dep_cents`: `cost_basis_cents[name] += dep_cents`.
     - On withdrawal `wd_cents` from pre-withdrawal balance `pre_bal > 0`:
       `fraction_sold = min(1.0, wd_cents / pre_bal)`
       `basis_removed = int(round(cost_basis_cents[name] * fraction_sold))`
       `realized_gain = wd_cents - basis_removed`
       `cost_basis_cents[name] = max(0, cost_basis_cents[name] - basis_removed)`
       `ytd_realized_cap_gains_cents += realized_gain`

4. **Credit card statement cycle, grace period, and cashback**:
   - Initialize `balances[card] = -int(round(principal * 100))` if `principal` is provided, else `int(round(balance * 100))` (negative when owing money).
   - `in_grace_period` starts `True` if initial balance `== 0`, else `False`.
   - When an expense fires with `from_account == card`:
     - Check limit: if `credit_limit is not None` and `-(balances[card] - amount_cents) > credit_limit_cents`, skip the declined charge (and increment `declined_tx_count`).
     - Subtract `balances[card] -= amount_cents`.
     - Cashback: `reward_rate = card.category_cashback.get(flow.category or "", card.cashback_pct)`. Accumulate `exact_reward = amount_cents * reward_rate + reward_remainders[card]`, `reward_cents = int(round(exact_reward))`, `unredeemed_rewards_cents[card] += reward_cents`.
   - When any transfer/payment arrives `to_account == card` of `pay_cents`:
     - `balances[card] += pay_cents`
     - `remaining_statement_due_cents[card] = max(0, remaining_statement_due_cents[card] - pay_cents)`
     - `payments_since_statement_cents[card] += pay_cents`
   - Daily interest check:
     - Active APR is `promo_apr` when `promo_end is not None and current_date <= promo_end`, else `apr`.
     - If `not in_grace_period[card]` and `balances[card] < 0` and `active_apr > 0`:
       `owed_cents = -balances[card]`
       `unposted_card_interest[card] += owed_cents * (active_apr / 365.0)`
   - On `due_day` (resolved via `resolve_day_of_month`):
     1. If `card.autopay` is enabled: determine `pay_target_cents` (`remaining_statement_due_cents` for `"statement_balance"`, `max(0, minimum_due_cents - payments_since_statement_cents)` for `"minimum_due"`, `max(0, -balances[card])` for `"full_balance"`, or `min(max(0, -balances[card]), fixed_cents)` for `"fixed"`). Execute transfer from `autopay.from_account` (running `auto_transfers` / `shortfall_cover` first if configured).
     2. Grace period check: if `remaining_statement_due_cents[card] == 0`, set `in_grace_period[card] = True`; otherwise set `in_grace_period[card] = False`.
     3. Late fee check: if `minimum_due_cents[card] > 0` and `payments_since_statement_cents[card] < minimum_due_cents[card]`, charge `late_fee_cents` (`balances[card] -= late_fee_cents`, ledger `f"{card} Late Fee"`).
   - On `statement_day` (resolved via `resolve_day_of_month`):
     1. Post accrued interest: `interest_cents = int(round(unposted_card_interest[card]))`. Subtract from `unposted_card_interest[card]`. If `interest_cents > 0`, `balances[card] -= interest_cents`, ledger `f"{card} Interest Charge"`, `total_interest_paid_cents += interest_cents`.
     2. Redeem cashback: if `unredeemed_rewards_cents[card] > 0`, either credit `balances[card] += rewards` (ledger `f"{card} Cashback Statement Credit"`) when `rewards_to_account is None`, or credit `balances[rewards_to_account] += rewards` (ledger `f"{card} Cashback Reward"`). Reset `unredeemed_rewards_cents[card] = 0`.
     3. Snapshot new statement: `stmt_bal = max(0, -balances[card])`, `statement_balance_cents[card] = stmt_bal`, `remaining_statement_due_cents[card] = stmt_bal`, `payments_since_statement_cents[card] = 0`.
     4. Minimum due: if `stmt_bal == 0`, `minimum_due_cents = 0`; else `pct_min = int(round(stmt_bal * min_payment_pct)) + interest_cents`, `minimum_due_cents = min(stmt_bal, max(min_floor_cents, pct_min))`.

5. **Loans and Mortgages (`loan`, `mortgage`, `student_loan`, `auto_loan`)**:
   - Initialize `initial_principal_cents = abs(int(round((principal if principal is not None else balance) * 100.0)))` and `balances[loan] = -initial_principal_cents`.
   - Compute scheduled monthly P&I `scheduled_pi_cents`:
     - If `monthly_payment is not None`: `int(round(monthly_payment * 100.0))`.
     - Else given `P = initial_principal_cents`, `r_m = apr / 12.0`, `n = term_months`:
       - If `r_m == 0.0`: `int(math.ceil(P / max(1, n)))`.
       - Else:
         ```python
         growth_factor = (1.0 + r_m) ** n
         numerator = P * r_m * growth_factor
         denominator = growth_factor - 1.0
         scheduled_pi_cents = int(round(numerator / denominator))
         ```
   - Daily interest accrual: while `balances[loan] < 0` and `apr > 0`, accumulate `unposted_loan_interest[loan] += (-balances[loan]) * (apr / 365.0)`.
   - On `payment_day` (within `[payment_start, payment_end]`):
     1. Post accrued loan interest: `interest_cents = int(round(unposted_loan_interest[loan]))`, `unposted_loan_interest[loan] -= interest_cents`. If `interest_cents > 0`, `balances[loan] -= interest_cents`, ledger `f"{loan} Interest"`, `total_interest_paid_cents += interest_cents`.
     2. Compute total P&I transfer `pi_transfer_cents = min(-balances[loan], scheduled_pi_cents + extra_monthly_principal_cents)`. Execute transfer from `payment_from_account or default_checking` to `loan` (ledger `f"{loan} Payment"`). Note how `-balances[loan]` now reflects exact remaining principal after interest + principal payment.
     3. If `kind == "mortgage"`:
        - Property tax + insurance escrow expense: `escrow_cents = int(round((current_asset_cents * property_tax_annual_pct + home_insurance_annual * 100.0) / 12.0))`. Deduct as expense from funding account (`f"{loan} Escrow Tax and Insurance"`).
        - PMI auto-drop: compute `current_ltv = (-balances[loan]) / max(1, current_asset_cents)`. If `pmi_annual_pct > 0` and `current_ltv > pmi_drop_ltv`, deduct monthly PMI `int(round(initial_principal_cents * pmi_annual_pct / 12.0))` as expense (`f"{loan} PMI"`). Once `current_ltv <= pmi_drop_ltv`, PMI stops automatically.

## 7. Automated cashflow policies and debt payoff strategies

Create `lifesim/policies.py`. Keep `ScenarioModel.auto_transfers` functioning as-is, and add `policies: List[PolicyModel]` sorted by ascending `priority: int = 100`. Every `PolicyModel` includes `name: str`, `kind: str`, `enabled: bool = True`, `start: Optional[date] = None`, `end: Optional[date] = None`, `priority: int = 100`, and `schedule: Optional[ScheduleModel] = None`.

Implement these 8 policy types:

1. **`shortfall_cover`**:
   - Fields: `to_account: str`, `from_accounts: List[str]`, `minimum_balance: float = 0.0`, `restore_to_balance: Optional[float] = None`.
   - Triggered automatically before any expense/payment from `to_account` (or at end-of-day sweep). Iterates `from_accounts` in order, pulling available positive balances (`max(0, balances[src])`) until `to_account` covers the expense plus `restore_to_balance` (or `minimum_balance`).

2. **`payday_skim`**:
   - Fields: `trigger_tag: str = "payday"`, `from_account: str = "checking"`, `to_account: str`, `pct_of_inflow: Optional[float] = None`, `fixed_amount: Optional[float] = None`, `respect_annual_limit: bool = True`, `overflow_to_account: Optional[str] = None`.
   - Triggered immediately whenever an income flow or net paycheck carrying `trigger_tag` lands.
   - If `to_account` has `annual_contribution_limit` (for example a `$7,000` Roth IRA) and `respect_annual_limit` is `True`, deposit up to remaining annual IRA room into `to_account` and automatically route any excess cents into `overflow_to_account` (for example taxable `brokerage`) if specified.

3. **`emergency_fund_target`**:
   - Fields: `schedule: ScheduleModel`, `from_account: str = "checking"`, `to_account: str = "savings"`, `keep_checking_buffer: float = 2000.0`, `target_balance: Optional[float] = None`, `target_months_expenses: Optional[float] = None`.
   - When `target_months_expenses` is set (for example `6.0`), compute trailing 90-day non-transfer expenses multiplied by `(30.4375 / 90.0) * target_months_expenses` (falling back to `target_balance` during the first 30 days if history is sparse). Sweeps excess checking above `keep_checking_buffer` into `to_account` up to the emergency target.

4. **`excess_sweep`**:
   - Fields: `schedule: ScheduleModel` (e.g. `{monthly: "last"}`), `from_account: str = "checking"`, `threshold: float` (e.g. `5000.0`), `keep_buffer: float` (e.g. `3000.0`), `allocations: List[SweepAllocation]` where each allocation has `to_account: str`, `weight: float`, `respect_annual_limit: bool = True`, `overflow_to_account: Optional[str] = None`.
   - When `balances[from_account] > threshold_cents`, sweeps `excess_cents = balances[from_account] - keep_buffer_cents` across `allocations` according to normalized weights (handling IRA caps + brokerage overflow identically to `payday_skim`).

5. **`debt_payoff` (`avalanche` and `snowball`)**:
   - Fields: `schedule: ScheduleModel` (e.g. `{monthly: 26}`), `from_account: str = "checking"`, `keep_checking_buffer: float = 1000.0`, `strategy: Literal["avalanche", "snowball"] = "avalanche"`, `target_accounts: List[str]`, `extra_payment: float = 0.0`, `total_monthly_budget: Optional[float] = None`.
   - Rollover physics: if `total_monthly_budget` is specified (for example `$1,500/month` total toward debt), subtract all scheduled loan/card payments already made in the current calendar month toward `target_accounts`; the entire remaining budget (`max(extra_payment_cents, budget_cents - paid_this_month_cents)`) attacks the top-ranked active debt (`balances[acc] < 0`), spilling over to the second-ranked debt on the exact same day if the top debt hits `0`!
   - Ranking:
     - `"avalanche"`: sort active debts by `(-active_apr, -balances[acc])` (highest APR first; smaller balance breaks ties).
     - `"snowball"`: sort active debts by `(-balances[acc], -active_apr)` (smallest debt balance `-balances[acc]` first; highest APR breaks ties).

6. **`portfolio_rebalance`**:
   - Fields: `schedule: ScheduleModel` (e.g. `{yearly: {month: 12, day: 28}}`), `target_weights: Dict[str, float]` (e.g. `{"us_equities": 0.75, "bonds": 0.25}`), `drift_band: float = 0.05`.
   - Sum balances across `target_weights` accounts. If `max_abs_weight_error >= drift_band`, execute transfers from overweight accounts to underweight accounts to restore exact target weights (applying average-cost basis disposition rules if any overweight account is taxable `investment`).

7. **`retirement_drawdown`**:
   - Fields: `schedule: ScheduleModel` (with `start` date = retirement date), `to_account: str = "checking"`, `target_checking_balance: Optional[float] = None`, `fixed_withdrawal: Optional[float] = None`, `swr_annual_pct: Optional[float] = None` (e.g. `0.04`), `withdrawal_order: List[str]` (default: `["savings", "investment", "traditional_401k", "traditional_ira", "roth_401k", "roth_ira", "hsa"]`), `pretax_gross_up_rate: float = 0.15`.
   - Pulls needed cash sequentially through `withdrawal_order`. When pulling `net_needed_cents` from `traditional_401k` or `traditional_ira`, withdraws `gross_cents = int(round(net_needed_cents / (1.0 - pretax_gross_up_rate)))`, withholds `gross_cents - net_needed_cents` into `ytd_fed_withheld_cents`, adds `gross_cents` to `ytd_taxable_ordinary_cents`, and deposits `net_needed_cents` into `to_account`.

8. **`sinking_fund`**:
   - Fields: `schedule: ScheduleModel` (e.g. `{monthly: 2}`), `from_account: str = "checking"`, `to_account: str = "savings"`, `target_flows: List[str]` (names or tags of lumpy semiannual/annual expenses such as 6-month car insurance, property tax, or vacations), `lookahead_days: int = 365`.
   - Sums scheduled upcoming outlays of `target_flows` over the next `lookahead_days`, divides by the number of policy executions in `lookahead_days`, and transfers that smoothed accrual from `from_account` into `to_account` so lumpy annual bills are pre-funded automatically.

## 8. Life events, stochastic shocks, inflation, and annual taxes

### 8.1 Scripted life events and random shocks (`lifesim/events.py`)

Add `events: List[EventModel]` to `ScenarioModel`. Support two event modes:

1. **Scripted date events** (`date: date`, optional `end_date: Optional[date] = None`):
   - `enable_flows: List[str]` / `disable_flows: List[str]` (matches by flow `name` or any flow carrying a matching `tag`; if `end_date` is set, automatically reverts the toggle on `end_date + 1 day`, making temporary events like a 5-month layoff or 4-year daycare period self-contained in one block).
   - `enable_paychecks: List[str]` / `disable_paychecks: List[str]`.
   - `terminate_job: Optional[str] = None`: disables the named paycheck and forfeits unvested employer 401(k) match (`unvested_cents = int(round(employer_match_pool * (1.0 - vested_fraction)))`, deducting `unvested_cents` from the retirement account with ledger entry `f"{job} Unvested 401k Forfeiture"`).
   - `set_flow_amount: Optional[Dict[str, AmountModel]] = None`.
   - `one_time_flow: Optional[OneTimeChargeSpec] = None` (`type: "income" | "expense" | "transfer"`, `amount: AmountModel`, `from_account`, `to_account`, `category`).
   - `open_account: Optional[Dict[str, AccountModel]] = None` (for example opening a new `mortgage` and `house` asset on a home-purchase date while disabling `"Rent"`).
   - `refinance_loan: Optional[RefinanceSpec] = None` (`loan_account`, `new_apr`, `new_term_months`, `closing_cost`, `closing_cost_from_account`): recomputes `scheduled_pi_cents` on current `-balances[loan_account]` over `new_term_months` at `new_apr`.

2. **Stochastic Poisson shocks** (`poisson_per_year: float`, bounded by optional `start` and `end`):
   - Fields: `name`, `enabled: bool = True`, `start: Optional[date]`, `end: Optional[date]`, `poisson_per_year: float`, `amount: AmountModel`, `type: Literal["expense", "income"] = "expense"`, `account: Optional[str] = None`, `category: str = "shocks"`, `cooldown_days: int = 0`, `insurance_deductible: Optional[float] = None`, `insurance_coinsurance_pct: float = 0.20`, `insurance_oop_max: Optional[float] = None`.
   - Daily firing probability using dedicated `event_rng`: `prob_today = 1.0 - math.exp(-poisson_per_year / 365.25)`. Skip if within `cooldown_days` of last trigger.
   - If `insurance_oop_max` is configured (medical shocks): track `ytd_medical_oop_cents` per calendar year so out-of-pocket charges clamp at remaining annual out-of-pocket max!

### 8.2 Macroeconomics and inflation (`lifesim/macro.py`)

Add `inflation: InflationModel` on `ScenarioModel`:

- `rate: float = 0.0` (e.g. `0.03` for 3% annual CPI inflation; default `0.0` so existing scenarios have zero inflation drift unless requested).
- `volatility: float = 0.0` (optional annual CPI standard deviation drawn each Jan 1 via `macro_rng`).
- `index_irs_limits: bool = True` (when `True` and `rate > 0`, scales annual 401k, IRA, HSA, Social Security wage base, standard deduction, and tax bracket thresholds each Jan 1 by `inflation_index`, rounding contribution caps to the nearest `$500` increment).

### 8.3 Tax configuration and April 15 true-up (`lifesim/taxes.py`)

Add optional `taxes: TaxConfigModel` on `ScenarioModel`:

- `enabled: bool = False`
- `filing_status: Literal["single", "married_joint", "head_of_household"] = "single"`
- `standard_deduction: Optional[float] = None` (defaults by filing status: `15000.0` single, `30000.0` married_joint, `22500.0` head_of_household)
- `federal_brackets: List[TaxBracket]` (defaults to 2026 US single/married progressive brackets: `10%, 12%, 22%, 24%, 32%, 35%, 37%`)
- `ltcg_brackets: List[TaxBracket]` (`0%, 15%, 20%` stacked on top of ordinary taxable income for `ytd_realized_cap_gains_cents + ytd_qualified_dividends_cents`)
- `state_flat_rate: float = 0.0`
- `state_brackets: List[TaxBracket] = Field(default_factory=list)`
- `ss_wage_base: float = 176100.0`
- `april_true_up: bool = True`
- `settlement_account: str = "checking"`

On `April 15` (shifted by `weekend_rule: "after"` if weekend/holiday) of year `Y`, if `taxes.enabled` and `taxes.april_true_up` and year `Y - 1` was simulated:

1. Compute prior-year `ordinary_income = ytd_taxable_ordinary + ytd_taxable_interest` minus `standard_deduction` minus deductible `traditional_ira` contributions.
2. Compute `total_fed_tax = progressive_tax(ordinary_income, federal_brackets) + ltcg_tax(ordinary_income, qualified_div_and_gains, ltcg_brackets)`.
3. Compute `total_state_tax` via `state_brackets` or `state_flat_rate`.
4. `net_settlement_cents = (total_fed_tax + total_state_tax) - (prior_fed_withheld + prior_state_withheld)`.
5. If `net_settlement_cents > 0`, execute tax bill expense (`"Annual Tax True-Up Owed"`); if `< 0`, deposit refund (`"Annual Tax Refund"`).

## 9. Goals, enriched ledger, analytics, Monte Carlo, and charts

### 9.1 Non-breaking Ledger and Daily Snapshot design (`lifesim/ledger.py`)

Preserve `Ledger.append(tx_date, flow_name, amount, account, balance)` positional compatibility while adding optional keyword metadata:

```python
def append(
    self,
    tx_date: date,
    flow_name: str,
    amount: int,
    account: str,
    balance: int,
    category: str = "uncategorized",
    tx_kind: str = "flow",
) -> None:
```

Store `date`, `flow`, `amount`, `account`, `balance`, `category`, and `tx_kind` in `self.records`. Notice that `test_ledger.py` checks `for col in ['date', 'flow', 'amount', 'account', 'balance']: assert col in df.columns`, which remains satisfied while exposing `category` and `tx_kind` for analytics and category charts!

Attach rich daily state directly onto `Ledger`:

- `self.daily_records: List[Dict[str, Union[date, float]]]` populated once at the end of every simulated day with `date`, every account's closing dollar balance, `liquid_net_worth`, `total_net_worth`, `vested_net_worth`, `total_assets`, and `total_debt`.
- `ledger.daily_df() -> pd.DataFrame` returning `pd.DataFrame(self.daily_records)`.
- `self.metrics: Dict[str, Any]` (populated by `analysis.compute_summary_metrics`).
- `self.goal_results: List[Dict[str, Any]]` (populated by `goals.evaluate_goals`).

### 9.2 Financial goals and milestones (`lifesim/goals.py`)

Add `goals: List[GoalModel]` on `ScenarioModel`:

- `name: str`
- `kind: Literal["net_worth", "liquid_net_worth", "account_balance", "debt_free", "emergency_months", "coast_fire", "financial_independence"]`
- `target_amount: float = 0.0`
- `account: Optional[str] = None`
- `target_date: Optional[date] = None`
- `swr: float = 0.04` (Safe Withdrawal Rate for `"financial_independence"`, satisfied when `invested_assets >= trailing_annual_expenses / swr`)
- `retirement_age_years_away: Optional[float] = None` and `real_return_assumption: float = 0.05` (for `"coast_fire"`, satisfied when `invested_assets * ((1 + real_return_assumption) ** years_away) >= target_fi_number`)

Record for each goal: `achieved: bool`, `achieved_date: Optional[date]`, `days_to_achieve: Optional[int]`, `met_by_target_date: Optional[bool]`, and `final_progress_pct: float`.

### 9.3 Comprehensive analytics (`lifesim/analysis.py`)

Implement `compute_summary(scenario: ScenarioModel, ledger: Ledger) -> Dict[str, Any]` computing:

- **Net worth summary**: starting, ending, min (with date), max (with date), total dollar change, and annualized CAGR of `total_net_worth` and `liquid_net_worth`.
- **Cash crunch & liquidity health**: lowest `checking` balance and exact date, count of days below `$500` warning buffer, count of days overdrawn (`checking < 0`), total overdraft fees paid, total credit card late fees paid, count of declined transactions, and ending cash runway in days (`liquid_cash_and_hysa / trailing_90d_daily_expense`).
- **Income, taxes, and savings rate**: total gross pay, total net income, total taxes paid + effective tax rate, total spending, net cash savings, and personal savings rate (`(total_retirement_contributions + net_savings_and_brokerage_transfers + loan_principal_paid) / max(1, total_net_income + employee_pretax_contributions)`).
- **Retirement & compounding scorecard**: employee 401(k) contributed, employer 401(k) match captured, **unclaimed employer 401(k) match dollars** (actionable alert if `> 0`), HSA contributions, total investment growth + HYSA interest earned, credit card cashback earned, and total loan + credit card interest paid.
- **Category breakdown & monthly/yearly cashflow tables**: `monthly_rollup_df(ledger) -> pd.DataFrame` and `category_summary_df(ledger) -> pd.DataFrame` (total, monthly mean, share of spending, share of net income).

### 9.4 Monte Carlo, Scenario A/B Comparison, and Sensitivity (`montecarlo.py`, `compare.py`)

1. **`run_monte_carlo(scenario: ScenarioModel, num_runs: int = 500) -> MonteCarloResult`**:
   - Clone `scenario` per trial `trial_idx in range(num_runs)` with `trial_seed = (base_seed + trial_idx * 10007) % (2**31)`.
   - Collect daily `total_net_worth` and `liquid_net_worth` matrices of shape `(num_runs, scenario.days)`.
   - Compute daily percentiles `p5, p10, p25, p50, p75, p90, p95`.
   - Compute `prob_ever_overdrawn`, `prob_negative_ending_net_worth`, `min_checking_p5`, and per-goal `prob_achieved` + `median_achieved_date`.

2. **`compare_scenarios(named_scenarios: Dict[str, ScenarioModel]) -> ComparisonResult`**:
   - Runs each scenario with the same `base_seed`, builds a side-by-side summary `pd.DataFrame` (ending net worth, delta vs baseline, lowest checking balance, total interest paid, employer match captured, FI date), and aligns daily net worth series for overlay plotting.

3. **`run_sensitivity_analysis(scenario: ScenarioModel, delta_pct: float = 0.10) -> SensitivityResult`**:
   - Runs baseline scenario, then perturbs one lever at a time (`+/- delta_pct` on each spending category, `+/- 0.01` (`1%`) on investment expected return, `+/- 0.02` (`2%`) on 401(k) contribution rate, `+/- delta_pct` on income), recording `low_ending_nw` and `high_ending_nw` sorted by `abs(high_ending_nw - low_ending_nw)` descending for Tornado plotting.

### 9.5 Visualization suite (`lifesim/plots.py`)

Keep `plot_balances(df: pd.DataFrame, filename: str)` intact, and add:

- `plot_net_worth_stack(ledger: Ledger, filename: str)`: stacked positive asset areas and negative liability areas with bold Net Worth line and milestone annotations.
- `plot_monthly_cashflow(ledger: Ledger, filename: str)`: grouped/stacked monthly expenses by category against monthly income and net cashflow line.
- `plot_compounding_breakdown(ledger: Ledger, filename: str)`: cumulative principal contributed vs cumulative investment growth + employer match.
- `plot_monte_carlo_fan(mc_result: MonteCarloResult, filename: str)`: shaded `p5-p95`, `p10-p90`, and `p25-p75` bands around the median `p50` line with horizontal goal target lines.
- `plot_scenario_comparison(comp_result: ComparisonResult, filename: str)`: overlaid net worth curves for Scenario A vs Scenario B (and C, D).
- `plot_sensitivity_tornado(sens_result: SensitivityResult, filename: str)`: horizontal two-sided bar chart ranking which financial change moves final net worth most.

### 9.6 CLI interface and `--set` overrides (`lifesim/cli.py`)

Preserve exact positional invocation `python -m lifesim <scenario.yaml> [--out-ledger ledger.csv] [--out-plot balances.png]` and add optional arguments:

- `--set KEY=VALUE` (repeatable, `action="append"`): mutates raw YAML dict prior to Pydantic validation. Support dot paths indexing dicts by key and lists either by integer index (`paychecks.0.annual_salary=135000`) or item `name` (`flows.Rent.amount.fixed=2100`). Parse values with `yaml.safe_load(value_str)`.
- `--out-daily PATH`: export `ledger.daily_df()` CSV.
- `--out-summary PATH`: export JSON summary metrics + goal results.
- `--charts-dir DIR`: render all single-run plots (`balances.png`, `net_worth.png`, `monthly_cashflow.png`, `compounding.png`) into `DIR`.
- `--monte-carlo N`: run `N` Monte Carlo trials and save fan chart (`--out-mc-plot`, default `monte_carlo.png`) and stats JSON.
- `--compare OTHER_YAML [OTHER_YAML ...]`: compare baseline `scenario` against one or more alternative scenario files and save overlay chart (`--out-compare-plot`, default `comparison.png`).
- `--sensitivity`: run tornado sensitivity sweep and save chart (`--out-tornado-plot`, default `sensitivity.png`).

## 10. Exact 12-step daily execution loop in engine.py

Inside `run(scenario: ScenarioModel) -> Ledger`, iterate `day_index` from `0` to `scenario.days - 1` (`current_date = scenario.start + timedelta(days=day_index)`) executing these 12 steps in exact order every day:

1. **Year rollover & macro update**:
   - If `day_index > 0` and `current_date.month == 1 and current_date.day == 1`: archive prior year's tax state for April 15 true-up, reset current-year `ytd_*` accumulators (`401k`, `IRA`, `HSA`, `FICA`, medical OOP), and update annual inflation / IRS contribution limits if `inflation.index_irs_limits` is `True`.
   - Advance `macro_state.inflation_index` for `current_date`.
2. **Scripted events & stochastic shocks**:
   - Revert any temporary event toggles whose `end_date == current_date - timedelta(days=1)`.
   - Execute scripted `events` matching `current_date` (flow/paycheck toggles, job terminations & unvested 401k forfeitures, new loans/accounts, loan refinances, one-time flows).
   - Roll Poisson `shocks` active on `current_date` using per-event `event_rng`.
3. **Paychecks, bonuses, RSU vests, & year-end payroll hooks**:
   - Fire active `paychecks` whose precomputed schedule count `> 0` on `current_date` (gross -> pre-tax benefits & HSA -> Traditional 401k -> Employer 401k match -> FICA & tax withholding -> Roth 401k & ESPP -> net direct deposits).
   - Fire paycheck `bonus` rules and `rsu_grants` scheduled on `current_date`.
   - Immediately trigger any `payday_skim` policies matching paycheck tags.
   - If `current_date` is an ESPP purchase date, convert ESPP escrow into `to_account` shares at `1.0 / (1.0 - discount_pct)`.
   - If `current_date.month == 12 and current_date.day == 31`, execute employer 401(k) `annual_true_up` deposits where enabled.
4. **Regular income flows & investment dividends**:
   - Fire active `FlowModel` items with `type == "income"` according to precomputed fire counts and `skip_prob`. Record `last_executed_flow_cents[flow.name]`.
   - Post scheduled `dividends` on investment accounts (`drip` reinvestment or cash sweep).
   - Trigger any `payday_skim` policies matching fired income flow tags.
5. **April 15 annual tax settlement**:
   - If `taxes.enabled` and `taxes.april_true_up` and `current_date` is the shifted April 15 tax day for a completed prior year, post tax refund or tax owed.
6. **Scheduled loan & mortgage payments**:
   - Accrue daily loan interest on liability accounts (`loan`, `mortgage`, `student_loan`, `auto_loan`).
   - If `current_date` is a loan's `payment_day` within `[payment_start, payment_end]`, post accrued loan interest, run `shortfall_cover` / `auto_transfers` on the funding account if needed, transfer amortized P&I + extra principal, and deduct mortgage escrow + conditional PMI (`LTV > pmi_drop_ltv`).
7. **Scheduled expense flows**:
   - Fire active `FlowModel` items with `type == "expense"` (preserving deterministic YAML list order).
   - If `from_account` is a `credit_card`, check `credit_limit`, deduct from card balance, and accrue cashback rewards.
   - Otherwise run `auto_transfers` and `shortfall_cover` rules for `from_account`, check `overdraft_limit`, deduct expense, and apply `overdraft_fee` (up to `max_overdraft_fees_per_day`) if `balances[from_account] < 0`.
8. **Scheduled transfer flows**:
   - Fire active `FlowModel` items with `type == "transfer"` (respecting `overdraft_limit` on `from_account`, IRA `annual_contribution_limit` if applicable, cost-basis updates on `investment` accounts, and optional lightweight `employer_match_multiplier`).
9. **Credit card due-date & statement-day cycle**:
   - Accrue daily credit card interest on cards with `not in_grace_period` and `balances[card] < 0`.
   - On `due_day`: execute card `autopay`, update `in_grace_period`, and assess `late_fee` if minimum due was unmet.
   - On `statement_day`: post accrued interest, redeem cashback rewards, and snapshot new `statement_balance` and `minimum_due`.
10. **Automated cashflow & portfolio policies**:
    - Execute scheduled `debt_payoff` (`avalanche` / `snowball`), `emergency_fund_target`, `excess_sweep`, `portfolio_rebalance`, and `retirement_drawdown` policies in ascending `priority` order.
11. **Account returns, HYSA interest, bank fees, & physical asset updates**:
    - Compound daily deterministic or GBM returns on `investment` and retirement accounts, and accrue/post `savings` / `hysa` / `cd` / `checking` APY interest (`daily` or month-end `monthly`).
    - On month-end, assess `monthly_maintenance_fee` on checking accounts below `min_balance_for_fee_waiver`.
    - Compound daily `asset_appreciation_rate` on physical `asset_value` (homes, vehicles).
12. **End-of-day snapshot & milestone evaluation**:
    - Append daily closing balances, `liquid_net_worth`, `total_net_worth`, and `vested_net_worth` to `ledger.daily_records`, and check all `goals` to stamp first achievement dates.

After the loop finishes, populate `ledger.metrics = compute_summary(scenario, ledger)` and return `ledger`.

## 11. Default template catalog and showcase scenarios

Create modular template packs in `defaults/` (each file defines optional `flows:` and/or `accounts:` that users cherry-pick via `include:` and `exclude:`):

- `defaults/income.yaml`: biweekly paycheck, annual December bonus, side-gig random Poisson income.
- `defaults/retirement_401k.yaml`: preconfigured `traditional_401k`, `roth_ira`, and `hsa` accounts plus a template `paychecks:` entry with `6%` 401(k) deferral, `100%` employer match up to `6%`, `7%` expected return, and `payday_skim` Roth IRA auto-invest with brokerage overflow.
- `defaults/housing.yaml`: rent (with 3.5% annual anniversary escalation), seasonal electricity and winter heating gas, water/sewer, fiber internet, mobile phone, renter's insurance.
- `defaults/transport.yaml`: auto loan or payment, 6-month car insurance (`every_n_months: {n: 6, day: 15}`), weekly `gas_estimate`, annual registration, semiannual oil/tire maintenance, random rideshare.
- `defaults/food.yaml`: weekly Saturday `grocery_estimate`, mid-week quick grocery run (`weekly: wed`, `skip_prob: 0.3`), weekday morning coffee (`weekdays_only: true`, `daily_prob: 0.7`), weekend-weighted restaurant dining (`random_per_week: 2.0`, `weekday_weights: {fri: 3.0, sat: 3.0, sun: 1.5}`).
- `defaults/subscriptions.yaml`: streaming video, music, cloud storage, gym membership, annual wholesale club / Prime renewal (tagged `[subscription, cancellable]`).
- `defaults/health.yaml`: dental/vision, monthly prescriptions, random doctor copays, medical shock with `insurance_oop_max`.
- `defaults/lifestyle.yaml`: haircuts (`every_n_days: 35`), clothing, hobbies, household supplies, holiday gifts in December, summer vacation `date_range` (`spread_evenly`).
- `defaults/debt.yaml`: sample student loan, auto loan, and 2% cashback credit card with statement autopay.
- `defaults/shocks.yaml`: Poisson car repair, vet/home emergency, electronics replacement.

Create 4 showcase scenarios in `scenarios/` (alongside existing `example_mvp.yaml` and `example_transfer.yaml`):

1. `scenarios/example_401k_match.yaml`: demonstrates a `$110,000` biweekly salary with `6%` employee 401(k) + `100%` employer match up to `6%`, annual `3.5%` raises, HSA with `$500` employer seed, `4.25%` HYSA emergency fund, `8%` S&P 500 brokerage with `1.5%` reinvested dividends, and month-end excess checking sweep.
2. `scenarios/example_credit_and_hysa.yaml`: routes everyday dining, groceries, and travel through a category-cashback credit card (`4%` dining, `3%` groceries, `2%` base) paid in full via `autopay: statement_balance` while cash sits earning `4.5%` APY in HYSA until card due date.
3. `scenarios/example_debt_payoff.yaml`: models a high-APR credit card, auto loan, and student loan with a `$1,400/month` `debt_payoff` policy ready to compare `--set policies.0.strategy=avalanche` vs `--set policies.0.strategy=snowball`.
4. `scenarios/example_fire_lifecycle.yaml`: multi-year forecast with promotion step, home purchase event (down payment -> mortgage + PMI auto-drop), CoastFIRE milestone, and Monte Carlo market volatility (`volatility: 0.16`).

## 12. Sequential implementation tasks for coding agents

Execute the 12 tasks below in numerical order. Complete all code, unit tests, pytest runs, and strict linter checks for Task `K` before starting Task `K + 1`.

### Task 1: RNG isolation helper, baseline lint cleanup, and Scenario horizon extensions

- **Files**: create `lifesim/rng.py`; edit `lifesim/config.py`, `lifesim/engine.py`, `tests/test_engine.py`.
- **Implement**:
  - Fix existing strict-lint issues in `lifesim/engine.py` (put the single-line `balances` dict comprehension on one line) and `tests/test_engine.py` (rename `val` to `amount_cents` and condense the 3-line comment block at line 145 to `<= 2` lines).
  - `derive_rng(base_seed: int, namespace: str, name: str) -> np.random.Generator` in `lifesim/rng.py`.
  - Add `end: Optional[date] = None` and `@model_validator(mode="after")` on `ScenarioModel` so scenarios can specify `days`, `end`, or both. Ensure all list/dict fields on Pydantic models use `Field(default_factory=...)` instead of mutable literal defaults.
  - Add `apply_cli_overrides(raw_data: Dict[str, Any], overrides: List[str]) -> Dict[str, Any]` in `lifesim/config.py` supporting dot-path overrides by dict key, list index, or list item `name`.
- **Tests** (`tests/test_schedule.py` or `tests/test_engine.py`): test `end` date without `days`, invalid `end < start` raising `ValueError`, `derive_rng` determinism, and `apply_cli_overrides` by both index and flow name.

### Task 2: Universal ScheduleModel and precomputed fire map

- **Files**: edit `lifesim/config.py`, `lifesim/schedule.py`; create `tests/test_schedule.py`.
- **Implement**:
  - Full `ScheduleModel` and sub-models from section 3.2.
  - `resolve_day_of_month`, `is_us_bank_holiday`, `shift_date`, `build_fire_counts`, and updated `should_fire` in `lifesim/schedule.py`.
- **Tests** (`tests/test_schedule.py`):
  - `daily`, `every_n_days: 14` with anchor, `biweekly: "fri"` across year boundary, `weekly: ["mon", "wed", "fri"]`.
  - `semimonthly: [15, "last"]` in February (`2024` leap vs `2025` non-leap), `monthly: [30, 31]` firing once on Feb 28.
  - `nth_weekday` (`2nd tue`, `last fri` via `nth: -1`).
  - `quarterly` and `every_n_months: {n: 6, day: 15}`.
  - `weekend_rule: "before"` shifting Sunday `2026-03-01` to Friday `2026-02-27`, and `"after"` shifting Saturday `2026-08-01` to Monday `2026-08-03`, plus `respect_us_holidays: True` on July 4 / Jan 1.
  - `date_range`, `weekdays_only`, `daily_prob`, and `random_per_week` with `weekday_weights` matching expected mean event count within statistical tolerance.

### Task 3: Macro inflation engine and dynamic amounts pipeline

- **Files**: create `lifesim/macro.py`; edit `lifesim/config.py`, `lifesim/amounts.py`; create `tests/test_amounts.py`.
- **Implement**:
  - `InflationModel` and `MacroState` in `lifesim/macro.py` computing daily `inflation_index` and annual IRS limit multipliers.
  - Extended `AmountModel` (`lognormal_dollars`, `triangular`, `choice`, `hourly_pay`, `percent_of_flow`, `percent_of_account`, `min_amount`, `max_amount`, `round_to`), `FlowModel` modifiers (`enabled`, `steps`, `seasonality`, `inflation_adjusted`, `annual_escalation_rate`, `escalation_mode`, `date_range_total`), and `resolve_flow_amount_cents` in `lifesim/amounts.py`.
- **Tests** (`tests/test_amounts.py`):
  - Exact step override transition on `start` and reversion after `end`.
  - Anniversary escalation (`$1,000` at `5%` is `100_000` cents in year 0, `105_000` cents on first anniversary).
  - `hourly_pay` with `45` hours at `$30/hr` and `1.5x` overtime over `40` -> `40*30 + 5*45 = $1,425.00` (`142_500` cents).
  - `date_range` `spread_evenly` of `$1,000.00` over `3` days yielding `33_334`, `33_333`, `33_333` cents (exact sum `100_000`).

### Task 4: Tax calculation module (FICA, brackets, capital gains, April 15 settlement)

- **Files**: create `lifesim/taxes.py`; edit `lifesim/config.py`.
- **Implement**:
  - `TaxBracket`, `TaxConfigModel`, `YearTaxAccumulator`, `compute_fica_cents`, `compute_progressive_tax_cents`, `compute_ltcg_tax_cents`, and `compute_april_settlement_cents` in `lifesim/taxes.py`.
- **Tests** (`tests/test_events_and_taxes.py`):
  - Social Security `6.2%` stopping cleanly once YTD FICA wages cross `$176,100.00`, while Medicare `1.45%` continues and `0.9%` Additional Medicare activates above `$200,000.00`.
  - Progressive bracket hand calculation matching cent-exact tax liability, plus April 15 refund when withholding exceeded liability.

### Task 5: Paycheck engine, 401(k) matching, annual caps, true-up, HSA, ESPP, and RSU

- **Files**: create `lifesim/payroll.py`; edit `lifesim/config.py`; create `tests/test_payroll.py`.
- **Implement**:
  - `PaycheckModel`, `Retirement401kSpec`, `EmployerMatchSpec`, `MatchTier`, `VestingSpec`, `HSASpec`, `ESPPSpec`, `RSUGrantModel`, and `process_paycheck` / `process_year_end_true_up` / `process_espp_purchase` / `process_rsu_vest` in `lifesim/payroll.py`.
- **Tests** (`tests/test_payroll.py`):
  - Flat match: `$4,000.00` biweekly gross, `6%` employee Traditional 401(k) (`24_000` cents) + `100%` match up to `6%` (`24_000` cents employer match).
  - Partial match & unclaimed tracking: `2%` employee contribution on `100%` up to `6%` yields `8_000` cents match and logs `16_000` cents (`$160.00`) in `unclaimed_401k_match_cents`.
  - Multi-tier match: `[{match_rate: 1.0, band_pct: 0.03}, {match_rate: 0.5, band_pct: 0.02}]` on `10%` employee contribution of `$4,000.00` yields exact `4%` match (`16_000` cents).
  - IRS cap + Dec 31 True-Up: `$4,000.00` biweekly gross (`26` paychecks = `$104,000.00`), employee contributes `25%` (`$1,000.00`/paycheck) with `annual_employee_limit: 23500.0` and `100%` match up to `6%` (`$240.00`/paycheck):
    - Paychecks 1..23 contribute `100_000` cents each; Paycheck 24 clamps to `50_000` cents; Paychecks 25..26 contribute `0` cents.
    - Per-paycheck employer match totals `24 * 24_000 = 576_000` cents (`$5,760.00`).
    - With `annual_true_up: True`, Dec 31 deposits `624_000 - 576_000 = 48_000` cents (`$480.00`) true-up so full `6% * $104,000 = $6,240.00` is received.
  - HSA annual cap clamping across combined `employer_annual_seed + employer_per_period + employee_per_period`.

### Task 6: Multi-account mechanics (HYSA, GBM investments, dividends, basis, credit cards, loans, mortgages)

- **Files**: create `lifesim/accounts.py`; edit `lifesim/config.py`; create `tests/test_accounts.py`.
- **Implement**:
  - Extended `AccountModel` and runtime `AccountState` manager in `lifesim/accounts.py` covering daily/monthly HYSA interest, deterministic & GBM investment returns net of `expense_ratio`, `drip` and cash dividends, average-cost basis tracking, credit card cycles (limits, cashback, grace period, autopay, statement/due days, late fees, promo APR), and amortized loans/mortgages (P&I formula, escrow, conditional PMI drop at `LTV <= 0.78`).
- **Tests** (`tests/test_accounts.py`):
  - Monthly HYSA posting on `$10,000.00` at `4.5%` APY over 365 days ending at `$10,450.00 +/- $0.02` with exactly 12 ledger entries.
  - Cost basis test: `$10,000` initial balance grows to `$12,500`, withdrawing `$2,500` removes `$2,000` basis (`$8,000` remaining basis) and records `$500` realized gain.
  - Credit card grace period: charging `$1,000` with `24%` APR and `autopay: statement_balance` charges `$0.00` interest and credits `$20.00` cashback (`2%`); switching to `autopay: minimum_due` loses grace period and charges daily interest on the next statement.
  - Loan amortization: `$12,000` loan at `6.0%` APR for `12` months computes `103_280` cents (`$1,032.80`) scheduled P&I and reaches `0` cents on month 12 without overpaying into positive balance.
  - Mortgage PMI drop: PMI charges while `LTV > 0.78` and stops automatically once principal payments + home appreciation bring `LTV <= 0.78`.

### Task 7: Cashflow automation policies and Snowball/Avalanche debt payoff

- **Files**: create `lifesim/policies.py`; edit `lifesim/config.py`; create `tests/test_policies.py`.
- **Implement**:
  - All 8 policy engines in `lifesim/policies.py` (`shortfall_cover`, `payday_skim` with annual IRA cap + brokerage overflow, `emergency_fund_target`, `excess_sweep`, `debt_payoff` with rollover budget for `avalanche` and `snowball`, `portfolio_rebalance`, `retirement_drawdown` with pre-tax gross-up, and `sinking_fund`).
- **Tests** (`tests/test_policies.py`):
  - IRA cap overflow: `payday_skim` sending `$1,000/month` to `roth_ira` (`annual_contribution_limit: 7000`) puts `$7,000` into `roth_ira` across Jan-Jul and automatically routes `$5,000` across Aug-Dec into `brokerage`.
  - Avalanche vs Snowball: given two debts (`$2,000` at `8%` APR and `$5,000` at `22%` APR) and fixed total monthly debt budget, verify `avalanche` pays less total interest than `snowball` and both roll paid-off payments into the remaining debt.

### Task 8: Scripted life events and stochastic shocks

- **Files**: create `lifesim/events.py`; edit `lifesim/config.py`; add event tests in `tests/test_events_and_taxes.py`.
- **Implement**:
  - `EventModel` processor supporting temporary `[date, end_date]` flow/paycheck toggles, `terminate_job` unvested 401k forfeiture, mid-sim `open_account` and `refinance_loan`, one-time charges/windfalls, and Poisson `shocks` with `cooldown_days` and medical `insurance_oop_max`.
- **Tests**:
  - Job layoff event on `2026-04-01` through `2026-06-30` disables salary, forfeits 50% unvested match, enables unemployment flow, and automatically restores salary on `2026-07-01`.
  - Medical shock capped by `insurance_oop_max: 4000.0` within a calendar year.

### Task 9: Goals, enriched Ledger, full 12-step engine integration, and analytics

- **Files**: create `lifesim/goals.py`, `lifesim/analysis.py`; edit `lifesim/ledger.py`, `lifesim/engine.py`.
- **Implement**:
  - Enriched `Ledger` with optional `category`/`tx_kind`, `daily_records`, `daily_df()`, `metrics`, and `goal_results`.
  - `GoalModel` evaluators (`net_worth`, `account_balance`, `debt_free`, `emergency_months`, `coast_fire`, `financial_independence`).
  - Complete 12-step daily loop in `lifesim/engine.py` wiring `macro`, `events`, `payroll`, `flows`, `taxes`, `accounts`, `policies`, and `goals`.
  - `compute_summary`, `monthly_rollup_df`, and `category_summary_df` in `lifesim/analysis.py`.
- **Tests**: verify all pre-existing tests in `tests/test_engine.py`, `tests/test_ledger.py`, and `tests/test_duplicates.py` pass alongside an end-to-end multi-account + 401k + loan + credit card integration test checking accounting conservation (`ending_net_worth - starting_net_worth == total_inflows_and_growth - total_outflows_and_fees_and_interest`).

### Task 10: Monte Carlo, Scenario Comparison, and Sensitivity Tornado modules

- **Files**: create `lifesim/montecarlo.py`, `lifesim/compare.py`; create `tests/test_analysis_and_mc.py`.
- **Implement**:
  - `run_monte_carlo`, `compare_scenarios`, and `run_sensitivity_analysis`.
- **Tests** (`tests/test_analysis_and_mc.py`):
  - Monte Carlo `N = 50` run produces monotonic percentile bands (`p5 <= p25 <= p50 <= p75 <= p95` on every day) and identical results when re-run with same seed.
  - `compare_scenarios` accurately computes positive net-worth delta for `6%` 401(k) match vs `0%` 401(k).
  - `run_sensitivity_analysis` ranks levers by net-worth spread descending.

### Task 11: Visualization suite and CLI flags

- **Files**: edit `lifesim/plots.py`, `lifesim/cli.py`, `tests/test_plots.py`, `tests/test_cli.py`.
- **Implement**:
  - New plotting functions in `lifesim/plots.py` (`plot_net_worth_stack`, `plot_monthly_cashflow`, `plot_compounding_breakdown`, `plot_monte_carlo_fan`, `plot_scenario_comparison`, `plot_sensitivity_tornado`).
  - CLI options `--set`, `--out-daily`, `--out-summary`, `--charts-dir`, `--monte-carlo`, `--out-mc-plot`, `--compare`, `--out-compare-plot`, `--sensitivity`, `--out-tornado-plot` in `lifesim/cli.py`.
- **Tests**: verify existing `tests/test_cli.py` and `tests/test_plots.py` pass unchanged, plus new tests exercising `--set`, `--out-summary`, `--monte-carlo 10`, and `--compare`.

### Task 12: Default template packs, showcase scenarios, and README update

- **Files**: create/update `defaults/*.yaml`, create 4 showcase `scenarios/example_*.yaml` files from section 11, update `README.md` with clear YAML examples for schedules, paychecks, 401(k) match, investment return rates, credit cards, loans, policies, and CLI commands.
- **Tests**: add a parametrized smoke test loading and executing every YAML file in `scenarios/` and validating every template pack in `defaults/`, then run full `pytest` suite and strict `claudemd_linter.py` scan until completely clean.
