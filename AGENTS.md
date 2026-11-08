# AI Agent Operational Reference

## Simulation State Engine
- The simulation engine uses a daily-tick mechanism to increment time, moving from the start date up through `days` (or the end date).
- The state evolves based on `scenario.accounts`, `scenario.flows`, `events`, `taxes`, and `policies`.
- Flows generate income, expense, or transfers according to schedules and amounts.
- Flow types are processed in order: income first, then expense, then transfers, to prevent premature overdrafts.

## Mathematical Models
- **Inflation**: The `real-dollars` mode uses the cumulative inflation index (via `InflationConfigModel.rate`) to adjust nominal ledger amounts down to real purchasing power.
- **Opportunity Cost**: Opportunity cost is modeled implicitly through alternative investments (e.g., keeping money in a low-interest checking account vs. transferring excess to a higher-yield brokerage or HYSA). The `excess_sweep` and `debt_payoff` policies automatically route cash to maximize returns or minimize interest based on configured rates.

## Parameter Schema
- Scenarios are validated via Pydantic (`ScenarioModel`, `FlowModel`, `AccountModel`, etc.)
- YAML configuration supports various estimators (`gas_estimate`, `grocery_estimate`, etc.) and statistical distributions (`normal`, `uniform`, etc.).

## Testing Commands and Invariants
- **Tests**: Use `uv run pytest`. All tests must pass with exit code 0.
- **Linter**: Assume linter checks strict type annotations on all function signatures, and limits comments to 2 lines or fewer.
- **Financial Calculations**: Done in integer cents.
- **Randomness**: Deterministic using per-flow seeds.
