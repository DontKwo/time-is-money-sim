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
