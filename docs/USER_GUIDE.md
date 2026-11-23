# User Guide

Life Money Simulator models daily cashflows, retirement accounts, credit cards, amortized loans, taxes, waterfall savings policies, Monte Carlo uncertainty, and sensitivity sweeps locally on your computer.

## Desktop Application Workflow

1. Launch **TimeIsMoneySim** (see [Desktop Installation Guide](INSTALLATION.md) if your operating system prompts for verification).
2. **Choose a Scenario**: Pick a built-in template (such as `example_mvp.yaml`, `example_401k_match.yaml`, `example_debt_payoff.yaml`, or `example_fire_lifecycle.yaml`) from the **Scenario Studio** selector.
3. **Adjust Horizon & Inflation**: Override the number of days or inflation rate right in the top bar without editing YAML files manually.
4. **Run Simulation, Monte Carlo, or Sensitivity**:
   - **Run Simulation**: Calculates ending net worth, liquid assets, total debt, goal attainment, account balance curves, and monthly cashflow charts.
   - **Monte Carlo**: Runs stochastic market trials and plots p5 through p95 fan bands.
   - **Sensitivity Sweep**: Measures net worth upside and downside across key financial levers on a tornado chart.
5. **Export Data**: Download the simulated transaction ledger as CSV for external inspection.

## Financial Disclaimer

Life Money Simulator is an educational modeling tool only. Verify outputs independently before making personal financial or tax decisions.

## Related Documentation

- [Project Overview](../README.md)
- [Desktop Installation Guide](INSTALLATION.md)
- [Configuration Reference](CONFIG_REFERENCE.md)
- [Frequently Asked Questions](FAQ.md)
- [System Architecture](ARCHITECTURE.md)
- [Developer Guide](DEVELOPMENT.md)
- [Security Policy](../SECURITY.md)
