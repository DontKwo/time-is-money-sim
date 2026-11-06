# Life Money Simulator

A daily-tick personal finance simulator in Python. It accurately models multi-account banking, retirement accounts, paychecks, employer matching, taxes, credit cards, amortized loans, and automated cashflow policies.

Detailed documentation is available in the [Comprehensive Configuration Reference](docs/CONFIG_REFERENCE.md).

---

## Quickstart

Run your first simulation with `uv`:

```bash
# Run a scenario: displays a clean terminal summary and saves balance chart
uv run lifesim scenarios/example_mvp.yaml
```

To run the realistic all-in-one life template:
```bash
uv run lifesim scenarios/realistic_life_template.yaml
```

---

## Installation & Setup

This project uses [uv](https://docs.astral.sh/uv/) for Python packaging and dependency management.

```bash
# Sync dependencies and install the project
uv sync
```

---

## Common CLI Commands

```bash
# Basic run: outputs ledger.csv, terminal summary, and balances.png
uv run lifesim scenarios/example_401k_match.yaml

# Interactive desktop plot display
uv run lifesim scenarios/example_401k_match.yaml --show

# Runtime dot-notation override
uv run lifesim scenarios/example_401k_match.yaml --set paychecks.0.annual_salary=125000.0

# Export daily balance snapshot and JSON analytics
uv run lifesim scenarios/example_401k_match.yaml --out-daily daily.csv --out-summary summary.json

# Render all visual charts to directory
uv run lifesim scenarios/example_401k_match.yaml --charts-dir charts/

# Monte Carlo simulation (500 stochastic trials)
uv run lifesim scenarios/example_401k_match.yaml --monte-carlo 500 --out-mc-plot mc_fan.png

# Scenario comparison (e.g. debt payoff strategies)
uv run lifesim scenarios/example_debt_payoff.yaml --compare scenarios/example_credit_and_hysa.yaml --out-compare-plot comparison.png

# Parameter sensitivity analysis (Tornado chart)
uv run lifesim scenarios/example_401k_match.yaml --sensitivity --out-tornado-plot sensitivity.png

# Validate a scenario configuration without running
uv run lifesim scenarios/example_mvp.yaml --validate
```

---

## Configuration Overview

Scenarios are defined in human-readable YAML. For a complete guide to every setting, see [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md).

### Core Components
- **Accounts**: Checking, HYSA, CD, Brokerage, Traditional 401(k), Roth 401(k), IRAs, HSA, Credit Cards, Loans, and Mortgages.
- **Universal Schedules**: Daily, weekly, biweekly with anchor dates, semimonthly, monthly with month-end clamping, quarterly, yearly, once, business-day shifting (`before`/`after`), and Federal Reserve holiday awareness.
- **Dynamic Amounts**: Fixed values, normal/uniform/lognormal distributions, and real-world estimators (`gas_estimate`, `grocery_estimate`, `hourly_pay`).
- **Paychecks & Benefits**: Gross-to-net paychecks, merit raises, 401(k) matching tiers, Dec 31 true-ups, HSA seeds, and direct deposit splits.
- **Automated Policies**: Overdraft protection (`shortfall_cover`), paycheck sweeps (`payday_skim`), emergency fund targets, excess cash sweeps, debt avalanche/snowball, and portfolio rebalancing.
- **Events & Shocks**: Career changes, home purchases, loan refinances, and Poisson medical/repair shocks with insurance out-of-pocket maximums.
- **Goals**: Net worth milestones, debt-free target, and Coast FIRE / FI tracking.

---

## Template Catalog

- `scenarios/realistic_life_template.yaml`: Complete, realistic real-person financial plan template.
- `scenarios/example_401k_match.yaml`: 401(k) matching, merit raises, HSA seed, and HYSA emergency fund.
- `scenarios/example_credit_and_hysa.yaml`: Category cashback credit card with full statement autopay from HYSA.
- `scenarios/example_debt_payoff.yaml`: High-APR debt payoff comparison.
- `scenarios/example_fire_lifecycle.yaml`: Multi-year career progression, home purchase event, and CoastFIRE milestone.
- `defaults/`: Modular building blocks for `income`, `housing`, `food`, `transport`, `health`, `subscriptions`, `lifestyle`, `debt`, and `shocks`.
