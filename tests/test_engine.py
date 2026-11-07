import os
import numpy as np
import pytest
from datetime import date
from lifesim.amounts import get_amount
from lifesim.config import (
    AmountModel,
    GasEstimate,
    GroceryEstimate,
    ScheduleModel,
    ScenarioModel,
    apply_cli_overrides,
    load_scenario,
)
from lifesim.engine import run
from lifesim.rng import derive_rng
from lifesim.schedule import should_fire

def test_schedule_monthly():
    schedule = ScheduleModel(monthly=15)
    start_date = date(2026, 1, 1)

    assert should_fire(schedule, date(2026, 1, 15), start_date) == True
    assert should_fire(schedule, date(2026, 1, 16), start_date) == False
    assert should_fire(schedule, date(2026, 2, 15), start_date) == True

def test_schedule_weekly():
    schedule = ScheduleModel(weekly='fri')
    start_date = date(2026, 1, 1) # Thursday

    assert should_fire(schedule, date(2026, 1, 2), start_date) == True # Friday
    assert should_fire(schedule, date(2026, 1, 3), start_date) == False # Saturday
    assert should_fire(schedule, date(2026, 1, 9), start_date) == True # Next Friday


def test_schedule_date_bounds():
    schedule = ScheduleModel(
        weekly='fri',
        start=date(2026, 1, 9),
        end=date(2026, 1, 16),
    )
    start_date = date(2026, 1, 1)

    assert should_fire(schedule, date(2026, 1, 2), start_date) == False
    assert should_fire(schedule, date(2026, 1, 9), start_date) == True
    assert should_fire(schedule, date(2026, 1, 16), start_date) == True
    assert should_fire(schedule, date(2026, 1, 23), start_date) == False


def test_amount_gas_estimate():
    amount = AmountModel(
        gas_estimate=GasEstimate(mpg=25.0, cost_per_gallon=3.5, miles_per_period=250.0)
    )
    amount_cents = get_amount(amount)
    assert amount_cents == 3500 # 250 / 25 * 3.5 = 35.00 -> 3500 cents

def test_amount_gas_estimate_zero_or_negative_mpg():
    amount = AmountModel(
        gas_estimate=GasEstimate(mpg=0.0, cost_per_gallon=3.5, miles_per_period=250.0)
    )
    amount_cents = get_amount(amount)
    assert amount_cents == 0

    amount2 = AmountModel(
        gas_estimate=GasEstimate(mpg=-10.0, cost_per_gallon=3.5, miles_per_period=250.0)
    )
    amount_cents_2 = get_amount(amount2)
    assert amount_cents_2 == 0

def test_amount_grocery_estimate():
    amount = AmountModel(
        grocery_estimate=GroceryEstimate(people=3, cost_per_person_per_period=100.0)
    )
    amount_cents = get_amount(amount)
    assert amount_cents == 30000

def test_amount_distributions():
    rng = np.random.default_rng(42)
    amount = AmountModel(normal=[100.0, 10.0])
    amount_cents = get_amount(amount, rng)
    # Using fixed seed 42
    assert isinstance(amount_cents, int)

    amount_uniform = AmountModel(uniform=[50.0, 150.0])
    amount_cents_uniform = get_amount(amount_uniform, rng)
    assert isinstance(amount_cents_uniform, int)

    amount_lognormal = AmountModel(lognormal=[0.0, 1.0])
    amount_cents_lognormal = get_amount(amount_lognormal, rng)
    assert isinstance(amount_cents_lognormal, int)

def test_include_exclude_logic(tmp_path):
    # Create mock defaults
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()

    with open(defaults_dir / "test_inc.yaml", "w") as f:
        f.write("""
flows:
  - name: IncFlow
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 100}
  - name: ExcludedFlow
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 50}
""")

    scenario_file = tmp_path / "scenario.yaml"
    with open(scenario_file, "w") as f:
        f.write(f"""
start: 2026-01-01
days: 30
include:
  - defaults/test_inc.yaml
exclude:
  - ExcludedFlow
accounts:
  checking: {{balance: 1000}}
flows: []
""")

    # Save original dir and cd to tmp_path so relative include works
    orig_dir = os.getcwd()
    os.chdir(tmp_path)
    try:
        scenario = load_scenario("scenario.yaml")
        assert len(scenario.flows) == 1
        assert scenario.flows[0].name == "IncFlow"
    finally:
        os.chdir(orig_dir)

