import calendar
from datetime import date, timedelta
import pytest
from lifesim.config import AccountModel, CardAutopaySpec
from lifesim.accounts import AccountManager
from lifesim.ledger import Ledger


def test_monthly_hysa_interest_posting() -> None:
    accounts = {
        "hysa": AccountModel(
            kind="hysa",
            balance=10_000.0,
            annual_growth_rate=0.045,
            interest_posting="monthly",
        )
    }
    manager = AccountManager(accounts, base_seed=42)
    ledger = Ledger()
    sim_start = date(2026, 1, 1)

    for day_index in range(365):
        current_date = sim_start + timedelta(days=day_index)
        manager.process_investment_returns_and_savings(current_date, ledger)

    ending_dollars = manager.balances["hysa"] / 100.0
    # $10,000 at 4.5% APY compounds to $10,450.00 +/- 0.02
    assert ending_dollars == pytest.approx(10_450.0, abs=0.02)
    entries = [record for record in ledger.records if "Monthly Interest" in record["flow"]]
    assert len(entries) == 12


def test_average_cost_basis_on_withdrawal() -> None:
    accounts = {
        "brokerage": AccountModel(
            kind="investment",
            balance=10_000.0,
            initial_cost_basis=10_000.0,
        )
    }
    manager = AccountManager(accounts, base_seed=42)
    # Balance grows from 10,000 to 12,500 (gain = 2,500)
    manager.balances["brokerage"] = 1_250_000
    assert manager.cost_bases["brokerage"] == 1_000_000

    # Withdraw $2,500 (20% of account). Basis removed is $2,000, realized gain is $500.
    manager.record_withdrawal("brokerage", 250_000)
    assert manager.cost_bases["brokerage"] == 800_000
    assert manager.ytd_realized_cap_gains_cents == 50_000


def test_credit_card_grace_period_and_autopay() -> None:
    accounts = {
        "checking": AccountModel(kind="checking", balance=5000.0),
        "card": AccountModel(
            kind="credit_card",
            balance=0.0,
            apr=0.24,
            cashback_pct=0.02,
            statement_day=25,
            due_day=20,
            autopay=CardAutopaySpec(enabled=True, mode="statement_balance", from_account="checking"),
        ),
    }
    manager = AccountManager(accounts, base_seed=42)
    ledger = Ledger()
    sim_start = date(2026, 1, 1)

    # Charge $1,000 on Jan 2
    manager.charge_credit_card("card", 100_000)
    assert manager.balances["card"] == -100_000

    # Run through Feb 26 (past first statement Jan 25 and due date Feb 20)
    for day_index in range(60):
        current_date = sim_start + timedelta(days=day_index)
        manager.accrue_daily_liabilities(current_date)
        manager.process_credit_card_due_date("card", current_date, ledger)
        manager.process_credit_card_statement("card", current_date, ledger)

    # Grace period held: zero interest paid, and card balance paid off by autopay
    assert manager.total_interest_paid_cents == 0
    assert manager.balances["card"] == 0


def test_loan_amortization_to_zero() -> None:
    # $12,000 at 6% APR for 12 months -> monthly payment = $1,032.80 (103_280 cents)
    accounts = {
        "checking": AccountModel(kind="checking", balance=20_000.0),
        "car_loan": AccountModel(
            kind="auto_loan",
            principal=12_000.0,
            apr=0.06,
            term_months=12,
            payment_day=1,
            payment_from_account="checking",
        ),
    }
    manager = AccountManager(accounts, base_seed=42)
    ledger = Ledger()
    assert manager.scheduled_pi_cents["car_loan"] == 103_280

    sim_start = date(2026, 1, 1)
    # Simulate 366 days (1 full year)
    for day_index in range(366):
        current_date = sim_start + timedelta(days=day_index)
        manager.accrue_daily_liabilities(current_date)
        manager.process_loan_payment("car_loan", current_date, ledger)

    # Loan reaches exactly 0 without overpaying
    assert manager.balances["car_loan"] == 0


