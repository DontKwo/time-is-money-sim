# Life Money Simulator

A daily-tick personal finance simulator in Python. It models multi-account banking, retirement accounts, paychecks, employer matching, taxes, credit cards, amortized loans, and automated cashflow policies.

## Installation

Install dependencies using uv:

```bash
uv pip install -r requirements.txt
```

## CLI Usage

```bash
# Basic run: outputs ledger.csv and balances.png
uv run --no-project python -m lifesim scenarios/example_mvp.yaml

# Runtime dot-notation override
uv run --no-project python -m lifesim scenarios/example_401k_match.yaml --set paychecks.0.annual_salary=125000.0

# Export daily balance snapshot and JSON analytics
uv run --no-project python -m lifesim scenarios/example_401k_match.yaml --out-daily daily.csv --out-summary summary.json

# Render all charts to directory
uv run --no-project python -m lifesim scenarios/example_401k_match.yaml --charts-dir charts/

# Monte Carlo simulation
uv run --no-project python -m lifesim scenarios/example_401k_match.yaml --monte-carlo 500 --out-mc-plot mc_fan.png

# Scenario comparison
uv run --no-project python -m lifesim scenarios/example_debt_payoff.yaml --compare scenarios/example_credit_and_hysa.yaml --out-compare-plot comparison.png

# Sensitivity tornado sweep
uv run --no-project python -m lifesim scenarios/example_401k_match.yaml --sensitivity --out-tornado-plot sensitivity.png
```

## Configuration Reference

Scenarios are configured in YAML.

### Scenario Horizon & Includes

```yaml
start: 2026-01-01
days: 365                  # or 'end: 2026-12-31'
seed: 42
include:
  - defaults/housing.yaml
  - defaults/food.yaml
exclude:
  - Rent                   # excludes specific flow names from merged files
```

### Universal Schedules

Recurring events support calendar dates, weekend rules, and bank holidays:

```yaml
schedule:
  biweekly: fri
  anchor: 2026-01-02
  weekend_rule: before      # before | after | ignore
  respect_us_holidays: true
```

Supported frequencies:
- `daily: true`
- `weekly: fri` (or list: `[mon, wed, fri]`)
- `biweekly: fri` with `anchor: 2026-01-02`
- `semimonthly: [1, 15]` or `semimonthly: [15, "last"]`
- `monthly: 1` or `monthly: "last"`
- `nth_weekday: {nth: 2, weekday: tue}`
- `quarterly: {month_offset: 2, day: 15}`
- `every_n_months: {n: 6, day: 15}`
- `yearly: {month: 4, day: 15}`
- `once: 2026-06-01`
- `date_range: {start: 2026-07-01, end: 2026-07-15, spread_evenly: true}`
- `random_per_week: 2.0` with `weekday_weights: {fri: 3.0, sat: 3.0, sun: 1.5}`
- `daily_prob: 0.70` with `weekdays_only: true`

### Dynamic Amounts

Flows support deterministic amounts, statistical distributions, and estimators:

- `fixed: 1200.0`
- `normal: [100.0, 15.0]`
- `uniform: [50.0, 150.0]`
- `lognormal_dollars: [50.0, 0.40]`
- `triangular: [100.0, 250.0, 600.0]`
- `choice: [[30.0, 0.70], [75.0, 0.30]]`
- `gas_estimate: {mpg: 28.0, cost_per_gallon: 3.65, miles_per_period: 250.0}`
- `grocery_estimate: {people: 2, cost_per_person_per_period: 85.0}`
- `hourly_pay: {hourly_rate: 35.0, hours_per_period: 45.0, overtime_threshold: 40.0, overtime_multiplier: 1.5}`

### Paychecks & Benefits

Model compensation, merit raises, 401(k) matching tiers, HSA contributions, and direct deposit splits:

```yaml
paychecks:
  - name: "Engineering Job"
    enabled: true
    schedule:
      biweekly: fri
      anchor: 2026-01-02
    annual_salary: 120000.0
    annual_raise_pct: 0.035
    raise_month: 3
    raise_day: 1
    salary_steps:
      - start: 2027-01-01
        annual_salary: 135000.0
    retirement_401k:
      enabled: true
      traditional_pct: 0.06
      employer_match:
        enabled: true
        match_rate: 1.0
        up_to_pct: 0.06
        annual_true_up: true
        to_account: traditional_401k
    hsa:
      enabled: true
      to_account: hsa
      employee_per_period: 125.0
      employer_annual_seed: 500.0
    direct_deposit:
      - to: hysa
        fixed: 500.0
      - to: checking
        remainder: true
    tags: [salary, payday]
```

