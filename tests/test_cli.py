import json
import os
import sys
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
