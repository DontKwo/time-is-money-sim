import pytest
import pandas as pd
from datetime import date
from lifesim.ledger import Ledger

def test_ledger_initialization():
    ledger = Ledger()
    assert ledger.records == []

def test_ledger_append_single():
    ledger = Ledger()
    tx_date = date(2026, 1, 1)

    ledger.append(
        tx_date=tx_date,
        flow_name="Rent",
        amount=-150000,
        account="checking",
        balance=350000
    )

    assert len(ledger.records) == 1
    record = ledger.records[0]

    assert record['date'] == tx_date
    assert record['flow'] == "Rent"
    assert record['amount'] == -1500.0
    assert record['account'] == "checking"
    assert record['balance'] == 3500.0

def test_ledger_append_multiple():
    ledger = Ledger()

    ledger.append(date(2026, 1, 1), "Rent", -150000, "checking", 350000)
    ledger.append(date(2026, 1, 15), "Salary", 200000, "checking", 550000)

    assert len(ledger.records) == 2
    assert ledger.records[0]['flow'] == "Rent"
    assert ledger.records[1]['flow'] == "Salary"

def test_ledger_to_df_empty():
    ledger = Ledger()
    df = ledger.to_df()

    assert isinstance(df, pd.DataFrame)
    assert df.empty

def test_ledger_to_df_populated():
    ledger = Ledger()

    tx_date_1 = date(2026, 1, 1)
    tx_date_2 = date(2026, 1, 15)

    ledger.append(tx_date_1, "Rent", -150000, "checking", 350000)
    ledger.append(tx_date_2, "Salary", 200000, "checking", 550000)

    df = ledger.to_df()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2

    # Check columns exist
    expected_columns = ['date', 'flow', 'amount', 'account', 'balance']
    for col in expected_columns:
        assert col in df.columns

    # Check values
    assert df.iloc[0]['flow'] == "Rent"
    assert df.iloc[0]['amount'] == -1500.0
    assert df.iloc[1]['flow'] == "Salary"
    assert df.iloc[1]['balance'] == 5500.0