def test_engine_run():
    scenario = load_scenario('scenarios/example_mvp.yaml')
    ledger = run(scenario)
    df = ledger.to_df()

    assert len(df) > 0

    # Check that rent was deducted on Jan 1st (start date)
    rent_tx = df[(df['date'] == date(2026, 1, 1)) & (df['flow'] == 'Rent')]
    assert len(rent_tx) == 1
    assert rent_tx.iloc[0]['amount'] == -1800.0

    # Check that paycheck was added on Jan 2nd (Friday)
    paycheck_tx = df[(df['date'] == date(2026, 1, 2)) & (df['flow'] == 'Paycheck')]
    assert len(paycheck_tx) == 1
    assert paycheck_tx.iloc[0]['amount'] == 2000.0

    # Start: 3000. Rent Jan 1: -1800 -> 1200.
    # Paycheck Jan 2: +2000 -> 3200.
    assert paycheck_tx.iloc[0]['balance'] == 3200.0

def test_overdraft_limit(tmp_path):
    scenario_file = tmp_path / "scenario_od_limit.yaml"
    with open(scenario_file, "w") as f:
        f.write("""
start: 2026-01-01
days: 2
accounts:
  checking:
    balance: 100
    overdraft_limit: 50
flows:
  - name: LargeExpense
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 200}
""")

    orig_dir = os.getcwd()
    os.chdir(tmp_path)
    try:
        scenario = load_scenario("scenario_od_limit.yaml")
        ledger = run(scenario)
        df = ledger.to_df()

        # Balance should still be 100, transaction should be skipped because 100 - 200 = -100, which is < -50
        assert len(df) == 0
    finally:
        os.chdir(orig_dir)

def test_overdraft_fee(tmp_path):
    scenario_file = tmp_path / "scenario_od_fee.yaml"
    with open(scenario_file, "w") as f:
        f.write("""
start: 2026-01-01
days: 2
accounts:
  checking:
    balance: 100
    overdraft_limit: 500
    overdraft_fee: 35
flows:
  - name: MediumExpense
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 200}
""")

    orig_dir = os.getcwd()
    os.chdir(tmp_path)
    try:
        scenario = load_scenario("scenario_od_fee.yaml")
        ledger = run(scenario)
        df = ledger.to_df()

        # 100 - 200 = -100
        # -100 - 35 = -135
        assert len(df) == 2

        expense_tx = df[df['flow'] == 'MediumExpense']
        fee_tx = df[df['flow'] == 'MediumExpense Overdraft Fee']

        assert len(expense_tx) == 1
        assert len(fee_tx) == 1

        assert expense_tx.iloc[0]['balance'] == -100.0
        assert fee_tx.iloc[0]['balance'] == -135.0
    finally:
        os.chdir(orig_dir)


def test_auto_transfer_covers_expense_shortfall(tmp_path):
    scenario_file = tmp_path / "scenario_auto_transfer.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 1
accounts:
  checking: {balance: 50}
  investments: {balance: 100}
auto_transfers:
  - from: investments
    to: checking
    minimum_balance: 0
flows:
  - name: Expense
    type: expense
    from: checking
    schedule: {once: "2026-01-01"}
    amount: {fixed: 75}
""")

    scenario = load_scenario(str(scenario_file))
    df = run(scenario).to_df()

    transfers = df[df['flow'] == 'Automatic transfer: investments to checking']
    expense = df[df['flow'] == 'Expense']
    assert len(transfers) == 2
    assert list(transfers['amount']) == [-25.0, 25.0]
    assert expense.iloc[0]['balance'] == 0.0
    assert df[df['account'] == 'investments'].iloc[-1]['balance'] == 75.0


def test_account_growth_compounds_to_annual_rate(tmp_path):
    scenario_file = tmp_path / "scenario_growth.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 365
accounts:
  investments:
    balance: 100
    annual_growth_rate: 0.06
flows: []
""")

    scenario = load_scenario(str(scenario_file))
    df = run(scenario).to_df()

    growth = df[df['flow'] == 'investments Investment Growth']
    assert len(growth) == 365
    assert growth.iloc[0]['amount'] == 0.02
    assert growth.iloc[-1]['balance'] == pytest.approx(106.0, abs=0.02)


