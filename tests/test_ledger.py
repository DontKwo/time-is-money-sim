from pathlib import Path
import json
import pytest
import pandas as pd
from datetime import date
from lifesim.ledger import Ledger

def test_ledger_initialization() -> None:
    ledger = Ledger()
    assert ledger.records == []

def test_ledger_append_single() -> None:
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

def test_ledger_append_multiple() -> None:
    ledger = Ledger()

    ledger.append(date(2026, 1, 1), "Rent", -150000, "checking", 350000)
    ledger.append(date(2026, 1, 15), "Salary", 200000, "checking", 550000)

    assert len(ledger.records) == 2
    assert ledger.records[0]['flow'] == "Rent"
    assert ledger.records[1]['flow'] == "Salary"

def test_ledger_to_df_empty() -> None:
    ledger = Ledger()
    df = ledger.to_df()

    assert isinstance(df, pd.DataFrame)
    assert df.empty

def test_ledger_to_df_populated() -> None:
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


def test_ledger_export_jsonl(tmp_path: Path) -> None:
    ledger = Ledger()
    tx_date_1 = date(2026, 1, 1)
    tx_date_2 = date(2026, 1, 15)

    ledger.append(
        tx_date=tx_date_1,
        flow_name="Rent",
        amount=-150000,
        account="checking",
        balance=350000,
        category="housing",
        tx_kind="flow",
    )
    ledger.append(
        tx_date=tx_date_2,
        flow_name="Salary",
        amount=250000,
        account="checking",
        balance=600000,
        category="income",
        tx_kind="flow",
    )
    ledger.daily_records.append({
        "date": tx_date_1,
        "checking": 3500.0,
        "total_net_worth": 3500.0,
    })
    ledger.daily_records.append({
        "date": tx_date_2,
        "checking": 6000.0,
        "total_net_worth": 6000.0,
    })

    jsonl_file = tmp_path / "ledger.jsonl"
    daily_jsonl_file = tmp_path / "daily.jsonl"

    ledger.export_jsonl(str(jsonl_file), daily_filepath=str(daily_jsonl_file))

    lines = [json.loads(line) for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n")]
    assert len(lines) == 2

    assert lines[0]["date"] == "2026-01-01"
    assert lines[0]["flow"] == "Rent"
    assert lines[0]["amount"] == -1500.0
    assert lines[0]["account"] == "checking"
    assert lines[0]["balance"] == 3500.0
    assert lines[0]["category"] == "housing"
    assert lines[0]["tx_kind"] == "flow"

    assert lines[1]["date"] == "2026-01-15"
    assert lines[1]["flow"] == "Salary"
    assert lines[1]["amount"] == 2500.0
    assert lines[1]["account"] == "checking"
    assert lines[1]["balance"] == 6000.0
    assert lines[1]["category"] == "income"
    assert lines[1]["tx_kind"] == "flow"

    daily_lines = [json.loads(line) for line in daily_jsonl_file.read_text(encoding="utf-8").strip().split("\n")]
    assert len(daily_lines) == 2
    assert daily_lines[0]["date"] == "2026-01-01"
    assert daily_lines[0]["checking"] == 3500.0
    assert daily_lines[0]["total_net_worth"] == 3500.0


def test_ledger_export_jsonl_with_daily_events(tmp_path: Path) -> None:
    ledger = Ledger()
    tx_date = date(2026, 1, 1)

    ledger.append(
        tx_date=tx_date,
        flow_name="Coffee",
        amount=-500,
        account="checking",
        balance=49500,
        category="food",
        tx_kind="flow",
    )
    ledger.daily_records.append({
        "date": tx_date,
        "checking": 495.0,
        "total_net_worth": 495.0,
    })

    combined_file = tmp_path / "combined.jsonl"
    ledger.export_jsonl(str(combined_file), include_daily_events=True)

    lines = [json.loads(line) for line in combined_file.read_text(encoding="utf-8").strip().split("\n")]
    assert len(lines) == 2
    assert lines[0]["event_type"] == "transaction"
    assert lines[0]["flow"] == "Coffee"
    assert lines[1]["event_type"] == "daily_balance"
    assert lines[1]["date"] == "2026-01-01"
    assert lines[1]["balances"]["checking"] == 495.0
