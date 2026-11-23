# Frequently Asked Questions

## Assumptions & Models

### 1. What are the core assumptions of the simulator?
The simulator advances one calendar day at a time:
- **Integer Cents**: All internal calculations use integer cents to prevent floating-point rounding drift.
- **Order of Operations**: Each day processes inflows before expenses and automated waterfall transfers to avoid false overdrafts.
- **Inflation**: Optional CPI deflation converts nominal balances into constant purchasing power dollars.
- **Taxes**: Progressive federal, FICA, and capital gains brackets settle on paychecks and April 15 tax reconciliations.

### 2. How do compounding formulas work?
High-yield savings, CDs, and investment accounts compound daily from configured annual return rates and post dividend or interest settlements according to your scenario settings.

### 3. How do I create a custom scenario?
Open any template scenario (such as [example_mvp.yaml](../scenarios/example_mvp.yaml)) inside the Scenario Studio desktop app or inspect all YAML fields in the [Configuration Reference](CONFIG_REFERENCE.md).

### 4. Does the simulator fetch live market data?
No. Everything runs locally on your machine using deterministic parameters from your scenario file.

### 5. Why do balance charts use step lines?
Account charts render step lines (`where='post'`) to show discrete daily cashflow changes instead of interpolating between transaction dates.

## Related Documentation

- [Project Overview](../README.md)
- [User Guide](USER_GUIDE.md)
- [Desktop Installation Guide](INSTALLATION.md)
- [Configuration Reference](CONFIG_REFERENCE.md)
- [System Architecture](ARCHITECTURE.md)
- [Developer Guide](DEVELOPMENT.md)
- [Security Policy](../SECURITY.md)