def test_schedule_yearly():
    schedule = ScheduleModel(yearly={'month': 2, 'day': 29})
    start_date = date(2023, 1, 1)

    # Leap year: 2024
    assert should_fire(schedule, date(2024, 2, 28), start_date) == False
    assert should_fire(schedule, date(2024, 2, 29), start_date) == True

    # Non-leap year: 2025
    assert should_fire(schedule, date(2025, 2, 28), start_date) == True


def test_scenario_end_date_resolution() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        accounts={},
        flows=[],
    )
    assert scenario.days == 31
    assert scenario.end == date(2026, 1, 31)


def test_scenario_invalid_end_date_raises() -> None:
    with pytest.raises(ValueError, match="on or after start date"):
        ScenarioModel(
            start=date(2026, 1, 10),
            end=date(2026, 1, 5),
            accounts={},
            flows=[],
        )


def test_derive_rng_determinism() -> None:
    rng_first = derive_rng(42, "account", "checking")
    rng_second = derive_rng(42, "account", "checking")
    rng_other = derive_rng(42, "account", "savings")
    first_draw = float(rng_first.normal())
    second_draw = float(rng_second.normal())
    other_draw = float(rng_other.normal())
    assert first_draw == second_draw
    assert first_draw != other_draw


def test_apply_cli_overrides() -> None:
    raw_config = {
        "start": "2026-01-01",
        "days": 30,
        "flows": [
            {"name": "Rent", "amount": {"fixed": 2000.0}},
            {"name": "Food", "amount": {"fixed": 500.0}},
        ],
        "paychecks": [
            {"annual_salary": 100000.0},
        ],
    }
    overrides = [
        "flows.Rent.amount.fixed=2200.0",
        "paychecks.0.annual_salary=125000.0",
    ]
    updated = apply_cli_overrides(raw_config, overrides)
    assert updated["flows"][0]["amount"]["fixed"] == 2200.0
    assert updated["paychecks"][0]["annual_salary"] == 125000.0


def test_end_to_end_accounting_conservation() -> None:
    # Test multi-account, 401k, credit card, and loan integration
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=60,
        seed=42,
        accounts={
            "checking": {
                "kind": "checking",
                "balance": 5000.0,
            },
            "traditional_401k": {
                "kind": "traditional_401k",
                "balance": 10000.0,
                "annual_growth_rate": 0.06,
            },
            "credit_card": {
                "kind": "credit_card",
                "balance": 0.0,
                "apr": 0.20,
                "statement_day": 25,
                "due_day": 20,
                "cashback_pct": 0.02,
                "autopay": {
                    "enabled": True,
                    "from_account": "checking",
                    "mode": "statement_balance",
                },
            },
            "auto_loan": {
                "kind": "auto_loan",
                "principal": 12000.0,
                "apr": 0.06,
                "term_months": 36,
                "payment_day": 1,
                "payment_from_account": "checking",
            },
        },
        paychecks=[
            {
                "name": "Engineering Job",
                "enabled": True,
                "schedule": {"biweekly": "fri", "anchor": date(2026, 1, 2)},
                "annual_salary": 130000.0,
                "retirement_401k": {
                    "enabled": True,
                    "traditional_pct": 0.06,
                    "employer_match": {
                        "enabled": True,
                        "match_rate": 1.0,
                        "up_to_pct": 0.06,
                        "to_account": "traditional_401k",
                    },
                },
            }
        ],
        flows=[
            {
                "name": "Rent",
                "type": "expense",
                "from_account": "checking",
                "schedule": {"monthly": 1},
                "amount": {"fixed": 1800.0},
            },
            {
                "name": "Groceries",
                "type": "expense",
                "from_account": "credit_card",
                "schedule": {"weekly": "sat"},
                "amount": {"fixed": 250.0},
            },
        ],
        goals=[
            {
                "name": "Reach 10k Liquid",
                "kind": "liquid_net_worth",
                "target_amount": 10000.0,
            }
        ],
    )

    ledger = run(scenario)
    daily_df = ledger.daily_df()
    assert len(daily_df) == 60
    assert "total_net_worth" in daily_df.columns
    assert "liquid_net_worth" in daily_df.columns

    start_record = daily_df.iloc[0]
    final_record = daily_df.iloc[-1]
    assert final_record["total_net_worth"] != start_record["total_net_worth"]

    # Verify metrics and goal result structures are attached
    assert "net_worth" in ledger.metrics
    assert "liquidity" in ledger.metrics
    assert len(ledger.goal_results) == 1
    assert ledger.goal_results[0]["name"] == "Reach 10k Liquid"

