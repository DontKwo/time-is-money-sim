# Scenario YAML Configuration Reference

This guide provides an exhaustive, field-by-field reference for configuring personal finance scenarios in Life Money Simulator (`lifesim`). Every available section, key, data type, default value, and computational behavior is documented with human-readable explanations and practical examples.

---

## Table of Contents
1. [Scenario Horizon & Merging](#1-scenario-horizon--merging)
2. [Accounts (`accounts`)](#2-accounts-accounts)
   - [Asset Accounts (Cash & Savings)](#asset-accounts-cash--savings)
   - [Investments & Retirement Accounts](#investments--retirement-accounts)
   - [Credit Cards](#credit-cards)
   - [Amortized Loans & Mortgages](#amortized-loans--mortgages)
3. [Universal Schedules (`schedule`)](#3-universal-schedules-schedule)
   - [Recurrence Patterns](#recurrence-patterns)
   - [Business Day & Holiday Rules](#business-day--holiday-rules)
   - [Stochastic Frequencies](#stochastic-frequencies)
4. [Amounts & Dynamic Estimators (`amount`)](#4-amounts--dynamic-estimators-amount)
   - [Distributions](#distributions)
   - [Estimators & Dynamic Formulas](#estimators--dynamic-formulas)
   - [Modifiers, Clamps, & Escalations](#modifiers-clamps--escalations)
5. [Cashflows (`flows`)](#5-cashflows-flows)
6. [Paychecks, Compensation, & Benefits (`paychecks`)](#6-paychecks-compensation--benefits-paychecks)
   - [Salary & Merit Raises](#salary--merit-raises)
   - [Bonuses](#bonuses)
   - [401(k) Employee Deferrals & Employer Matching](#401k-employee-deferrals--employer-matching)
   - [HSA & FSA Deductions](#hsa--fsa-deductions)
   - [ESPP & Direct Deposit Splits](#espp--direct-deposit-splits)
7. [Equity & RSU Grants (`rsu_grants`)](#7-equity--rsu-grants-rsu_grants)
8. [Automated Cashflow Policies (`policies`)](#8-automated-cashflow-policies-policies)
   - [`shortfall_cover`](#shortfall_cover)
   - [`payday_skim`](#payday_skim)
   - [`emergency_fund_target`](#emergency_fund_target)
   - [`excess_sweep`](#excess_sweep)
   - [`debt_payoff` (Avalanche & Snowball)](#debt_payoff-avalanche--snowball)
   - [`portfolio_rebalance`](#portfolio_rebalance)
   - [`retirement_drawdown`](#retirement_drawdown)
   - [`sinking_fund`](#sinking_fund)
9. [Life Events & Shocks (`events`)](#9-life-events--shocks-events)
   - [Scripted Milestone Events](#scripted-milestone-events)
   - [Stochastic Shocks & Insurance](#stochastic-shocks--insurance)
10. [Taxes (`taxes`)](#10-taxes-taxes)
11. [Inflation & Macroeconomics (`inflation`)](#11-inflation--macroeconomics-inflation)
12. [Social Security & RMDs](#12-social-security--rmds)
13. [Financial Goals (`goals`)](#13-financial-goals-goals)

---

## 1. Scenario Horizon & Merging

Top-level keys configure the simulation timeline, deterministic random number generation seed, and modular configuration file composition.

| Field | Type | Default | Description |
|---|---|---|---|
| `start` | `date` (`YYYY-MM-DD`) | *Required* | First calendar day of the simulation. |
| `days` | `integer` | `None` | Number of days to simulate (inclusive). Either `days` or `end` must be provided. |
| `end` | `date` (`YYYY-MM-DD`) | `None` | Ending calendar day of the simulation. If provided without `days`, `days` is automatically computed as `(end - start).days + 1`. |
| `seed` | `integer` | `42` | Base random seed. All random processes (stochastic returns, Poisson events, expense variations) are isolated and deterministic based on this seed. |
| `include` | `list[string]` | `[]` | List of external YAML files (e.g. from `defaults/`) to merge into this scenario. Paths are resolved relative to the scenario file or workspace root. |
| `exclude` | `list[string]` | `[]` | List of flow names defined in included files that should be ignored/filtered out. |

### Example
```yaml
start: 2026-01-01
end: 2035-12-31
seed: 1337
include:
  - defaults/housing.yaml
  - defaults/transport.yaml
exclude:
  - Rent
```

---

## 2. Accounts (`accounts`)

Accounts represent financial containers: liquid deposits, investment portfolios, debt liabilities, and physical assets. All accounts are defined as a key-value mapping under `accounts:`.

### Account Kinds (`kind`)
- **Cash & Savings**: `checking`, `savings`, `hysa`, `cd`
- **Investments & Tax-Advantaged**: `investment` (taxable brokerage), `traditional_401k`, `roth_401k`, `traditional_ira`, `roth_ira`, `hsa`, `529`
- **Liabilities & Debt**: `credit_card`, `loan`, `mortgage`, `student_loan`, `auto_loan`

---

### Asset Accounts (Cash & Savings)

Liquid accounts track available cash for day-to-day spending and reserves.

| Field | Type | Default | Description |
|---|---|---|---|
| `kind` | `string` | `"checking"` | The account type: `checking`, `savings`, `hysa`, or `cd`. |
| `balance` | `float` | `0.0` | Initial dollar balance on day 1. |
| `overdraft_limit` | `float` | `None` | Allowed negative cash balance before transactions are skipped or rejected. |
| `overdraft_fee` | `float` | `0.0` | Fee charged each day the account dips below $0.00. |
| `max_overdraft_fees_per_day` | `integer` | `3` | Maximum number of overdraft penalties assessed in a single calendar day. |
| `min_balance_for_fee_waiver` | `float` | `0.0` | Minimum balance threshold required to avoid monthly maintenance fees. |
| `monthly_maintenance_fee` | `float` | `0.0` | Monthly fee charged if closing balance falls below `min_balance_for_fee_waiver`. |
| `annual_growth_rate` / `apy` | `float` | `0.0` | Annual Percentage Yield (APY) as a decimal (e.g. `0.045` for 4.50%). |
| `interest_posting` | `string` | `"daily"` | Interest credit frequency: `"daily"` (compounded each day) or `"monthly"` (accrued daily, credited on last calendar day). |
| `rate_steps` | `list` | `[]` | Scheduled future APY changes (`start`, optional `end`, `rate`). |
| `cd_maturity_date` | `date` | `None` | (For `cd`) Maturity date of Certificate of Deposit. |
| `cd_penalty_days_interest` | `integer` | `90` | Penalty in days of interest for early withdrawal from CD. |

```yaml
accounts:
  checking:
    kind: checking
    balance: 3500.0
    overdraft_limit: 500.0
    overdraft_fee: 35.0

  hysa:
    kind: hysa
    balance: 20000.0
    apy: 0.045
    interest_posting: monthly
```

---

### Investments & Retirement Accounts

Used for taxable brokerages, 401(k) plans, IRAs, and HSAs. Supports Geometric Brownian Motion (GBM) market volatility, dividend reinvestment (DRIP), expense ratios, and cost-basis accounting.

| Field | Type | Default | Description |
|---|---|---|---|
| `kind` | `string` | - | `investment`, `traditional_401k`, `roth_401k`, `traditional_ira`, `roth_ira`, `hsa`, or `529`. |
| `balance` | `float` | `0.0` | Initial market value. |
| `initial_cost_basis` | `float` | `balance` | Initial tax cost basis (distinguishes principal from taxable gains upon withdrawal). |
| `expected_return` | `float` | `0.0` | Expected total annual nominal return (e.g. `0.08` for 8.0%). |
| `volatility` | `float` | `0.0` | Annualized volatility (standard deviation, e.g. `0.16`). When > 0, daily returns follow stochastic GBM with variance drag. |
| `expense_ratio` | `float` | `0.0` | Annual asset management fee deducted daily (e.g. `0.0003` for 3 bps). |
| `dividend_yield` | `float` | `0.0` | Annual dividend yield (e.g. `0.015` for 1.50%). |
| `dividend_schedule` | `string` | `"quarterly"` | Dividend payment cadence: `"monthly"` or `"quarterly"` (March, June, September, December). |
| `drip` | `boolean` | `true` | Dividend Reinvestment Plan. If `true`, dividends purchase more shares and increase cost basis. If `false`, swept as cash. |
| `dividend_to_account` | `string` | `None` | Target account for cash dividends if `drip: false` (defaults to primary checking). |
| `return_includes_dividends` | `boolean` | `true` | If `true`, price appreciation is `expected_return - expense_ratio - dividend_yield`. |
| `annual_contribution_limit` | `float` | `None` | Maximum allowed contributions per calendar year (e.g. `7000.0` for Roth IRA). Used by policies to prevent over-contribution. |

```yaml
accounts:
  brokerage:
    kind: investment
    balance: 45000.0
    expected_return: 0.085
    volatility: 0.16
    expense_ratio: 0.0003
    dividend_yield: 0.015
    drip: true

  roth_ira:
    kind: roth_ira
    balance: 14000.0
    expected_return: 0.08
    annual_contribution_limit: 7000.0
```

---

### Credit Cards

Models revolving credit, statement cycles, grace periods, category cashback rewards, and automated payments.

| Field | Type | Default | Description |
|---|---|---|---|
| `kind` | `string` | `"credit_card"` | Identifies this account as a revolving credit card. |
| `balance` | `float` | `0.0` | Current balance owed (internally stored as negative). Positive debt can also be set with `principal`. |
| `apr` | `float` | `0.0` | Annual Percentage Rate (e.g. `0.2499` for 24.99%). Accrues daily when not in grace period. |
| `promo_apr` | `float` | `None` | Promotional 0% or low APR rate. |
| `promo_end` | `date` | `None` | Expiration date of promotional APR. |
| `credit_limit` | `float` | `None` | Maximum spending limit. Charges that would exceed this limit are declined. |
| `statement_day` | `integer` | `25` | Day of the month when statement closes and interest/cashback post. |
| `due_day` | `integer` | `20` | Day of the month when payment is due. |
| `min_payment_pct` | `float` | `0.02` | Percentage of statement balance required as minimum payment (e.g. `0.02` for 2%). |
| `min_payment_floor` | `float` | `25.0` | Dollar floor for minimum payment (e.g. `$25.00`). |
| `late_fee` | `float` | `35.0` | Fee assessed if minimum payment is not made by the due date. |
| `cashback_pct` | `float` | `0.0` | Flat cash back rebate rate on all purchases (e.g. `0.02` for 2% back). |
| `category_cashback` | `dict[str, float]` | `{}` | Category multiplier overrides (e.g. `dining: 0.04`, `groceries: 0.03`). |
| `rewards_to_account` | `string` | `None` | Account to deposit cashback rewards into. If omitted, applies as statement credit. |
| `autopay` | `object` | `None` | Automatic bill payment configuration (see below). |

#### `autopay` Sub-Configuration
- `enabled`: `boolean` (default: `true`)
- `from_account`: `string` (account paying the bill, e.g. `"checking"`)
- `mode`: `"statement_balance"`, `"minimum_due"`, `"full_balance"`, or `"fixed"`
- `fixed_amount`: `float` (used when `mode: "fixed"`)

```yaml
accounts:
  rewards_card:
    kind: credit_card
    balance: 0.0
    credit_limit: 15000.0
    apr: 0.2299
    statement_day: 25
    due_day: 20
    cashback_pct: 0.02
    category_cashback:
      dining: 0.04
      groceries: 0.03
    autopay:
      enabled: true
      from_account: checking
      mode: statement_balance
```

---

### Amortized Loans & Mortgages

Tracks fixed-rate installment loans (`loan`, `student_loan`, `auto_loan`, `mortgage`), computing exact amortized Principal & Interest (P&I), property tax/insurance escrow, and automatic PMI drop when LTV drops to 78%.

| Field | Type | Default | Description |
|---|---|---|---|
| `kind` | `string` | - | `loan`, `student_loan`, `auto_loan`, or `mortgage`. |
| `principal` / `balance` | `float` | `0.0` | Initial loan balance owed. |
| `apr` | `float` | *Required* | Fixed annual interest rate (e.g. `0.065` for 6.50%). |
| `term_months` | `integer` | `None` | Original or remaining loan term in months (e.g. `360` for 30-year, `60` for 5-year auto). |
| `monthly_payment` | `float` | `None` | Fixed monthly P&I payment. If omitted, auto-calculated from `principal`, `apr`, and `term_months`. |
| `payment_day` | `integer` | `1` | Day of the month on which the monthly payment is debited. |
| `payment_from_account` | `string` | `None` | Funding account for the monthly payment (defaults to checking). |
| `extra_monthly_principal` | `float` | `0.0` | Extra dollar amount applied directly to principal reduction each month. |
| `asset_value` | `float` | `0.0` | Value of underlying physical asset (house or vehicle). |
| `asset_appreciation_rate` | `float` | `0.0` | Annual appreciation or depreciation rate (e.g. `0.035` for real estate, `-0.15` for vehicle). |
| `property_tax_annual_pct` | `float` | `0.0` | (Mortgage) Property tax rate as a percent of current asset value paid into monthly escrow. |
| `home_insurance_annual` | `float` | `0.0` | (Mortgage) Annual homeowners insurance premium divided into 12 monthly escrow payments. |
| `pmi_annual_pct` | `float` | `0.0` | (Mortgage) Annual Private Mortgage Insurance premium percentage (e.g. `0.005` for 0.5%). |
| `pmi_drop_ltv` | `float` | `0.78` | (Mortgage) Loan-to-Value ratio threshold (e.g. 78%) where PMI automatically ceases. |

```yaml
accounts:
  home_mortgage:
    kind: mortgage
    principal: 380000.0
    apr: 0.065
    term_months: 360
    payment_day: 1
    payment_from_account: checking
    extra_monthly_principal: 200.0
    asset_value: 450000.0
    asset_appreciation_rate: 0.03
    property_tax_annual_pct: 0.012
    home_insurance_annual: 1400.0
    pmi_annual_pct: 0.005
    pmi_drop_ltv: 0.78
```

---

## 3. Universal Schedules (`schedule`)

Every flow, paycheck, policy, and event accepts a `schedule:` block.

### Recurrence Patterns
- `daily: true`: Fires every single calendar day.
- `every_n_days: integer`: Fires every N days from `anchor:` date (or scenario start).
- `weekly: "day"` or `weekly: ["mon", "fri"]`: Fires on specified day(s) of week.
- `biweekly: "fri"` with `anchor: YYYY-MM-DD`: Fires every other week anchored on a specific date.
- `semimonthly: [1, 15]` or `semimonthly: [15, "last"]`: Fires twice a month. Supports `-1` or `"last"` for month end.
- `monthly: 1` or `monthly: "last"`: Fires on specified day each month. Days beyond month-end (e.g. 31 in Feb) are safely clamped.
- `nth_weekday: {nth: 2, weekday: "tue", months: [optional list]}`: Fires on the Nth weekday (e.g. 2nd Tuesday). `nth: -1` represents the last occurrence.
- `quarterly: {day: 15, months: [1, 4, 7, 10]}`: Fires once per calendar quarter.
- `every_n_months: {n: 6, day: 15}`: Fires every N months (ideal for semiannual insurance).
- `yearly: {month: 4, day: 15}`: Fires annually on given date.
- `once: YYYY-MM-DD`: Fires exactly once on specified date.
- `dates: [YYYY-MM-DD, ...]`: Explicit list of execution dates.
- `date_range: {start: YYYY-MM-DD, end: YYYY-MM-DD, mode: "daily" | "spread_evenly" | "first_day" | "last_day"}`: Active across an inclusive date window.

### Business Day & Holiday Rules
- `weekend_rule`: `"ignore"` (default), `"before"` (rolls to preceding Friday), or `"after"` (rolls to following Monday).
- `respect_us_holidays`: `boolean` (default: `false`). When `true`, shifts transactions away from all 11 Federal Reserve bank holidays.
- `weekdays_only`: `boolean` (restricts execution to Monday through Friday).
- `weekends_only`: `boolean` (restricts execution to Saturday and Sunday).
- `allowed_weekdays`: `list[string]` (e.g. `["mon", "wed", "fri"]`).
- `pause_windows`: `list[{start: YYYY-MM-DD, end: YYYY-MM-DD}]` (suspends firing during unpaid leaves or sabbaticals).

### Stochastic Frequencies
- `daily_prob`: `float` (0.0 to 1.0 probability of firing on any given day).
- `random_per_week`: `float` (average occurrences per week drawn via Poisson distribution).
- `random_per_month` / `random_per_year`: `float` (Poisson rate per month or year).
- `weekday_weights`: `dict[str, float]` (weights occurrences toward specific days, e.g. `fri: 3.0, sat: 3.0`).

---

## 4. Amounts & Dynamic Estimators (`amount`)

Amounts can be deterministic dollar values, statistical random distributions, or dynamic cost estimators.

### Distributions
- `fixed: 120.0`: Exact constant dollar amount.
- `normal: [mean, std_dev]`: Gaussian distribution clamped at $0.00.
- `uniform: [min, max]`: Continuous uniform range.
- `lognormal: [mu, sigma]`: Standard log-normal distribution.
- `lognormal_dollars: [median_dollars, sigma]`: Intuitive log-normal centered on median dollar value.
- `triangular: [low, mode, high]`: Triangular distribution.
- `choice: [[amount, weight], ...]`: Discrete weighted choices.

### Estimators & Dynamic Formulas
- `gas_estimate: {mpg: 28.0, cost_per_gallon: 3.85, miles_per_period: 250.0}`: Calculates fuel expense based on driving habits and current gas prices.
- `grocery_estimate: {people: 2, cost_per_person_per_period: 90.0}`: Scales grocery spending by household size.
- `hourly_pay: {hourly_rate: 35.0, hours_per_period: 45.0, overtime_threshold: 40.0, overtime_multiplier: 1.5}`: Computes regular pay plus 1.5x overtime.
- `percent_of_flow: {flow: "FlowName", pct: 15.0}`: Dynamically calculates amount as a percentage of another recent flow (e.g. restaurant tip or sales commission).
- `percent_of_account: {account: "investment", pct: 0.04, divisor: 12.0}`: Computes percentage of current account balance (e.g. 4% SWR divided by 12 months).

### Modifiers, Clamps, & Escalations
Flows support real-world cost escalation and sharing:
- `min_amount` / `max_amount`: Hard upper and lower bounds on sampled amounts.
- `round_to`: Rounding interval (e.g. `1.0` for whole dollars, `5.0` for nearest $5).
- `share_fraction`: Fraction of total bill you pay (e.g. `0.50` for 50/50 rent or utility split with a roommate).
- `inflation_adjusted`: `boolean` (when `true`, scales with cumulative CPI index).
- `annual_escalation_rate`: Annual compounding price increase (e.g. `0.035` for 3.5% rent increase).
- `escalation_mode`: `"anniversary"` (bumps each year on start date), `"jan_1"` (bumps each Jan 1), or `"smooth_daily"`.
- `seasonality`: Multipliers by month or season (`winter`, `spring`, `summer`, `fall`).
- `steps`: Scheduled overrides on exact dates (`- start: 2027-01-01, amount: {fixed: 1800.0}`).

---

## 5. Cashflows (`flows`)

Flows model recurring and one-off incomes, living expenses, and transfers between accounts.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | *Required* | Unique descriptive identifier. |
| `type` | `string` | `"expense"` | Cashflow direction: `"income"`, `"expense"`, or `"transfer"`. |
| `enabled` | `boolean` | `true` | Toggle flow on/off without deleting it. |
| `account` / `from_account` / `from` | `string` | - | Funding account for expenses or transfers. |
| `to_account` / `to` | `string` | - | Destination account for incomes or transfers. |
| `schedule` | `ScheduleModel` | *Required* | Recurrence schedule. |
| `amount` | `AmountModel` | *Required* | Amount distribution or estimator. |
| `category` | `string` | `"uncategorized"` | Budget category (e.g. `housing`, `food`, `utilities`, `leisure`). |
| `tags` | `list[string]` | `[]` | Search and policy tags (e.g. `[subscription, essential]`). |
| `skip_prob` | `float` | `0.0` | Probability (0.0 to 1.0) of randomly skipping this occurrence (e.g. skipping a coffee run). |
| `employer_match_multiplier` | `float` | `0.0` | (For transfers) Lightweight employer match bonus credited directly into the destination account. |

```yaml
flows:
  - name: "Apartment Rent"
    type: expense
    from: checking
    category: housing
    schedule:
      monthly: 1
      weekend_rule: before
    amount: {fixed: 2100.0}
    annual_escalation_rate: 0.03
    share_fraction: 0.50

  - name: "Electric Bill"
    type: expense
    from: rewards_card
    category: utilities
    schedule: {monthly: 18}
    amount: {normal: [95.0, 15.0]}
    seasonality:
      summer: 1.40
      winter: 1.25
```

---

## 6. Paychecks, Compensation, & Benefits (`paychecks`)

Models comprehensive gross-to-net payroll, pre-tax deductions, employer 401(k) matching tiers, vesting, IRS contribution limits, HSA contributions, ESPP, and direct deposit routing.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | *Required* | Employer or job name. |
| `enabled` | `boolean` | `true` | Enable/disable paycheck. |
| `schedule` | `ScheduleModel` | *Required* | Payday frequency (`biweekly: fri`, `semimonthly: [1, 15]`, etc.). |
| `annual_salary` | `float` | `None` | Base annual gross salary. |
| `pay_periods_per_year` | `integer` | Auto | Pay periods per year (auto-inferred: biweekly=26, weekly=52, semimonthly=24, monthly=12). |
| `annual_raise_pct` | `float` | `0.0` | Annual merit salary increase (e.g. `0.035` for 3.5%). |
| `raise_month` / `raise_day` | `integer` | `1` / `1` | Calendar date when annual raises take effect. |
| `salary_steps` | `list` | `[]` | Scheduled future salary jumps (`start`, `annual_salary`). |
| `pretax_deductions_per_period` | `float` | `0.0` | Pre-tax Section 125 medical, dental, and vision insurance premiums per paycheck. |
| `posttax_deductions_per_period` | `float` | `0.0` | Post-tax deductions (union dues, disability, legal plan). |
| `bonuses` | `list` | `[]` | Sign-on and recurring annual bonuses with performance multipliers. |
| `retirement_401k` | `object` | `None` | 401(k) deferral and employer match configuration. |
| `hsa` | `object` | `None` | HSA contributions and employer seed. |
| `fsa` | `object` | `None` | Health Care Flexible Spending Account pre-tax deductions. |
| `espp` | `object` | `None` | Employee Stock Purchase Plan payroll deductions and purchase discount. |
| `withholding` | `object` | `None` | Tax withholding parameters (`brackets` or `effective_rate`). |
| `direct_deposit` | `list` | `[]` | Split direct deposit rules (`to`, `fixed` or `pct`, final `remainder: true`). |

---

### 401(k) Employee Deferrals & Employer Matching (`retirement_401k`)

Models pre-tax Traditional 401(k), Roth 401(k), Mega-Backdoor after-tax Roth conversions, employer matching tiers, and annual true-ups.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `boolean` | `true` | Enables 401(k) processing. |
| `traditional_pct` | `float` | `0.0` | Employee pre-tax Traditional contribution rate (e.g. `0.06` for 6%). |
| `roth_pct` | `float` | `0.0` | Employee post-tax Roth 401(k) contribution rate. |
| `after_tax_roth_pct` | `float` | `0.0` | Mega-Backdoor after-tax contribution rate (auto-converted to Roth up to 415(c) limit). |
| `traditional_account` | `string` | `"traditional_401k"` | Account destination for pre-tax employee and employer contributions. |
| `roth_account` | `string` | `"roth_401k"` | Account destination for Roth employee contributions. |
| `annual_employee_limit` | `float` | `23500.0` | IRS annual elective deferral limit (indexed with inflation). |
| `annual_total_limit` | `float` | `70000.0` | IRS 415(c) total limit across employee and employer contributions. |
| `employer_match` | `object` | - | Employer matching formula. |

#### Employer Match Formula (`employer_match`)
- `enabled`: `boolean` (default: `true`)
- `match_rate`: `float` (e.g. `1.0` for 100% dollar-for-dollar match)
- `up_to_pct`: `float` (e.g. `0.06` to match up to 6% of salary)
- `tiers`: `list[{match_rate: float, band_pct: float}]` (optional multi-tier formula, e.g. 100% on first 3%, 50% on next 2%)
- `annual_true_up`: `boolean` (default: `true`). If employee hits IRS cap early in the year, true-up deposits missed matching funds on Dec 31.
- `vesting`: Graded or cliff vesting schedule (`cliff`, `graded`, `immediate`).

---

## 7. Equity & RSU Grants (`rsu_grants`)

Models Restricted Stock Unit vesting schedules, automatic sell-to-cover tax withholding, and diversification sweeps.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | *Required* | Grant name (e.g. `"New Hire RSU Grant"`). |
| `enabled` | `boolean` | `true` | Toggle grant on/off. |
| `schedule` | `ScheduleModel` | *Required* | Vesting schedule (e.g. `quarterly: {day: 15, months: [3, 6, 9, 12]}`). |
| `gross_vest_amount` | `AmountModel` | *Required* | Value of shares vesting on each date (e.g. `{fixed: 6250.0}`). |
| `withhold_tax_rate` | `float` | `0.30` | Flat sell-to-cover statutory tax withholding rate (e.g. 30%). |
| `to_account` | `string` | `"brokerage"` | Account receiving net shares. |
| `auto_sell_to_account` | `string` | `None` | If specified, immediately sells shares and sweeps proceeds to cash or another account. |

---

## 8. Automated Cashflow Policies (`policies`)

Policies automate account sweeps, overdraft prevention, debt payoffs, and portfolio rebalancing. Executed in ascending `priority:` order.

### `shortfall_cover`
Automatically sweeps funds from secondary accounts into a spending account to prevent overdraft fees or transaction declines.
```yaml
policies:
  - name: "Checking Overdraft Guard"
    kind: shortfall_cover
    priority: 10
    to_account: checking
    from_accounts: [hysa, savings]
    minimum_balance: 500.0
```

### `payday_skim`
Sweeps a fixed amount or percentage of every paycheck directly into savings or investments immediately upon deposit.
```yaml
policies:
  - name: "Roth IRA Payday Sweep"
    kind: payday_skim
    priority: 20
    trigger_tag: payday
    from_account: checking
    to_account: roth_ira
    fixed_amount: 500.0
    respect_annual_limit: true
    overflow_to_account: brokerage
```

### `emergency_fund_target`
Maintains a target emergency fund balance or rolling months of living expenses in liquid savings.
```yaml
policies:
  - name: "6 Month Emergency Fund"
    kind: emergency_fund_target
    priority: 30
    schedule: {monthly: 1}
    from_account: checking
    to_account: hysa
    keep_checking_buffer: 2500.0
    target_months_expenses: 6.0
```

### `excess_sweep`
Sweeps checking account cash exceeding a comfort threshold into target investment allocations on a schedule.
```yaml
policies:
  - name: "Month End Cash Sweep"
    kind: excess_sweep
    priority: 40
    schedule: {monthly: "last"}
    from_account: checking
    threshold: 6000.0
    keep_buffer: 3500.0
    allocations:
      - to_account: roth_ira
        weight: 0.50
        respect_annual_limit: true
        overflow_to_account: brokerage
      - to_account: brokerage
        weight: 0.50
```

### `debt_payoff` (Avalanche & Snowball)
Allocates extra cash or a fixed monthly debt budget toward active liabilities.
- `strategy: avalanche`: Targets the highest APR debt first (minimizes interest paid).
- `strategy: snowball`: Targets the lowest remaining balance first (maximizes psychological momentum).
```yaml
policies:
  - name: "Accelerated Debt Avalanche"
    kind: debt_payoff
    priority: 15
    schedule: {monthly: 26}
    from_account: checking
    keep_checking_buffer: 1500.0
    strategy: avalanche
    target_accounts: [credit_card, student_loan, auto_loan]
    total_monthly_budget: 1200.0
```

### `portfolio_rebalance`
Restores target asset allocation across investment accounts when drift exceeds a threshold.
```yaml
policies:
  - name: "Annual Rebalance"
    kind: portfolio_rebalance
    priority: 50
    schedule: {yearly: {month: 12, day: 28}}
    drift_band: 0.05
    target_weights:
      brokerage: 0.80
      hysa: 0.20
```

### `retirement_drawdown`
Executes systematic withdrawals in retirement across asset accounts with pre-tax gross-up.
```yaml
policies:
  - name: "Retirement Safe Withdrawal"
    kind: retirement_drawdown
    schedule: {monthly: 1, start: 2045-01-01}
    to_account: checking
    swr_annual_pct: 0.04
    withdrawal_order: [hysa, brokerage, traditional_401k, roth_ira]
    pretax_gross_up_rate: 0.15
```

### `sinking_fund`
Pre-funds lumpy semiannual or annual expenses (car insurance, property taxes, vacations) by transferring smoothed monthly accruals into savings.
```yaml
policies:
  - name: "Insurance Sinking Fund"
    kind: sinking_fund
    schedule: {monthly: 2}
    from_account: checking
    to_account: hysa
    target_flows: ["Auto Insurance"]
    lookahead_days: 365
```

---

## 9. Life Events & Shocks (`events`)

### Scripted Milestone Events
Model career transitions, home purchases, loan refinances, or temporary changes.
```yaml
events:
  - name: "Buy First Home"
    date: 2027-06-01
    disable_flows: ["Apartment Rent"]
    one_time_flow:
      name: "Home Down Payment"
      type: expense
      from_account: checking
      amount: {fixed: 60000.0}
    open_account:
      home_mortgage:
        kind: mortgage
        principal: 340000.0
        apr: 0.065
        term_months: 360
        payment_day: 1
        asset_value: 400000.0
```

### Stochastic Shocks & Insurance
Simulates random emergency repairs, medical events, or unexpected windfalls via Poisson processes.
```yaml
events:
  - name: "Emergency Medical Event"
    enabled: true
    poisson_per_year: 0.30
    category: health
    type: expense
    account: checking
    amount: {lognormal_dollars: [3500.0, 0.6]}
    insurance_deductible: 1500.0
    insurance_coinsurance_pct: 0.20
    insurance_oop_max: 4000.0
    cooldown_days: 60
```

---

## 10. Taxes (`taxes`)

Computes Federal, FICA, State, and Capital Gains taxes with April 15 annual true-up settlement.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `boolean` | `false` | Enables tax simulation. |
| `filing_status` | `string` | `"single"` | `"single"`, `"married_joint"`, or `"head_of_household"`. |
| `standard_deduction` | `float` | Auto | Standard deduction ($15,000 single, $30,000 married). |
| `state_flat_rate` | `float` | `0.0` | State flat income tax rate (e.g. `0.05` for 5%). |
| `federal_brackets` | `list` | 2026 IRS | Progressive federal tax brackets (10%, 12%, 22%, 24%, 32%, 35%, 37%). |
| `ltcg_brackets` | `list` | 2026 IRS | Long-term capital gains and qualified dividend brackets (0%, 15%, 20%). |
| `ss_wage_base` | `float` | `176100.0` | Maximum wage base subject to 6.2% Social Security tax. |
| `april_true_up` | `boolean` | `true` | Credits refund or settles balance owed on April 15. |
| `settlement_account` | `string` | `"checking"` | Account for tax refunds or payments. |

```yaml
taxes:
  enabled: true
  filing_status: single
  state_flat_rate: 0.045
  april_true_up: true
  settlement_account: checking
```

---

## 11. Inflation & Macroeconomics (`inflation`)

Adjusts real purchasing power and scales annual IRS contribution caps.

| Field | Type | Default | Description |
|---|---|---|---|
| `rate` | `float` | `0.0` | Annual CPI inflation rate (e.g. `0.025` for 2.50%). |
| `volatility` | `float` | `0.0` | Annual inflation standard deviation for stochastic inflation. |
| `index_irs_limits` | `boolean` | `true` | Scales 401(k), IRA, HSA caps, and tax brackets annually with inflation. |

```yaml
inflation:
  rate: 0.025
  index_irs_limits: true
```

---

## 12. Social Security & RMDs

Models retirement Social Security benefits and Required Minimum Distributions (RMDs).

### Social Security (`social_security`)
- `enabled`: `boolean` (default: `false`)
- `start_date`: `date` (benefit commencement date)
- `monthly_benefit`: `float` (initial monthly benefit in today's dollars)
- `annual_cola`: `float` (Cost of Living Adjustment, default: `0.025`)
- `to_account`: `string` (destination account, default: `"checking"`)
- `taxable_pct`: `float` (portion subject to income tax, default: `0.85`)

### Required Minimum Distributions (`rmd_enabled`)
- `birth_date`: `date` (used to determine SECURE Act 2.0 RMD age 73/75)
- `rmd_enabled`: `boolean` (calculates IRS Uniform Lifetime Table withdrawals from traditional accounts)
- `rmd_target_account`: `string` (defaults to `"checking"`)

---

## 13. Financial Goals (`goals`)

Evaluates milestone achievement dates, progress percentages, and on-track status.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | *Required* | Goal name. |
| `kind` | `string` | *Required* | Milestone type (see below). |
| `target_amount` | `float` | `0.0` | Target dollar amount. |
| `account` | `string` | `None` | Account to inspect (for `account_balance`). |
| `target_date` | `date` | `None` | Optional target deadline date. |
| `swr` | `float` | `0.04` | Safe Withdrawal Rate for `financial_independence`. |
| `retirement_age_years_away` | `float` | `None` | Years away from retirement for `coast_fire`. |
| `real_return_assumption` | `float` | `0.05` | Real expected return assumption for `coast_fire`. |

### Goal Kinds (`kind`)
- `net_worth`: Total net worth reaches `target_amount`.
- `liquid_net_worth`: Liquid assets (cash + savings + taxable brokerage) reach `target_amount`.
- `account_balance`: Specific account balance reaches `target_amount`.
- `debt_free`: Total debt liabilities reach $0.00.
- `emergency_months`: Liquid savings cover N months of living expenses.
- `coast_fire`: Current invested assets will grow to fully fund retirement at retirement age with zero future contributions.
- `financial_independence`: Total invested assets reach 25x annual expenses (based on `swr: 0.04`).

```yaml
goals:
  - name: "Debt Free"
    kind: debt_free

  - name: "100k Net Worth Milestone"
    kind: net_worth
    target_amount: 100000.0
    target_date: 2028-12-31

  - name: "Coast FIRE"
    kind: coast_fire
    retirement_age_years_away: 15.0
    real_return_assumption: 0.05
    swr: 0.04
```
