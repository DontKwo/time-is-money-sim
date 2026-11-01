import argparse
import json
from pathlib import Path
from typing import Optional, List

from lifesim.config import load_scenario
from lifesim.engine import run
from lifesim.plots import (
    plot_balances,
    plot_net_worth_stack,
    plot_monthly_cashflow,
    plot_compounding_breakdown,
    plot_monte_carlo_fan,
    plot_scenario_comparison,
    plot_sensitivity_tornado,
)
from lifesim.montecarlo import run_monte_carlo
from lifesim.compare import compare_scenarios, run_sensitivity_analysis
from lifesim.db import export_to_sqlite


def main() -> None:
    parser = argparse.ArgumentParser(description="Life Money Simulator")
    parser.add_argument("scenario", type=str, help="Path to scenario YAML file")
    parser.add_argument("--out-ledger", type=str, default="ledger.csv", help="Output ledger CSV path")
    parser.add_argument("--out-plot", type=str, default="balances.png", help="Output plot PNG path")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Override YAML key with KEY=VALUE",
    )
    parser.add_argument("--out-daily", type=str, default=None, help="Output daily balances CSV path")
    parser.add_argument("--out-summary", type=str, default=None, help="Output summary metrics JSON path")
    parser.add_argument("--charts-dir", type=str, default=None, help="Output charts directory")
    parser.add_argument("--monte-carlo", type=int, default=None, help="Number of Monte Carlo trials")
    parser.add_argument("--out-mc-plot", type=str, default="monte_carlo.png", help="Monte Carlo fan plot path")
    parser.add_argument(
        "--compare",
        nargs="+",
        type=str,
        default=None,
        help="Other scenario YAML paths to compare against",
    )
    parser.add_argument("--out-compare-plot", type=str, default="comparison.png", help="Comparison plot path")
    parser.add_argument("--sensitivity", action="store_true", help="Run tornado sensitivity analysis")
    parser.add_argument("--out-tornado-plot", type=str, default="sensitivity.png", help="Tornado plot path")
    parser.add_argument("--out-sqlite", type=str, default=None, help="Output SQLite database path")

    args = parser.parse_args()

    # Verify scenario path exists
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        print(f"Error: Scenario file {args.scenario} not found.")
        return

    print(f"Loading scenario from {args.scenario}...")
    overrides_list: Optional[List[str]] = args.overrides if args.overrides else None
    scenario = load_scenario(args.scenario, overrides=overrides_list)

    print(f"Running simulation for {scenario.days} days...")
    ledger = run(scenario)
    dataframe = ledger.to_df()

    print(f"Exporting ledger to {args.out_ledger}...")
    dataframe.to_csv(args.out_ledger, index=False)

    print(f"Generating plot to {args.out_plot}...")
    plot_balances(dataframe, args.out_plot)

    if args.out_daily is not None:
        daily_dataframe = ledger.daily_df()
        daily_dataframe.to_csv(args.out_daily, index=False)

    if args.out_sqlite is not None:
        export_to_sqlite(ledger, args.out_sqlite)

    if args.out_summary is not None:
        summary_payload = {
            "metrics": ledger.metrics,
            "goals": ledger.goal_results,
        }
        with open(args.out_summary, "w", encoding="utf-8") as summary_file:
            json.dump(summary_payload, summary_file, indent=2, default=str)

    if args.charts_dir is not None:
        charts_directory = Path(args.charts_dir)
        charts_directory.mkdir(parents=True, exist_ok=True)
        plot_balances(dataframe, str(charts_directory / "balances.png"))
        plot_net_worth_stack(ledger, str(charts_directory / "net_worth.png"))
        plot_monthly_cashflow(ledger, str(charts_directory / "monthly_cashflow.png"))
        plot_compounding_breakdown(ledger, str(charts_directory / "compounding.png"))

    if args.monte_carlo is not None:
        mc_result = run_monte_carlo(scenario, num_runs=args.monte_carlo)
        plot_monte_carlo_fan(mc_result, args.out_mc_plot)

    if args.compare is not None:
        named_scenarios = {scenario_path.stem: scenario}
        for other_path_str in args.compare:
            other_scenario = load_scenario(other_path_str)
            named_scenarios[Path(other_path_str).stem] = other_scenario
        comparison_result = compare_scenarios(named_scenarios)
        plot_scenario_comparison(comparison_result, args.out_compare_plot)

    if args.sensitivity:
        sensitivity_result = run_sensitivity_analysis(scenario)
        plot_sensitivity_tornado(sensitivity_result, args.out_tornado_plot)

    print("Done!")


if __name__ == "__main__":
    main()
