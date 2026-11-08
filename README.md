# Life Money Simulator

FINANCIAL DISCLAIMER: time-is-money-sim is a pedagogical and conceptual economic simulation. It does NOT provide financial, investment, legal, tax, or retirement advice. The software is provided AS IS without warranty of any kind. The author is not a licensed financial planner or broker, and assumes no liability for economic decisions or outcomes.

Welcome to **Life Money Simulator**! A powerful, daily-tick personal finance simulator written in Python. Whether you want to model multi-account banking, complex retirement strategies (401k, HSA), credit cards, amortized loans, or automate your cashflow policies, this simulator can help you visualize your financial future.

## Quick Start

1. **Install dependencies:**
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```

2. **Run your first simulation:**
   ```bash
   # Basic run: outputs ledger.csv and balances.png
   uv run --no-project python -m lifesim scenarios/example_mvp.yaml
   ```

For a comprehensive guide on running simulations, adjusting parameters, and interpreting results, please refer to the [User Guide](docs/USER_GUIDE.md).

## Simulation Scenarios

The simulator includes several templates to help you get started:

- **`example_mvp.yaml`**: A basic minimal viable product scenario.
- **`example_401k_match.yaml`**: Models 401(k) matching, merit raises, HSA seed, and HYSA emergency fund.
- **`example_credit_and_hysa.yaml`**: Simulates a category cashback card with autopay statement balance funded from a High Yield Savings Account.
- **`example_debt_payoff.yaml`**: High-APR debt payoff comparison (avalanche vs snowball).
- **`example_fire_lifecycle.yaml`**: Models multi-year career progression, a home purchase event, CoastFIRE targets, and market volatility.
- **`realistic_life_template.yaml`**: A comprehensive, realistic full-life financial plan template.

## Documentation

- **[User Guide](docs/USER_GUIDE.md)**: Step-by-step instructions on running and interpreting simulations.
- **[FAQ](docs/FAQ.md)**: Questions on assumptions, compounding formulas, and more.
- **[Configuration Reference](docs/CONFIG_REFERENCE.md)**: Detailed schema and parameters for scenario files.
- **[AGENTS.md](AGENTS.md)**: AI Agent Operational Reference detailing the simulation state engine and technical invariants.

## CLI Usage Examples

```bash
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

## Features

- **Daily-tick Engine**: Accurate day-by-day cashflow simulation.
- **Universal Schedules**: Supports complex frequencies like `biweekly`, `random_per_week`, and `nth_weekday`, respecting US holidays.
- **Dynamic Amounts**: Incorporate deterministic amounts, statistical distributions (normal, lognormal), or estimators (gas, groceries).
- **Automated Cashflow Policies**: Automate sweeps, shortfall coverage, debt payoffs (avalanche/snowball), portfolio rebalancing, and sinking funds.
- **Events & Shocks**: Add one-off life milestones or unpredictable medical/repair shocks.
- **Goals**: Track progress towards Net Worth, Debt-Free, and Coast FIRE milestones.
