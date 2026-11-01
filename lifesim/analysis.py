from datetime import date
from typing import Dict, Any, List, TYPE_CHECKING
import pandas as pd
from .config import ScenarioModel

if TYPE_CHECKING:
    from .ledger import Ledger


def deflate_daily_records(daily_records: List[Dict[str, Any]], macro_inflation_indices: Dict[date, float]) -> List[Dict[str, Any]]:
    # Adjust nominal daily records into real purchasing power dollars
    # Using the cumulative inflation factor relative to scenario start
    deflated_records = []
    for record in daily_records:
        record_date = record["date"]
        inflation_factor = macro_inflation_indices.get(record_date, 1.0)
        deflated_record = {"date": record_date}
        for key, value in record.items():
            if key != "date" and isinstance(value, (int, float)):
                deflated_record[key] = round(float(value) / inflation_factor, 2)
            elif key != "date":
                deflated_record[key] = value
        deflated_records.append(deflated_record)
    return deflated_records


def compute_summary(scenario: ScenarioModel, ledger: "Ledger") -> Dict[str, Any]:
    daily_df = ledger.daily_df()
    tx_df = ledger.to_df()
    summary: Dict[str, Any] = {}

    if not daily_df.empty:
        start_nw = float(daily_df["total_net_worth"].iloc[0])
        end_nw = float(daily_df["total_net_worth"].iloc[-1])
        min_idx = daily_df["total_net_worth"].idxmin()
        max_idx = daily_df["total_net_worth"].idxmax()
        min_nw = float(daily_df["total_net_worth"].loc[min_idx])
        min_nw_date = str(daily_df["date"].loc[min_idx])
        max_nw = float(daily_df["total_net_worth"].loc[max_idx])
        max_nw_date = str(daily_df["date"].loc[max_idx])

        years_horizon = max(0.001, (scenario.days or 30) / 365.25)
        if start_nw > 0.0 and end_nw > 0.0:
            cagr = (end_nw / start_nw) ** (1.0 / years_horizon) - 1.0
        else:
            cagr = 0.0

        summary["net_worth"] = {
            "starting": round(start_nw, 2),
            "ending": round(end_nw, 2),
            "min": round(min_nw, 2),
            "min_date": min_nw_date,
            "max": round(max_nw, 2),
            "max_date": max_nw_date,
            "change": round(end_nw - start_nw, 2),
            "cagr": round(cagr, 4),
            "starting_liquid": round(float(daily_df["liquid_net_worth"].iloc[0]), 2),
            "ending_liquid": round(float(daily_df["liquid_net_worth"].iloc[-1]), 2),
        }

        if "checking" in daily_df.columns:
            lowest_chk_idx = daily_df["checking"].idxmin()
            lowest_chk = float(daily_df["checking"].loc[lowest_chk_idx])
            lowest_chk_date = str(daily_df["date"].loc[lowest_chk_idx])
            days_overdrawn = int((daily_df["checking"] < 0.0).sum())
            days_below_500 = int(((daily_df["checking"] >= 0.0) & (daily_df["checking"] < 500.0)).sum())
        else:
            lowest_chk = 0.0
            lowest_chk_date = str(scenario.start)
            days_overdrawn = 0
            days_below_500 = 0

        summary["liquidity"] = {
            "lowest_checking": round(lowest_chk, 2),
            "lowest_checking_date": lowest_chk_date,
            "days_overdrawn": days_overdrawn,
            "days_below_500": days_below_500,
        }

    # Transaction aggregates
    if not tx_df.empty:
        non_transfers = tx_df[tx_df["tx_kind"] != "transfer"]
        income_tx = non_transfers[non_transfers["amount"] > 0]
        expense_tx = non_transfers[non_transfers["amount"] < 0]

        total_income = float(income_tx["amount"].sum())
        total_spending = abs(float(expense_tx["amount"].sum()))

        summary["cashflow"] = {
            "total_income": round(total_income, 2),
            "total_spending": round(total_spending, 2),
            "net_savings": round(total_income - total_spending, 2),
            "savings_rate": round((total_income - total_spending) / max(1.0, total_income), 4),
        }

    summary["goals"] = ledger.goal_results
    return summary


def monthly_rollup_df(ledger: "Ledger") -> pd.DataFrame:
    tx_df = ledger.to_df()
    if tx_df.empty:
        return pd.DataFrame()

    tx_df = tx_df.copy()
    tx_df["year_month"] = tx_df["date"].apply(lambda d: f"{d.year:04d}-{d.month:02d}")
    non_transfers = tx_df[tx_df["tx_kind"] != "transfer"]

    rows = []
    for month_key, group in non_transfers.groupby("year_month"):
        income_dollars = float(group[group["amount"] > 0]["amount"].sum())
        expense_dollars = abs(float(group[group["amount"] < 0]["amount"].sum()))
        rows.append({
            "month": month_key,
            "income": round(income_dollars, 2),
            "expenses": round(expense_dollars, 2),
            "net_cashflow": round(income_dollars - expense_dollars, 2),
        })

    return pd.DataFrame(rows)


def category_summary_df(ledger: "Ledger") -> pd.DataFrame:
    tx_df = ledger.to_df()
    if tx_df.empty:
        return pd.DataFrame()

    expenses = tx_df[(tx_df["tx_kind"] != "transfer") & (tx_df["amount"] < 0)].copy()
    if expenses.empty:
        return pd.DataFrame()

    total_expense = abs(float(expenses["amount"].sum()))
    category_totals = expenses.groupby("category")["amount"].sum().abs()

    result = []
    for category_name, cat_total in category_totals.items():
        share = float(cat_total) / max(1e-6, total_expense)
        result.append({
            "category": category_name,
            "total": round(float(cat_total), 2),
            "share_of_spending": round(share, 4),
        })

    return pd.DataFrame(result).sort_values("total", ascending=False)

