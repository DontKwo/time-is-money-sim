from datetime import date, timedelta
from lifesim.config import PolicyModel, AccountModel
from lifesim.policies import apply_payday_skim, apply_debt_payoff, apply_roth_conversion_ladder, apply_tax_loss_harvesting
from lifesim.accounts import AccountManager
from lifesim.ledger import Ledger
from lifesim.taxes import YearTaxAccumulator, compute_april_settlement_cents
from lifesim.config import TaxConfigModel, TaxBracket
from lifesim.payroll import PayrollState


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


def test_roth_conversion_ladder() -> None:
    policy = PolicyModel(
        name="Roth Conversion",
        kind="roth_conversion_ladder",
        from_account="traditional_401k",
        to_account="roth_ira",
        conversion_amount=12000.0,
        seasoning_years=5,
    )

    accounts = {
        "traditional_401k": AccountModel(kind="traditional_401k", balance=50000.0),
        "roth_ira": AccountModel(kind="roth_ira", balance=0.0),
    }

    manager = AccountManager(accounts, base_seed=42)
    manager.balances = {"traditional_401k": 5000000, "roth_ira": 0}

    ledger = Ledger()
    payroll_state = PayrollState(2026)

    current_date = date(2026, 12, 1)

    apply_roth_conversion_ladder(
        policy,
        manager.balances,
        ledger,
        current_date,
        payroll_state,
        manager
    )

    # Verify balance transfer (12k dollars = 1.2M cents)
    assert manager.balances["traditional_401k"] == 3800000
    assert manager.balances["roth_ira"] == 1200000

    # Verify taxable event
    assert payroll_state.ytd_taxable_ordinary_cents == 1200000

    # Verify seasoned buckets tracking
    assert len(manager.roth_conversion_seasoning) == 1
    assert manager.roth_conversion_seasoning[0] == (current_date, 1200000)

    # Test conversion limits (available < conversion_amount)
    manager.balances["traditional_401k"] = 500000 # Only 5k left
    manager.balances["roth_ira"] = 1200000

    current_date_2 = date(2027, 12, 1)

    apply_roth_conversion_ladder(
        policy,
        manager.balances,
        ledger,
        current_date_2,
        payroll_state,
        manager
    )

    # Should only transfer available 5k
    assert manager.balances["traditional_401k"] == 0
    assert manager.balances["roth_ira"] == 1700000
    assert payroll_state.ytd_taxable_ordinary_cents == 1700000

    # Seasoning bucket should only record the 5k transfer
    assert len(manager.roth_conversion_seasoning) == 2
    assert manager.roth_conversion_seasoning[1] == (current_date_2, 500000)


def test_tax_loss_harvesting_and_carryforward() -> None:
    policy = PolicyModel(
        name="TLH",
        kind="tax_loss_harvesting",
        target_accounts=["brokerage"]
    )

    accounts = {
        "brokerage": AccountModel(kind="investment", balance=15000.0)
    }

    manager = AccountManager(accounts, base_seed=42)
    manager.balances = {"brokerage": 10_000_000} # Current balance is $100k
    manager.cost_bases = {"brokerage": 15_000_000} # Cost basis is $150k (Loss of $50k)

    ledger = Ledger()
    current_date = date(2026, 12, 1)

    # 1. Harvest the loss
    harvested = apply_tax_loss_harvesting(policy, manager.balances, ledger, current_date, manager)

    # Should have harvested the full $50k loss (5_000_000 cents)
    assert harvested == 5_000_000
    assert manager.ytd_realized_cap_losses_cents == 5_000_000
    assert manager.balances["brokerage"] == 10_000_000
    assert manager.cost_bases["brokerage"] == 10_000_000 # Cost basis resets to current balance

    # 2. Simulate tax settlement to test $3,000 deduction limit and carryforward
    tax_state = YearTaxAccumulator(2026)
    tax_state.ytd_realized_cap_losses_cents = manager.ytd_realized_cap_losses_cents
    tax_state.ytd_taxable_ordinary_cents = 100_000_000 # $100k ordinary income

    tax_config = TaxConfigModel(
        enabled=True,
        filing_status="single",
        standard_deduction=0.0, # Zero to simplify math
        federal_brackets=[TaxBracket(rate=0.10, threshold=0.0)],
        state_brackets=[]
    )

    compute_april_settlement_cents(tax_state, tax_config)

    # Out of $50k loss, $3k should be deducted, $47k carried forward
    assert tax_state.carryforward_cap_losses_cents == 4_700_000
