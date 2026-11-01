import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List
import pydantic
import yaml

from lifesim.analysis import compute_summary
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
from lifesim.report import generate_html_report
from lifesim.batch import run_batch
import glob
import os
from tabulate import tabulate


def main() -> None:
    parser = argparse.ArgumentParser(description="Life Money Simulator")
    parser.add_argument("scenario", type=str, nargs="?", default=None, help="Path to scenario YAML file")
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
    parser.add_argument("--validate", action="store_true", help="Validate scenario file without running simulation")
    parser.add_argument("--out-sqlite", type=str, default=None, help="Output SQLite database path")
    parser.add_argument("--out-html", type=str, default=None, help="Output interactive HTML report path")
    parser.add_argument("--real-dollars", action="store_true", help="Deflate output metrics and charts into constant purchasing power dollars")
    parser.add_argument("--batch", type=str, default=None, help="Glob pattern or directory for batch running scenarios")
    parser.add_argument("--out-batch-csv", type=str, default=None, help="Output CSV path for batch summary matrix")


    args = parser.parse_args()

    if args.batch is not None:
        batch_path = Path(args.batch)
        scenario_files: List[str] = []
        if batch_path.is_dir():
            scenario_files = [str(path_item) for path_item in batch_path.glob("*.yaml")] + [str(path_item) for path_item in batch_path.glob("*.yml")]
        else:
            scenario_files = glob.glob(args.batch)

        if not scenario_files:
            print(f"Error: No scenario files found for batch {args.batch}")
            sys.exit(1)

        print(f"Running batch on {len(scenario_files)} scenarios...")
        summary_df = run_batch(scenario_files)

        # Print ASCII table
        print(tabulate(summary_df, headers="keys", tablefmt="grid", floatfmt=".2f"))

        if args.out_batch_csv is not None:
            print(f"Exporting batch summary to {args.out_batch_csv}...")
            summary_df.to_csv(args.out_batch_csv)

        sys.exit(0)

    if args.scenario is None:
        parser.error("scenario is required unless --batch is provided")

    # Handle scenario validation mode
    if args.validate:
        scenario_file_path = Path(args.scenario)
        if not scenario_file_path.exists():
            print(f"Error: Scenario file {args.scenario} not found.")
            sys.exit(1)
        try:
            overrides_arg: Optional[List[str]] = args.overrides if args.overrides else None
            load_scenario(args.scenario, overrides=overrides_arg)
            print(f"Validation successful: {args.scenario} is valid.")
            sys.exit(0)
        except (yaml.YAMLError, pydantic.ValidationError, ValueError) as validation_err:
            print(f"Validation error: {validation_err}")
            sys.exit(1)

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

    if args.real_dollars:
        ledger.daily_records = ledger.real_df(scenario.start).to_dict(orient="records")
        for record in ledger.records:
            record_date = record["date"]
            inflation_factor = ledger.inflation_indices.get(record_date, 1.0)
            if inflation_factor != 0.0:
                record["amount"] = round(record["amount"] / inflation_factor, 2)
                record["balance"] = round(record["balance"] / inflation_factor, 2)
        ledger.metrics = compute_summary(scenario, ledger)

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

    if args.out_html is not None:
        print(f"Generating HTML report to {args.out_html}...")
        generate_html_report(scenario, ledger, args.out_html)

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
