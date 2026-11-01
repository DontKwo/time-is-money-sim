from datetime import date, timedelta
from lifesim.config import PolicyModel, AccountModel
from lifesim.policies import apply_payday_skim, apply_debt_payoff
from lifesim.accounts import AccountManager
from lifesim.ledger import Ledger


def test_ira_cap_overflow_to_brokerage() -> None:
    policy = PolicyModel(
        name="Auto IRA",
        kind="payday_skim",
        from_account="checking",
        to_account="roth_ira",
        fixed_amount=1000.0,
        respect_annual_limit=True,
        overflow_to_account="brokerage",
    )
    accounts = {
        "checking": AccountModel(kind="checking", balance=20_000.0),
        "roth_ira": AccountModel(kind="roth_ira", balance=0.0, annual_contribution_limit=7000.0),
        "brokerage": AccountModel(kind="investment", balance=0.0),
    }
    balances = {"checking": 2_000_000, "roth_ira": 0, "brokerage": 0}
    annual_contributions = {}
    ledger = Ledger()

    # Skim $1,000 each month for 12 months
    for month_index in range(1, 13):
        current_date = date(2026, month_index, 1)
        apply_payday_skim(
            policy,
            100_000,
            balances,
            ledger,
            current_date,
            accounts,
            annual_contributions,
        )

    # First 7 months deposit $7,000 into roth_ira; remaining 5 months route $5,000 into brokerage
    assert balances["roth_ira"] == 700_000
    assert balances["brokerage"] == 500_000
    assert balances["checking"] == 800_000


def test_avalanche_vs_snowball_debt_payoff() -> None:
    # Debt 1: $2,000 at 8% APR. Debt 2: $5,000 at 22% APR.
    # Total monthly debt budget is $800.
    budget = 800.0

    def run_strategy(strategy_name: str) -> int:
        accounts = {
            "checking": AccountModel(kind="checking", balance=20_000.0),
            "low_apr_small": AccountModel(kind="loan", principal=2000.0, apr=0.08, term_months=36),
            "high_apr_large": AccountModel(kind="credit_card", principal=5000.0, apr=0.22),
        }
        manager = AccountManager(accounts, base_seed=42)
        policy = PolicyModel(
            name="Debt Attack",
            kind="debt_payoff",
            from_account="checking",
            strategy=strategy_name,
            target_accounts=["low_apr_small", "high_apr_large"],
            total_monthly_budget=budget,
            extra_payment=0.0,
            keep_checking_buffer=0.0,
        )
        ledger = Ledger()

        # Simulate 12 months (365 days)
        sim_start = date(2026, 1, 1)
        for day_index in range(365):
            current_date = sim_start + timedelta(days=day_index)
            # Accrue daily interest on active debts
            manager.accrue_daily_liabilities(current_date)
            manager.process_loan_payment("low_apr_small", current_date, ledger)
            manager.process_credit_card_due_date("high_apr_large", current_date, ledger)
            manager.process_credit_card_statement("high_apr_large", current_date, ledger)

            # On the 26th of each month, apply debt payoff policy
            if current_date.day == 26:
                monthly_payments = {}
                apply_debt_payoff(
                    policy,
                    manager.balances,
                    ledger,
                    current_date,
                    accounts,
                    monthly_payments,
                )

        return manager.total_interest_paid_cents

    interest_avalanche = run_strategy("avalanche")
    interest_snowball = run_strategy("snowball")

    # Avalanche targets the 22% APR card first, so total interest paid must be strictly less
    assert interest_avalanche < interest_snowball
