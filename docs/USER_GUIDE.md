# User Guide: Life Money Simulator

Welcome to the Life Money Simulator! This guide will walk you through how to use the simulator, adjust simulation parameters, and interpret the outputs.

## 1. Running Simulations

You can run simulations from your terminal using `uv` (a fast Python package installer and runner). The basic command takes a scenario YAML file and produces a ledger and charts.

```bash
uv run --no-project python -m lifesim scenarios/example_mvp.yaml
```

**Common Flags:**
- `--out-daily <file.csv>`: Export a daily snapshot of account balances.
- `--out-summary <file.json>`: Export simulation summary analytics to JSON.
- `--charts-dir <dir>`: Generate charts (balances, net worth) and save them to a directory.
- `--compare <scenario.yaml>`: Compare your base scenario against an alternative.
- `--sensitivity`: Run a sensitivity sweep to see which parameters most affect outcomes.
- `--monte-carlo <N>`: Run N probabilistic simulations to show variance.
- `--out-html <file.html>`: Generate an interactive, self-contained HTML report.

## 2. Adjusting Parameters

Scenarios are built using YAML files. You can edit the YAML files directly or use runtime overrides.

### Runtime Overrides
To quickly test a change without modifying the YAML file, use `--set`:
```bash
uv run --no-project python -m lifesim scenarios/example_mvp.yaml --set paychecks.0.annual_salary=85000.0
```

### Modifying the YAML
Open the `.yaml` file in any text editor. Key areas to adjust:
- **`paychecks`**: Modify your `annual_salary`, 401(k) contribution rates (`traditional_pct`), and employer match details.
- **`accounts`**: Update your starting balances (`balance`), debt interest rates (`apr`), or investment returns (`expected_return`).
- **`flows`**: Add custom recurring expenses or incomes using various schedules (e.g., `monthly`, `weekly`).
- **`events`**: Plan major life events, such as buying a house or a car, which might change your monthly flows.

## 3. Interpreting Outputs

The simulator produces several types of outputs:
- **CLI Table**: A quick ASCII summary showing final net worth, liquid cash, and debt.
- **Ledger (`ledger.csv`)**: An exact transaction history detailing every flow on every day. Note that financial amounts are internally processed in integer cents but stored as dollar amounts in the ledger.
- **Charts**: Step-function charts showing account balances over time. Investments might show volatility based on the configured statistical distributions.
- **HTML Report**: If you used `--out-html`, open the file in your browser for an interactive deep dive into cashflows and net worth progression.

Experiment with different savings rates, debt payoff strategies (like `avalanche` vs. `snowball`), and market conditions to see how they impact your long-term financial health!
