import json
import os
import sqlite3
import sys
from typing import List, Tuple
from unittest.mock import patch
from pathlib import Path
import pytest

from lifesim.cli import main


def test_cli_scenario_not_found(capsys: pytest.CaptureFixture) -> None:
    test_args = ["lifesim", "non_existent_scenario.yaml"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "Error: Scenario file non_existent_scenario.yaml not found." in captured.out


def test_cli_success(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    scenario_file = tmp_path / "scenario.yaml"
    with open(scenario_file, "w") as f_out:
        f_out.write("""
start: 2026-01-01
days: 10
accounts:
  checking: {balance: 1000}
flows:
  - name: DummyFlow
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 10}
""")

    out_ledger = tmp_path / "ledger.csv"
    out_plot = tmp_path / "balances.png"

    test_args = [
        "lifesim",
        str(scenario_file),
        "--out-ledger", str(out_ledger),
        "--out-plot", str(out_plot),
    ]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert f"Loading scenario from {scenario_file}..." in captured.out
    assert "Running simulation for 10 days..." in captured.out
    assert f"Exporting ledger to {out_ledger}..." in captured.out
    assert f"Generating plot to {out_plot}..." in captured.out
    assert "Done!" in captured.out

    assert out_ledger.exists()
    assert out_plot.exists()


def test_cli_extended_flags(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario_ext.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 15
accounts:
  checking: {balance: 5000}
flows:
  - name: Food
    category: food
    type: expense
    schedule: {weekly: fri}
    amount: {fixed: 100}
""")

    alt_scenario_file = tmp_path / "scenario_alt.yaml"
    alt_scenario_file.write_text("""
start: 2026-01-01
days: 15
accounts:
  checking: {balance: 7000}
flows:
  - name: Food
    category: food
    type: expense
    schedule: {weekly: fri}
    amount: {fixed: 100}
""")

    out_daily = tmp_path / "daily.csv"
    out_summary = tmp_path / "summary.json"
    charts_dir = tmp_path / "charts"
    mc_plot = tmp_path / "mc.png"
    compare_plot = tmp_path / "comp.png"
    tornado_plot = tmp_path / "tornado.png"

    test_args = [
        "lifesim",
        str(scenario_file),
        "--set", "flows.Food.amount.fixed=150.0",
        "--out-daily", str(out_daily),
        "--out-summary", str(out_summary),
        "--charts-dir", str(charts_dir),
        "--monte-carlo", "5",
        "--out-mc-plot", str(mc_plot),
        "--compare", str(alt_scenario_file),
        "--out-compare-plot", str(compare_plot),
        "--sensitivity",
        "--out-tornado-plot", str(tornado_plot),
    ]
    with patch.object(sys, "argv", test_args):
        main()

    assert out_daily.exists() and out_daily.stat().st_size > 0
    assert out_summary.exists() and out_summary.stat().st_size > 0

    with open(out_summary, "r", encoding="utf-8") as json_in:
        summary_data = json.load(json_in)
        assert "metrics" in summary_data

    assert (charts_dir / "balances.png").exists()
    assert (charts_dir / "net_worth.png").exists()
    assert (charts_dir / "monthly_cashflow.png").exists()
    assert (charts_dir / "compounding.png").exists()
    assert mc_plot.exists()
    assert compare_plot.exists()
    assert tornado_plot.exists()

def test_cli_sqlite_export(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario_sqlite.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 10
accounts:
  checking: {balance: 2000}
  savings: {balance: 5000}
flows:
  - name: Salary
    type: income
    to: checking
    schedule: {weekly: fri}
    amount: {fixed: 500}
  - name: Rent
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 800}
""")

    out_sqlite = tmp_path / "export.sqlite"
    test_args = [
        "lifesim",
        str(scenario_file),
        "--out-sqlite", str(out_sqlite),
    ]
    with patch.object(sys, "argv", test_args):
        main()

    assert out_sqlite.exists()

    db_connection = sqlite3.connect(str(out_sqlite))
    db_cursor = db_connection.cursor()

    # Verify transactions table schema and rows
    db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
    table_result = db_cursor.fetchone()
    assert table_result is not None

    db_cursor.execute("PRAGMA table_info(transactions)")
    tx_columns: List[str] = [column_info[1] for column_info in db_cursor.fetchall()]
    expected_tx_cols = ["date", "flow", "amount", "account", "balance", "category", "tx_kind"]
    assert tx_columns == expected_tx_cols

    db_cursor.execute("SELECT COUNT(*) FROM transactions")
    tx_count_row = db_cursor.fetchone()
    assert tx_count_row is not None
    assert tx_count_row[0] > 0

    # Verify queryability and index presence
    db_cursor.execute("PRAGMA index_list(transactions)")
    tx_indexes: List[str] = [index_info[1] for index_info in db_cursor.fetchall()]
    assert "idx_transactions_date" in tx_indexes
    assert "idx_transactions_account" in tx_indexes

    db_cursor.execute("SELECT date, flow, amount FROM transactions WHERE account='checking'")
    query_rows: List[Tuple] = db_cursor.fetchall()
    assert len(query_rows) == tx_count_row[0]

    # Verify daily_balances table schema and rows
    db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_balances'")
    daily_table_result = db_cursor.fetchone()
    assert daily_table_result is not None

    db_cursor.execute("PRAGMA table_info(daily_balances)")
    daily_columns: List[str] = [column_info[1] for column_info in db_cursor.fetchall()]
    base_daily_cols = [
        "date",
        "total_net_worth",
        "liquid_net_worth",
        "vested_net_worth",
        "total_assets",
        "total_debt",
    ]
    for base_col in base_daily_cols:
        assert base_col in daily_columns
    assert "checking" in daily_columns
    assert "savings" in daily_columns

    db_cursor.execute("SELECT COUNT(*) FROM daily_balances")
    daily_count_row = db_cursor.fetchone()
    assert daily_count_row is not None
    assert daily_count_row[0] == 10

    db_cursor.execute("PRAGMA index_list(daily_balances)")
    daily_indexes: List[str] = [index_info[1] for index_info in db_cursor.fetchall()]
    assert "idx_daily_balances_date" in daily_indexes

    db_cursor.execute("SELECT date, total_net_worth, checking, savings FROM daily_balances")
    daily_query_rows: List[Tuple] = db_cursor.fetchall()
    assert len(daily_query_rows) == 10

    db_connection.close()


def test_cli_validate_success(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    scenario_file = tmp_path / "scenario_valid.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 30
accounts:
  checking: {balance: 2500}
flows:
  - name: Rent
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 1200}
""")

    test_args = ["lifesim", str(scenario_file), "--validate"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exit_info:
            main()

    assert exit_info.value.code == 0
    captured = capsys.readouterr()
    assert f"Validation successful: {scenario_file} is valid." in captured.out


def test_cli_validate_scenario_not_found(capsys: pytest.CaptureFixture) -> None:
    non_existent_file = "missing_scenario.yaml"
    test_args = ["lifesim", non_existent_file, "--validate"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exit_info:
            main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert f"Error: Scenario file {non_existent_file} not found." in captured.out


def test_cli_validate_invalid_yaml(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    invalid_yaml_file = tmp_path / "broken_syntax.yaml"
    invalid_yaml_file.write_text("start: 2026-01-01\naccounts: [unclosed list\n")

    test_args = ["lifesim", str(invalid_yaml_file), "--validate"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exit_info:
            main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "Validation error:" in captured.out


def test_cli_validate_broken_account(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    broken_scenario_file = tmp_path / "broken_account.yaml"
    broken_scenario_file.write_text("""
start: 2026-01-01
days: 30
accounts:
  checking:
    kind: non_existent_account_kind
    balance: 1000
""")

    test_args = ["lifesim", str(broken_scenario_file), "--validate"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exit_info:
            main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "Validation error:" in captured.out

def test_cli_html_report_export(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    scenario_file = tmp_path / "scenario_html.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 30
accounts:
  checking: {balance: 5000}
flows:
  - name: Salary
    type: income
    to: checking
    schedule: {weekly: fri}
    amount: {fixed: 1000}
  - name: Rent
    category: housing
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 1200}
goals:
  - name: Emergency Fund
    kind: net_worth
    target_amount: 6000
""")

    out_html = tmp_path / "report.html"
    test_args = [
        "lifesim",
        str(scenario_file),
        "--out-html", str(out_html),
    ]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert f"Generating HTML report to {out_html}..." in captured.out

    assert out_html.exists()

    html_content = out_html.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content
    assert "Life Money Simulator - Financial Report" in html_content
    assert "Executive Summary" in html_content
    assert "Net Worth Chart" in html_content
    assert "<svg" in html_content
    assert "Monthly Cashflow" in html_content
    assert "Expense Categories" in html_content
    assert "Goal Milestones" in html_content


def test_cli_real_dollars(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario_inflation.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 10
inflation:
  rate: 0.10
accounts:
  checking: {balance: 1000}
flows:
  - name: Rent
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 100}
""")

    out_ledger = tmp_path / "ledger_real.csv"
    out_daily = tmp_path / "daily_real.csv"

    test_args = [
        "lifesim",
        str(scenario_file),
        "--out-ledger", str(out_ledger),
        "--out-daily", str(out_daily),
        "--real-dollars"
    ]
    with patch.object(sys, "argv", test_args):
        main()

    assert out_ledger.exists()
    assert out_daily.exists()

    import pandas as pd
    daily_df = pd.read_csv(out_daily)
    assert not daily_df.empty
    assert "total_net_worth" in daily_df.columns


def test_cli_jsonl_export(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario_jsonl.yaml"
    scenario_file.write_text("""
start: 2026-01-01
days: 10
accounts:
  checking: {balance: 1000}
flows:
  - name: Rent
    type: expense
    from: checking
    schedule: {monthly: 1}
    amount: {fixed: 100}
""")

    out_jsonl = tmp_path / "ledger.jsonl"

    test_args = [
        "lifesim",
        str(scenario_file),
        "--out-jsonl", str(out_jsonl),
    ]
    with patch.object(sys, "argv", test_args):
        main()

    assert out_jsonl.exists()

    out_daily_jsonl = tmp_path / "ledger_daily.jsonl"
    assert out_daily_jsonl.exists()

    with open(out_jsonl, "r", encoding="utf-8") as file_in:
        lines = file_in.readlines()
        # 1 flow per month * 1 month out of 10 days? Actually only 1 transaction on start day
        assert len(lines) == 1
        for json_line in lines:
            data = json.loads(json_line)
            assert "date" in data
            assert "flow" in data
            assert "amount" in data
            assert "account" in data
            assert "balance" in data
            assert "category" in data
            assert "tx_kind" in data
            assert data["flow"] == "Rent"
            assert data["amount"] == -100.0  # (amount 100 fixed, amounts are read as dollars directly in config, and stored as amount / 100.0 if passed as cents, but actually the parser multiplies fixed by 100 in engine if it was specified as dollar, wait config says {fixed: 100} meaning $100) -> so -100.0
            assert data["account"] == "checking"
            assert data["balance"] == 900.0
            assert data["tx_kind"] == "flow"

    with open(out_daily_jsonl, "r", encoding="utf-8") as daily_in:
        daily_lines = daily_in.readlines()
        assert len(daily_lines) == 10
        for json_line in daily_lines:
            daily_data = json.loads(json_line)
            assert "date" in daily_data
            assert "total_net_worth" in daily_data
            assert "checking" in daily_data

import pandas as pd

def test_cli_batch_runner(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    scenario_1 = tmp_path / "scenario_1.yaml"
    scenario_1.write_text("""
start: 2026-01-01
days: 30
accounts:
  checking: {balance: 1000}
flows:
  - name: Salary
    type: income
    to: checking
    schedule: {monthly: 1}
    amount: {fixed: 1000}
""")

    scenario_2 = tmp_path / "scenario_2.yaml"
    scenario_2.write_text("""
start: 2026-01-01
days: 30
accounts:
  checking: {balance: 2000}
flows:
  - name: Salary
    type: income
    to: checking
    schedule: {monthly: 1}
    amount: {fixed: 2000}
""")

    out_csv = tmp_path / "batch_out.csv"

    test_args = [
        "lifesim",
        "--batch", f"{tmp_path}/*.yaml",
        "--out-batch-csv", str(out_csv),
    ]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exit_info:
            main()

    assert exit_info.value.code == 0

    # Check outputs
    captured = capsys.readouterr()
    assert "Running batch simulation" in captured.out
    assert "Scenario" in captured.out
    assert "Total Net Worth" in captured.out
    assert str(out_csv) in captured.out

    # Check CSV existence and content
    assert out_csv.exists()
    df = pd.read_csv(out_csv)
    assert len(df) == 2
    assert "Total Net Worth" in df.columns
    assert "Scenario" in df.columns

    names = df["Scenario"].tolist()
    assert "scenario_1.yaml" in names
    assert "scenario_2.yaml" in names
