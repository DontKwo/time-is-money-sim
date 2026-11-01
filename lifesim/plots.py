import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing import Any, Dict

from .ledger import Ledger
from .analysis import monthly_rollup_df


def plot_balances(df: pd.DataFrame, filename: str) -> None:
    if df.empty:
        return

    plt.figure(figsize=(10, 6))
    for account_name, account_data in df.groupby("account"):
        plt.step(account_data["date"], account_data["balance"], where="post", label=account_name)

    plt.xlabel("Date")
    plt.ylabel("Balance ($)")
    plt.title("Account Balances")
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_net_worth_stack(ledger: Ledger, filename: str) -> None:
    daily_df = ledger.daily_df()
    if daily_df.empty:
        return

    plt.figure(figsize=(12, 6))
    sim_dates = daily_df["date"]
    plt.plot(sim_dates, daily_df["total_net_worth"], label="Total Net Worth", color="black", linewidth=2.5)
    plt.plot(sim_dates, daily_df["liquid_net_worth"], label="Liquid Net Worth", color="blue", linestyle="--")

    # Mark achieved goal dates
    for goal_item in ledger.goal_results:
        achieved_date = goal_item.get("achieved_date")
        if goal_item.get("achieved") and achieved_date is not None:
            plt.axvline(x=achieved_date, color="green", linestyle=":", alpha=0.7)

    plt.xlabel("Date")
    plt.ylabel("Net Worth ($)")
    plt.title("Net Worth Over Time")
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_monthly_cashflow(ledger: Ledger, filename: str) -> None:
    cashflow_df = monthly_rollup_df(ledger)
    if cashflow_df.empty:
        return

    plt.figure(figsize=(10, 6))
    months = cashflow_df["month"]
    x_positions = np.arange(len(months))
    bar_width = 0.35

    plt.bar(x_positions - bar_width / 2, cashflow_df["income"], bar_width, label="Income", color="green", alpha=0.7)
    plt.bar(x_positions + bar_width / 2, cashflow_df["expenses"], bar_width, label="Expenses", color="red", alpha=0.7)
    plt.plot(x_positions, cashflow_df["net_cashflow"], label="Net Cashflow", color="blue", marker="o", linewidth=2)

    plt.xticks(x_positions, months, rotation=45)
    plt.ylabel("Amount ($)")
    plt.title("Monthly Cashflow")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_compounding_breakdown(ledger: Ledger, filename: str) -> None:
    daily_df = ledger.daily_df()
    if daily_df.empty:
        return

    plt.figure(figsize=(10, 6))
    sim_dates = daily_df["date"]
    plt.plot(sim_dates, daily_df["total_net_worth"], label="Total Net Worth", color="blue", linewidth=2)
    if "total_assets" in daily_df.columns:
        plt.plot(sim_dates, daily_df["total_assets"], label="Total Assets", color="teal", linestyle="--")

    tx_df = ledger.to_df()
    growth_mask = tx_df["flow"].str.contains("Growth|Interest|Dividend", case=False, na=False)
    growth_records = tx_df[growth_mask]
    total_growth = float(growth_records["amount"].sum()) if not growth_records.empty else 0.0

    plt.title(f"Compounding Breakdown (Total Return: ${total_growth:,.2f})")
    plt.xlabel("Date")
    plt.ylabel("Value ($)")
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_monte_carlo_fan(mc_result: Any, filename: str) -> None:
    plt.figure(figsize=(12, 6))
    sim_dates = mc_result.dates
    p50_curve = mc_result.net_worth_percentiles["p50"]

    plt.plot(sim_dates, p50_curve, color="navy", label="Median (p50)", linewidth=2)
    plt.fill_between(
        sim_dates,
        mc_result.net_worth_percentiles["p25"],
        mc_result.net_worth_percentiles["p75"],
        color="royalblue",
        alpha=0.3,
        label="25th-75th Percentile",
    )
    plt.fill_between(
        sim_dates,
        mc_result.net_worth_percentiles["p10"],
        mc_result.net_worth_percentiles["p90"],
        color="cornflowerblue",
        alpha=0.2,
        label="10th-90th Percentile",
    )
    plt.fill_between(
        sim_dates,
        mc_result.net_worth_percentiles["p5"],
        mc_result.net_worth_percentiles["p95"],
        color="lightsteelblue",
        alpha=0.15,
        label="5th-95th Percentile",
    )

    plt.xlabel("Date")
    plt.ylabel("Net Worth ($)")
    plt.title(f"Monte Carlo Net Worth Projection ({mc_result.num_runs} Trials)")
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_scenario_comparison(comp_result: Any, filename: str) -> None:
    plt.figure(figsize=(12, 6))
    for scenario_name, daily_series in comp_result.daily_net_worths.items():
        plt.plot(daily_series.index, daily_series.values, label=scenario_name, linewidth=2)

    plt.xlabel("Date")
    plt.ylabel("Total Net Worth ($)")
    plt.title("Scenario Comparison")
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_sensitivity_tornado(sens_result: Any, filename: str) -> None:
    table_df = sens_result.table
    if table_df.empty:
        return

    plt.figure(figsize=(10, 6))
    lever_names = list(table_df["lever"])[::-1]
    low_deltas = list(table_df["low_ending_nw"] - sens_result.baseline_ending_nw)[::-1]
    high_deltas = list(table_df["high_ending_nw"] - sens_result.baseline_ending_nw)[::-1]
    y_positions = np.arange(len(lever_names))

    plt.barh(y_positions, low_deltas, height=0.4, label="Downside Impact", color="crimson", alpha=0.7)
    plt.barh(y_positions, high_deltas, height=0.4, label="Upside Impact", color="forestgreen", alpha=0.7)
    plt.yticks(y_positions, lever_names)
    plt.xlabel("Delta vs Baseline Net Worth ($)")
    plt.axvline(0, color="black", linewidth=1.2)
    plt.title("Sensitivity Analysis (Tornado Chart)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
