from pathlib import Path
from datetime import date, datetime
import os
import pandas as pd
from unittest.mock import patch

from lifesim.plots import (
    plot_balances,
    plot_net_worth_stack,
    plot_monthly_cashflow,
    plot_compounding_breakdown,
    plot_monte_carlo_fan,
    plot_scenario_comparison,
    plot_sensitivity_tornado,
)
from lifesim.config import ScenarioModel
from lifesim.engine import run
from lifesim.montecarlo import run_monte_carlo
from lifesim.compare import compare_scenarios, run_sensitivity_analysis


def test_plot_balances_empty_df(tmp_path: Path) -> None:
    df = pd.DataFrame()
    filename = tmp_path / "test_plot.png"

    with patch("matplotlib.pyplot.figure") as mock_figure:
        plot_balances(df, str(filename))
        mock_figure.assert_not_called()

    assert not os.path.exists(filename)


def test_plot_balances_creates_file(tmp_path: Path) -> None:
    data = {
        "date": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
        "account": ["Checking", "Checking", "Savings"],
        "balance": [1000, 1500, 5000],
    }
    dataframe = pd.DataFrame(data)
    filename = tmp_path / "test_plot_balances.png"

    plot_balances(dataframe, str(filename))

    assert os.path.exists(filename)
    assert os.path.getsize(filename) > 0


def test_all_new_plots_create_files(tmp_path: Path) -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=30,
        accounts={"checking": {"kind": "checking", "balance": 2000.0}},
        flows=[
            {
                "name": "Rent",
                "category": "housing",
                "type": "expense",
                "schedule": {"monthly": 1},
                "amount": {"fixed": 1000.0},
            }
        ],
        goals=[{"name": "Target NW", "kind": "net_worth", "target_amount": 5000.0}],
    )
    ledger = run(scenario)

    nw_plot = tmp_path / "nw.png"
    plot_net_worth_stack(ledger, str(nw_plot))
    assert nw_plot.exists() and nw_plot.stat().st_size > 0

    cashflow_plot = tmp_path / "cashflow.png"
    plot_monthly_cashflow(ledger, str(cashflow_plot))
    assert cashflow_plot.exists() and cashflow_plot.stat().st_size > 0

    comp_plot = tmp_path / "compounding.png"
    plot_compounding_breakdown(ledger, str(comp_plot))
    assert comp_plot.exists() and comp_plot.stat().st_size > 0

    mc_result = run_monte_carlo(scenario, num_runs=5)
    mc_plot = tmp_path / "mc.png"
    plot_monte_carlo_fan(mc_result, str(mc_plot))
    assert mc_plot.exists() and mc_plot.stat().st_size > 0

    comp_result = compare_scenarios({"A": scenario, "B": scenario})
    comp_plot_file = tmp_path / "comparison.png"
    plot_scenario_comparison(comp_result, str(comp_plot_file))
    assert comp_plot_file.exists() and comp_plot_file.stat().st_size > 0

    sens_result = run_sensitivity_analysis(scenario)
    sens_plot = tmp_path / "tornado.png"
    plot_sensitivity_tornado(sens_result, str(sens_plot))
    assert sens_plot.exists() and sens_plot.stat().st_size > 0
