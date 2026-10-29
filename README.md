# Life Money Simulator

A daily-tick, event-driven personal finance simulator in Python.

## Installation

Install the required dependencies via pip:

```bash
pip install -r requirements.txt
```

## Running the Simulator

To run the simulator, execute the CLI module and provide a scenario file:

```bash
python -m lifesim scenarios/example_mvp.yaml
```

This will run the simulator based on the configuration and generate a `ledger.csv` and `balances.png` plot.

## Configuration

Configurations are written in YAML format. The primary model is the `Scenario`, which defines:
- `start`: The start date (YYYY-MM-DD)
- `days`: The number of days to simulate
- `seed`: Random seed for deterministic distributions
- `include`: A list of other YAML files to merge into the scenario (optional)
- `exclude`: A list of flow names to exclude from the merged config (optional)
- `accounts`: A dictionary of accounts and starting balances
- `flows`: A list of inflows and outflows

### Include and Exclude

You can organize your configuration using the `include` and `exclude` directives:

```yaml
include:
  - defaults/housing.yaml
  - defaults/transport.yaml
exclude:
  - Rent # Drops the 'Rent' flow from the included housing.yaml file
```

### Amount Types

Flows require an `amount` specification. You can use standard fixed amounts, statistical distributions, or specific helper functions:

- `fixed`: A fixed amount (e.g., `fixed: 1500`)
- `normal`: A normal distribution `[mean, standard deviation]` (e.g., `normal: [110, 30]`)
- `uniform`: A uniform distribution `[min, max]` (e.g., `uniform: [50, 150]`)
- `lognormal`: A log-normal distribution `[mean, sigma]` (e.g., `lognormal: [3.5, 0.5]`)

### Helpers

To simplify the calculation of dynamic costs, we offer a few helper objects:

**Gas Estimate:** calculates cost based on MPG, cost per gallon, and miles driven per period.
```yaml
gas_estimate:
  mpg: 25.0
  cost_per_gallon: 3.50
  miles_per_period: 300.0
```

**Grocery Estimate:** calculates cost based on the number of people and a budget per person.
```yaml
grocery_estimate:
  people: 2
  cost_per_person_per_period: 75.0
```

### Schedule Types

Flows require a `schedule` defining when they execute:
- `monthly: <day>`: Runs on a specific day of the month.
- `weekly: <day>`: Runs on a specific weekday (`mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`).
- `yearly`: Runs on a specific date (`{month: 4, day: 15}`).
- `once: <date>`: Runs exactly once on the specified YYYY-MM-DD string.