def test_mortgage_pmi_auto_drop() -> None:
    # $400,000 home with $350,000 loan -> initial LTV = 87.5% (> 78%)
    # PMI drops automatically when LTV <= 78% ($312,000 principal on $400k home)
    accounts = {
        "checking": AccountModel(kind="checking", balance=100_000.0),
        "house_loan": AccountModel(
            kind="mortgage",
            principal=350_000.0,
            asset_value=400_000.0,
            apr=0.06,
            term_months=360,
            pmi_annual_pct=0.006,
            pmi_drop_ltv=0.78,
            payment_day=1,
            extra_monthly_principal=5_000.0,  # Aggressive prepayments to drop PMI fast
        ),
    }
    manager = AccountManager(accounts, base_seed=42)
    ledger = Ledger()
    sim_start = date(2026, 1, 1)

    for day_index in range(250):
        current_date = sim_start + timedelta(days=day_index)
        manager.accrue_daily_liabilities(current_date)
        manager.process_loan_payment("house_loan", current_date, ledger)

    pmi_records = [record for record in ledger.records if "PMI" in record["flow"]]
    # PMI should have fired in early months, but stopped once LTV <= 0.78
    assert len(pmi_records) > 0
    # Current debt is now below 78% of asset value
    assert (-manager.balances["house_loan"]) / manager.asset_values_cents["house_loan"] <= 0.78

def test_529_college_savings_plan() -> None:
    accounts = {
        "checking": AccountModel(kind="checking", balance=10_000.0),
        "college_fund": AccountModel(
            kind="college_529",
            balance=10_000.0,
            initial_cost_basis=8_000.0,
            annual_growth_rate=0.05,
            state_tax_deduction_limit=4_000.0
        )
    }
    manager = AccountManager(accounts, base_seed=42)
    ledger = Ledger()

    # Check deposit adds to contributions
    manager.record_deposit("college_fund", 500_000) # $5,000 contribution
    assert manager.ytd_529_contributions_cents["college_fund"] == 500_000
    assert manager.cost_bases["college_fund"] == 1_300_000 # 8,000 + 5,000

    # Check tax-free investment growth
    sim_start = date(2026, 1, 1)
    for day_index in range(365):
        current_date = sim_start + timedelta(days=day_index)
        manager.process_investment_returns_and_savings(current_date, ledger)

    # Growth occurred
    assert manager.balances["college_fund"] > 1_500_000
    # No tax consequences recorded during growth
    assert manager.ytd_taxable_interest_cents == 0
    assert manager.ytd_realized_cap_gains_cents == 0
    assert manager.ytd_qualified_dividends_cents == 0

    # Check qualified withdrawal
    pre_withdrawal_balance = manager.balances["college_fund"]
    manager.record_withdrawal("college_fund", pre_withdrawal_balance, category="education")
    assert manager.ytd_realized_cap_gains_cents == 0
    assert manager.ytd_529_non_qualified_earnings_cents == 0
    assert manager.balances["college_fund"] == 0

    # Reset and test non-qualified
    manager.balances["college_fund"] = 10_000_00
    manager.cost_bases["college_fund"] = 8_000_00

    manager.record_withdrawal("college_fund", 10_000_00)
    assert manager.ytd_529_non_qualified_earnings_cents == 2_000_00
    assert manager.ytd_realized_cap_gains_cents == 0


def test_529_state_tax_deduction_limit() -> None:
    from lifesim.steps import step_1_macro_rollover
    from lifesim.macro import MacroState
    from lifesim.payroll import PayrollState
    from lifesim.taxes import YearTaxAccumulator

    accounts = {
        "college_fund": AccountModel(
            kind="college_529",
            balance=0.0,
            state_tax_deduction_limit=4_000.0
        )
    }
    manager = AccountManager(accounts, base_seed=42)
    manager.record_deposit("college_fund", 500_000) # Contribute $5,000

    from lifesim.config import InflationModel

    tax_state = YearTaxAccumulator(2026)
    payroll_state = PayrollState(2026)
    macro_state = MacroState(InflationModel(), date(2026, 1, 1))
    prior_tax_states = {}

    # Trigger macro rollover which computes tax deductions
    step_1_macro_rollover(
        day_index=366,
        current_date=date(2027, 1, 1),
        current_tax_year=2026,
        tax_state=tax_state,
        payroll_state=payroll_state,
        accounts_manager=manager,
        prior_year_tax_states=prior_tax_states,
        annual_contributions_ytd={"college_fund": 500_000},
        macro_state=macro_state
    )

    # Verify deduction is capped at 4,000 (400,000 cents)
    archived_tax_state = prior_tax_states[2026]
    assert archived_tax_state.ytd_state_529_deductible_cents == 400_000