### Accounts

```yaml
accounts:
  checking:
    kind: checking
    balance: 3000.0
    overdraft_limit: 500.0
    overdraft_fee: 35.0

  hysa:
    kind: hysa
    balance: 15000.0
    annual_growth_rate: 0.045
    interest_posting: monthly

  brokerage:
    kind: investment
    balance: 25000.0
    expected_return: 0.08
    volatility: 0.16
    dividend_yield: 0.015
    drip: true

  credit_card:
    kind: credit_card
    balance: 0.0
    apr: 0.2299
    credit_limit: 10000.0
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

  mortgage:
    kind: mortgage
    principal: 320000.0
    apr: 0.065
    term_months: 360
    payment_day: 1
    payment_from_account: checking
    asset_value: 400000.0
    asset_appreciation_rate: 0.035
    pmi_annual_pct: 0.005
    pmi_drop_ltv: 0.78
```

### Automated Cashflow Policies

Policies automate account sweeps, shortfall protection, debt payoffs, and portfolio rebalancing:

- `shortfall_cover`: covers cash deficits before bills trigger overdraft fees.
- `payday_skim`: sweeps income into tax-advantaged accounts with overflow to brokerage.
- `emergency_fund_target`: maintains rolling target months of living expenses in liquid savings.
- `excess_sweep`: transfers checking balances above a threshold into investment allocations.
- `debt_payoff`: applies excess cash using `avalanche` (highest APR first) or `snowball` (lowest balance first).
- `portfolio_rebalance`: rebalances target asset allocation when weights drift past tolerance.
- `retirement_drawdown`: executes sequential withdrawals with pre-tax gross-up during retirement.
- `sinking_fund`: pre-funds lumpy annual expenses.

Example Debt Avalanche Policy:

```yaml
policies:
  - name: "Debt Avalanche"
    kind: debt_payoff
    enabled: true
    priority: 10
    schedule: {monthly: 26}
    from_account: checking
    keep_checking_buffer: 1000.0
    strategy: avalanche
    target_accounts: [credit_card, auto_loan, student_loan]
    total_monthly_budget: 1500.0
```

### Events, Shocks, & Taxes

Model life milestones, loan refinancing, and medical shocks:

```yaml
events:
  - name: "Home Purchase"
    date: 2027-06-01
    disable_flows: ["Rent"]
    one_time_flow:
      name: "Down Payment"
      type: expense
      from_account: checking
      amount: {fixed: 60000.0}

  - name: "Medical Shock"
    enabled: true
    poisson_per_year: 0.35
    category: health
    amount: {lognormal_dollars: [2500.0, 0.5]}
    type: expense
    account: checking
    insurance_oop_max: 4000.0

taxes:
  enabled: true
  filing_status: single     # single | married_joint | head_of_household
  state_flat_rate: 0.045
  april_true_up: true
  settlement_account: checking

inflation:
  rate: 0.025
  index_irs_limits: true
```

### Financial Goals

Track net worth, liquid runway, and safe withdrawal milestones:

```yaml
goals:
  - name: "Debt Free"
    kind: debt_free

  - name: "100k Net Worth"
    kind: net_worth
    target_amount: 100000.0

  - name: "Coast FIRE"
    kind: coast_fire
    retirement_age_years_away: 15.0
    real_return_assumption: 0.05
    swr: 0.04
```

## Template Catalog & Showcases

- `defaults/`: modular packs for `income`, `retirement_401k`, `housing`, `transport`, `food`, `subscriptions`, `health`, `lifestyle`, `debt`, and `shocks`.
- `scenarios/example_401k_match.yaml`: 401(k) matching, merit raises, HSA seed, and HYSA emergency fund.
- `scenarios/example_credit_and_hysa.yaml`: category cashback card with autopay statement balance funded from HYSA.
- `scenarios/example_debt_payoff.yaml`: high-APR debt payoff comparison.
- `scenarios/example_fire_lifecycle.yaml`: multi-year career progression, home purchase event, CoastFIRE target, and market volatility.
