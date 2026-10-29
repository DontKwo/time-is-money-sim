import pytest
from datetime import date
from lifesim.config import ScheduleModel, load_scenario
from lifesim.schedule import should_fire
from lifesim.engine import run

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

import os
from lifesim.config import AmountModel, GasEstimate, GroceryEstimate
from lifesim.amounts import get_amount
import numpy as np

def test_amount_gas_estimate():
    amount = AmountModel(
        gas_estimate=GasEstimate(mpg=25.0, cost_per_gallon=3.5, miles_per_period=250.0)
    )
    val = get_amount(amount)
    assert val == 3500 # 250 / 25 * 3.5 = 35.00 -> 3500 cents

def test_amount_grocery_estimate():
    amount = AmountModel(
        grocery_estimate=GroceryEstimate(people=3, cost_per_person_per_period=100.0)
    )
    val = get_amount(amount)
    assert val == 30000

def test_amount_distributions():
    rng = np.random.default_rng(42)
    amount = AmountModel(normal=[100.0, 10.0])
    val = get_amount(amount, rng)
    # Using fixed seed 42
    assert isinstance(val, int)

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

    # Start balance: 3000
    # Jan 1: Rent -1800 -> 1200
    # Jan 2: Paycheck +2000 -> 3200
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
