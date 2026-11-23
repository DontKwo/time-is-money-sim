# System Architecture

Life Money Simulator processes personal cashflows, accounts, payroll deductions, taxes, policies, debt payoff strategies, life events, and stochastic Monte Carlo runs one calendar day at a time.

## Acyclic Module Layers

1. **Deterministic PRNG (`lifesim/rng.py`)**: Derives isolated `np.random.Generator` streams using `derive_rng(base_seed, namespace, name)` with SHA-256 digests so modifying one flow or event leaves unrelated streams unchanged.
2. **Configuration (`lifesim/config.py`)**: Validates YAML files with Pydantic v2 (`ScenarioModel`, `AccountModel`, `FlowModel`, `PaycheckModel`, `PolicyModel`, `EventModel`, `GoalModel`) and resolves `include` merges, `exclude` lists, and runtime `--set` overrides.
3. **Calendar & Amounts (`lifesim/schedule.py`, `lifesim/amounts.py`, `lifesim/macro.py`)**: Precomputes recurrence fire counts (`daily`, `weekly`, `biweekly`, `semimonthly`, `monthly`, `nth_weekday`, `quarterly`, `yearly`, `once`) with US holiday and weekend rules, CPI inflation indices, and stochastic draw distributions.
4. **Subsystems (`lifesim/accounts.py`, `taxes.py`, `payroll.py`, `policies.py`, `events.py`, `goals.py`)**: Models HYSA/CD interest, investments with dividend reinvestment, credit cards, amortized loans, progressive federal/FICA/capital gains brackets, 401(k)/HSA matching, waterfall sweeps, avalanche/snowball debt payoff, and milestone tracking.
5. **12-Step Simulation Engine (`lifesim/steps.py`, `lifesim/engine.py`, `lifesim/ledger.py`)**: Executes `step_1_macro_rollover` through `step_12_snapshot_and_goals` per day, recording cent-exact transactions and daily snapshots into `Ledger`.
6. **Analytics & Plotting (`lifesim/analysis.py`, `montecarlo.py`, `compare.py`, `sensitivity.py`, `plots.py`, `report.py`)**: Computes summaries, Monte Carlo fan percentiles, multi-scenario comparisons, parameter sensitivity sweeps, and Matplotlib charts.
7. **Interfaces (`lifesim/cli.py`, `lifesim/gui.py`)**: Exposes both CLI flags and the cross-platform loopback HTTP WebView desktop studio with `--self-test` verification.

## Integer-Cent & Sign Conventions

- Dollar inputs in YAML are converted to integer cents (`int(round(dollars * 100.0))`) at load boundaries.
- Fractional daily compounding interest and investment remainders accumulate in floating-point remainder maps and settle into integer cents when posted.
- Asset accounts hold positive cents when funded; liability accounts hold negative cents (`-principal_cents`) when debt is owed so `sum(balances.values())` yields net financial wealth directly.

## Related Documentation

- [Project Overview](../README.md)
- [User Guide](USER_GUIDE.md)
- [Configuration Reference](CONFIG_REFERENCE.md)
- [Developer Guide](DEVELOPMENT.md)
- [AI Agent Reference](../AGENTS.md)
- [Security Policy](../SECURITY.md)
