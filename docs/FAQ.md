# Frequently Asked Questions

### 1. What are the core assumptions of the simulator?
The simulator operates on a daily tick, processing events day by day. Important assumptions include:
- **Integer Cents**: All internal financial calculations are performed in integer cents to avoid floating-point errors. They are converted to dollars when exporting or displaying.
- **Order of Operations**: On any given day, flows are executed in this order: Income -> Expenses -> Transfers. This prevents premature overdrafting.
- **Inflation**: If `--real-dollars` is used, nominal amounts are deflated based on a cumulative inflation index to represent real purchasing power. By default, scenarios might run in nominal terms unless inflation is explicitly modeled.
- **Taxes**: Tax brackets and rates use simplified progressive/flat structures as configured in the scenario, computed on a year-to-date basis.

### 2. How do compounding formulas work?
Compounding is handled at the account level depending on the configuration. For example, High-Yield Savings Accounts (HYSA) compound based on their `annual_growth_rate` and `interest_posting` schedule (e.g., daily accrual, monthly posting). Investment accounts may apply a daily or monthly return derived from the configured `expected_return` and `volatility`.

### 3. How do I create a custom scenario?
Creating a custom scenario is easy. We recommend copying an existing template (like `scenarios/example_mvp.yaml`) and modifying it to fit your situation.
- You can use the `include` block to pull in standard defaults (like housing or food expenses).
- Define your specific `accounts`, `paychecks`, and `goals`.
- You can find a comprehensive reference of all available YAML configurations in `docs/CONFIG_REFERENCE.md`.

### 4. Can the simulator pull in real-time market data?
No. To comply with licensing rules and prevent dependencies on external systems, the simulator does not pull in proprietary financial data feeds. All returns and volatilities must be statically configured in your YAML file.

### 5. Why are my charts showing "step" lines instead of smooth curves?
The simulator uses `plt.step(where='post')` for visualizing account balances to accurately reflect the daily, discrete nature of transactions, rather than interpolating continuous lines between data points.
