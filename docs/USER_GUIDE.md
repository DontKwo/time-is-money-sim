# User Guide

Life Money Simulator models daily cashflows, retirement accounts, credit cards, amortized loans, taxes, waterfall savings policies, Monte Carlo uncertainty, and sensitivity sweeps locally on your computer.

## Desktop Application Workflow

1. Launch **TimeIsMoneySim** (see [Desktop Installation Guide](INSTALLATION.md) if your operating system prompts for verification).
2. **Dashboard Tab**: Pick a built-in template (`MVP`, `401k Match`, `Debt Payoff`, or `FIRE Lifecycle`), set the projection **Days** horizon, and click:
   - **Run Simulation**: Calculates ending net worth, liquid assets, total debt, goal attainment, account balance curves, net worth stacked charts, and monthly cashflow charts.
   - **Monte Carlo**: Runs stochastic market trials and plots p5 through p95 fan bands under **Monte Carlo / Tornado**.
   - **Sensitivity**: Measures net worth upside and downside across financial parameters on a tornado chart.
   - **Export CSV / Export PNG**: Downloads the simulated daily transaction ledger or active chart image locally.
3. **Scenario Studio Tab**: Visually edit accounts, paychecks, recurring cashflows, life events, and policies, load or import `.yaml` templates, download edited `.yaml` configs, and run custom projections directly.
4. **Compare Scenarios Tab**: Benchmark a baseline strategy against an alternative scenario side by side.

## Related Documentation

- [Project Overview](../README.md)
- [Desktop Installation Guide](INSTALLATION.md)
- [Configuration Reference](CONFIG_REFERENCE.md)
- [Frequently Asked Questions](FAQ.md)
- [System Architecture](ARCHITECTURE.md)
- [Developer Guide](DEVELOPMENT.md)
- [Security Policy](../SECURITY.md)

## Financial Disclaimer

Life Money Simulator is an educational modeling tool only. Verify outputs independently before making personal financial or tax decisions.
