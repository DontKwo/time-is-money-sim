import os
import sys
from unittest.mock import patch
from pathlib import Path

from lifesim.cli import main

def test_cli_scenario_not_found(capsys):
    test_args = ["lifesim", "non_existent_scenario.yaml"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "Error: Scenario file non_existent_scenario.yaml not found." in captured.out

def test_cli_success(tmp_path, capsys):
    # Create a dummy scenario file
    scenario_file = tmp_path / "scenario.yaml"
    with open(scenario_file, "w") as f:
        f.write("""
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
        "--out-plot", str(out_plot)
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
