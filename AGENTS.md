# AI Agent Operational Reference

## Architecture & Invariants

Life Money Simulator (`lifesim`) is a deterministic, daily-tick personal finance simulation engine with a WebView desktop application (`lifesim/gui.py`):

- **Acyclic Module Graph**: `rng` -> `config` -> `macro` / `schedule` / `amounts` -> `accounts` / `taxes` / `payroll` / `policies` / `events` / `goals` -> `ledger` -> `steps` -> `engine` -> `analysis` / `montecarlo` / `compare` / `sensitivity` / `plots` -> `cli` / `gui`.
- **Integer-Cent Accounting**: All currency balances, transactions, loan principals, limits, and YTD accumulators are stored as `int` cents (`$100.00 -> 10000`). Asset accounts carry positive balances when funded; liability accounts (`credit_card`, `loan`, `mortgage`, `student_loan`, `auto_loan`) hold negative balances when debt is owed so total financial net worth equals `sum(balances.values())`.
- **Daily Order of Operations**: Each simulated calendar date advances through the 12 ordered functions in `lifesim/steps.py` (`step_1_macro_rollover` through `step_12_snapshot_and_goals`), processing inflows before expenses and automated waterfall transfers to avoid false overdrafts.
- **RNG Stream Isolation**: Every random generator uses `derive_rng(base_seed, namespace, name)` backed by SHA-256 so adding or toggling one flow or event never shifts draws on another stream.
- **Desktop GUI (`lifesim/gui.py`)**: Stdlib loopback HTTP server serving the Scenario Studio and Analytics UI, rendering live Matplotlib charts cleanly and supporting `--self-test` and `--screenshot`.

## Rules & Commands

- Annotate every function signature (parameters and return type) and keep comments concise (<= 2 lines).
- Run tests with `uv run --no-project --python ".venv/Scripts/python.exe" python -m pytest`.
- Run strict linter (`claudemd_linter.py . --level strict --full`) and `link_checker.py .` before committing.

## Related Documentation

- [Project Overview](README.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [User Guide](docs/USER_GUIDE.md)
- [Developer Guide](docs/DEVELOPMENT.md)
- [Security Policy](SECURITY.md)