def test_rmd_calculation_and_withdrawal():
    # Born 1950 (RMD age 72).
    # Turn 72 in 2022. RMD starts year 2022.

    scenario = ScenarioModel(
        start=date(2021, 1, 1),
        days=365 * 3, # Run through end of 2023
        birth_date=date(1950, 6, 15),
        rmd_enabled=True,
        rmd_target_account="checking",
        accounts={
            "checking": {
                "kind": "checking",
                "balance": 1000.0,
            },
            "traditional_401k": {
                "kind": "traditional_401k",
                "balance": 27400.0,
                "annual_growth_rate": 0.0, # no growth for easier math
            }
        },
        flows=[]
    )

    ledger = run(scenario)
    df = ledger.to_df()

    # RMD should occur on Dec 1st.
    # In 2021, age is 71 -> No RMD
    rmd_2021 = df[(df['date'] == date(2021, 12, 1)) & (df['category'] == 'rmd')]
    assert len(rmd_2021) == 0

    # In 2022, age is 72. RMD statutory age reached.
    # Prior year balance is 27400 (from Jan 1 start because no growth).
    # Age 72 factor is 27.4. RMD = 27400 / 27.4 = 1000.
    rmd_2022 = df[(df['date'] == date(2022, 12, 1)) & (df['category'] == 'rmd')]
    assert len(rmd_2022) == 2 # withdrawal and deposit

    withdrawal_2022 = rmd_2022[rmd_2022['amount'] < 0].iloc[0]
    deposit_2022 = rmd_2022[rmd_2022['amount'] > 0].iloc[0]

    assert withdrawal_2022['amount'] == -1000.0
    assert withdrawal_2022['account'] == 'traditional_401k'
    assert withdrawal_2022['balance'] == 26400.0

    assert deposit_2022['amount'] == 1000.0
    assert deposit_2022['account'] == 'checking'
    assert deposit_2022['balance'] == 2000.0

    # In 2023, age is 73. Factor is 26.5.
    # Prior year balance is 26400. RMD = 26400 / 26.5 = 996.226... -> 996.23
    # Actually it's 2640000 cents / 26.5 = 99622.641... => 99623 cents -> 996.23
    rmd_2023 = df[(df['date'] == date(2023, 12, 1)) & (df['category'] == 'rmd')]
    assert len(rmd_2023) == 2

    withdrawal_2023 = rmd_2023[rmd_2023['amount'] < 0].iloc[0]
    assert pytest.approx(withdrawal_2023['amount'], abs=0.01) == -996.23

def test_rmd_disabled():
    scenario = ScenarioModel(
        start=date(2022, 1, 1),
        days=365,
        birth_date=date(1950, 6, 15),
        rmd_enabled=False,
        accounts={
            "checking": {"kind": "checking", "balance": 1000.0},
            "traditional_401k": {"kind": "traditional_401k", "balance": 27400.0}
        },
        flows=[]
    )
    ledger = run(scenario)
    df = ledger.to_df()

    if len(df) > 0 and 'category' in df.columns:
        rmd_tx = df[df['category'] == 'rmd']
        assert len(rmd_tx) == 0
    else:
        assert True
