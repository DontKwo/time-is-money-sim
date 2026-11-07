from typing import Any, Dict
import io
import pandas as pd
import matplotlib.pyplot as plt

from .config import ScenarioModel
from .ledger import Ledger
from .analysis import monthly_rollup_df, category_summary_df

def _generate_svg_chart(ledger: Ledger) -> str:
    daily_df = ledger.daily_df()
    if daily_df.empty:
        return ""

    fig, axis = plt.subplots(figsize=(10, 5))
    sim_dates = daily_df["date"]

    axis.plot(sim_dates, daily_df["total_net_worth"], label="Total Net Worth", color="black", linewidth=2.5)
    axis.plot(sim_dates, daily_df["liquid_net_worth"], label="Liquid Net Worth", color="blue", linestyle="--")

    # Add vertical markers for achieved goals
    achieved_goals = [goal_result for goal_result in ledger.goal_results if goal_result["achieved"]]
    for goal in achieved_goals:
        achieved_date = pd.to_datetime(goal["achieved_date"])
        axis.axvline(x=achieved_date, color="green", linestyle=":", alpha=0.7)
        axis.text(achieved_date, axis.get_ylim()[1], goal["name"], rotation=90, va="top", ha="right", color="green", alpha=0.7)

    axis.set_title("Net Worth Over Time")
    axis.set_xlabel("Date")
    axis.set_ylabel("Balance ($)")
    axis.legend()
    axis.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    svg_buf = io.StringIO()
    fig.savefig(svg_buf, format='svg')
    plt.close(fig)

    return svg_buf.getvalue()


def generate_html_report(scenario: ScenarioModel, ledger: Ledger, filename: str) -> None:
    # Gather summary metrics
    metrics = ledger.metrics
    nw_metrics = metrics.get("net_worth", {})
    cashflow_metrics = metrics.get("cashflow", {})
    liquidity_metrics = metrics.get("liquidity", {})

    # Calculate cash runway
    cash_runway_days = "N/A"
    tx_df = ledger.to_df()
    if not tx_df.empty:
        non_transfers = tx_df[tx_df["tx_kind"] != "transfer"]
        expense_tx = non_transfers[non_transfers["amount"] < 0]

        # Calculate daily expenses from trailing 90 days if possible
        if not expense_tx.empty:
            last_date = pd.to_datetime(tx_df["date"].iloc[-1])
            cutoff_date = last_date - pd.Timedelta(days=90)
            recent_expenses = expense_tx[pd.to_datetime(expense_tx["date"]) >= cutoff_date]

            if not recent_expenses.empty:
                total_recent_spending = abs(float(recent_expenses["amount"].sum()))
                days_in_period = (last_date - cutoff_date).days
                if days_in_period > 0:
                    daily_expense = total_recent_spending / days_in_period
                    ending_liquid = nw_metrics.get("ending_liquid", 0)
                    if daily_expense > 0:
                        runway = ending_liquid / daily_expense
                        cash_runway_days = f"{runway:.0f} days"

    # Tables
    monthly_df = monthly_rollup_df(ledger)
    monthly_html = monthly_df.to_html(index=False, classes="table table-striped") if not monthly_df.empty else "<p>No monthly cashflow data.</p>"

    cat_df = category_summary_df(ledger)
    cat_html = cat_df.to_html(index=False, classes="table table-striped") if not cat_df.empty else "<p>No category expenses.</p>"

    goals = ledger.goal_results
    if goals:
        goals_df = pd.DataFrame(goals)
        goals_html = goals_df.to_html(index=False, classes="table table-striped")
    else:
        goals_html = "<p>No goals defined.</p>"

    svg_chart = _generate_svg_chart(ledger)

    # HTML Template
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Life Money Simulator - Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            color: #333;
        }}
        .summary-cards {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-bottom: 30px;
        }}
        .card {{
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            flex: 1;
            min-width: 200px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .card h3 {{
            margin-top: 0;
            font-size: 1.1em;
            color: #495057;
        }}
        .card p {{
            font-size: 1.4em;
            font-weight: bold;
            margin-bottom: 0;
            color: #007bff;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        h2 {{
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 5px;
        }}
        .table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        .table th, .table td {{
            padding: 8px 12px;
            border: 1px solid #dee2e6;
            text-align: left;
        }}
        .table th {{
            background-color: #e9ecef;
        }}
        .table-striped tbody tr:nth-of-type(odd) {{
            background-color: #f8f9fa;
        }}
        .chart-container {{
            width: 100%;
            max-width: 1000px;
            margin: 0 auto;
        }}
    </style>
</head>
<body>
    <h1>Life Money Simulator - Financial Report</h1>

    <div class="section">
        <h2>Executive Summary</h2>
        <div class="summary-cards">
            <div class="card">
                <h3>Starting Net Worth</h3>
                <p>${nw_metrics.get('starting', 0):,.2f}</p>
            </div>
            <div class="card">
                <h3>Ending Net Worth</h3>
                <p>${nw_metrics.get('ending', 0):,.2f}</p>
            </div>
            <div class="card">
                <h3>CAGR</h3>
                <p>{nw_metrics.get('cagr', 0):.2%}</p>
            </div>
            <div class="card">
                <h3>Savings Rate</h3>
                <p>{cashflow_metrics.get('savings_rate', 0):.2%}</p>
            </div>
            <div class="card">
                <h3>Cash Runway</h3>
                <p>{cash_runway_days}</p>
            </div>
            <div class="card">
                <h3>Lowest Checking</h3>
                <p>${liquidity_metrics.get('lowest_checking', 0):,.2f}</p>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Net Worth Chart</h2>
        <div class="chart-container">
            {svg_chart}
        </div>
    </div>

    <div class="section">
        <h2>Monthly Cashflow</h2>
        {monthly_html}
    </div>

    <div class="section">
        <h2>Expense Categories</h2>
        {cat_html}
    </div>

    <div class="section">
        <h2>Goal Milestones</h2>
        {goals_html}
    </div>
</body>
</html>
"""

    with open(filename, "w", encoding="utf-8") as out_file:
        out_file.write(html_content)
