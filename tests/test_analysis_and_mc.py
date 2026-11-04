from datetime import date
import pytest
import numpy as np
from lifesim.config import ScenarioModel
from lifesim.engine import run
from lifesim.montecarlo import run_monte_carlo
from lifesim.compare import compare_scenarios, run_sensitivity_analysis
from lifesim.analysis import monthly_rollup_df, category_summary_df, recommend_traditional_vs_roth


def test_recommend_traditional_vs_roth() -> None:
    # Test traditional recommendation
    assert recommend_traditional_vs_roth(0.24, 0.12) == "Traditional"
    assert recommend_traditional_vs_roth(0.22, 0.19) == "Traditional"

    # Test roth recommendation
    assert recommend_traditional_vs_roth(0.12, 0.22) == "Roth"
    assert recommend_traditional_vs_roth(0.0, 0.10) == "Roth"

    # Test tie recommendation
    assert recommend_traditional_vs_roth(0.24, 0.24) == "Tie"
    assert recommend_traditional_vs_roth(0.22, 0.20) == "Tie"


def test_monte_carlo_monotonic_and_deterministic() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=30,
        seed=100,
        accounts={
            "checking": {"kind": "checking", "balance": 5000.0},
            "brokerage": {
                "kind": "investment",
                "balance": 20000.0,
                "expected_return": 0.08,
                "volatility": 0.15,
            },
        },
        flows=[
            {
                "name": "Groceries",
                "type": "expense",
                "schedule": {"weekly": "fri"},
                "amount": {"normal": [150.0, 20.0]},
            }
        ],
        goals=[
            {
                "name": "Target NW",
                "kind": "net_worth",
                "target_amount": 25000.0,
            }
        ],
    )

    first_result = run_monte_carlo(scenario, num_runs=50)
    second_result = run_monte_carlo(scenario, num_runs=50)

    # Determinism test
    np.testing.assert_allclose(
        first_result.net_worth_percentiles["p50"],
        second_result.net_worth_percentiles["p50"],
    )

    # Monotonicity test: p5 <= p25 <= p50 <= p75 <= p95 across every day
    p5 = first_result.net_worth_percentiles["p5"]
    p25 = first_result.net_worth_percentiles["p25"]
    p50 = first_result.net_worth_percentiles["p50"]
    p75 = first_result.net_worth_percentiles["p75"]
    p95 = first_result.net_worth_percentiles["p95"]

    assert (p5 <= p25 + 1e-6).all()
    assert (p25 <= p50 + 1e-6).all()
    assert (p50 <= p75 + 1e-6).all()
    assert (p75 <= p95 + 1e-6).all()


def test_compare_scenarios_401k_match_delta() -> None:
    scenario_no_match = ScenarioModel(
        start=date(2026, 1, 1),
        days=60,
        seed=42,
        accounts={
            "checking": {"kind": "checking", "balance": 5000.0},
            "traditional_401k": {"kind": "traditional_401k", "balance": 0.0},
        },
        paychecks=[
            {
                "name": "Salary",
                "enabled": True,
                "schedule": {"biweekly": "fri", "anchor": date(2026, 1, 2)},
                "annual_salary": 120000.0,
                "retirement_401k": {
                    "enabled": True,
                    "traditional_pct": 0.06,
                    "employer_match": {
                        "enabled": False,
                    },
                },
            }
        ],
        flows=[],
    )

    scenario_with_match = scenario_no_match.model_copy(deep=True)
    scenario_with_match.paychecks[0].retirement_401k.employer_match.enabled = True
    scenario_with_match.paychecks[0].retirement_401k.employer_match.match_rate = 1.0
    scenario_with_match.paychecks[0].retirement_401k.employer_match.up_to_pct = 0.06
    scenario_with_match.paychecks[0].retirement_401k.employer_match.to_account = "traditional_401k"

    comparison = compare_scenarios({
        "No Match": scenario_no_match,
        "With 6% Match": scenario_with_match,
    })

    assert len(comparison.table) == 2
    match_row = comparison.table[comparison.table["scenario"] == "With 6% Match"].iloc[0]
    assert match_row["delta_vs_baseline"] > 0.0


def test_sensitivity_analysis_ranking() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=90,
        seed=42,
        accounts={
            "checking": {"kind": "checking", "balance": 5000.0},
            "brokerage": {"kind": "investment", "balance": 10000.0, "annual_growth_rate": 0.07},
        },
        paychecks=[
            {
                "name": "Salary",
                "enabled": True,
                "schedule": {"biweekly": "fri", "anchor": date(2026, 1, 2)},
                "annual_salary": 100000.0,
            }
        ],
        flows=[
            {
                "name": "Rent",
                "category": "housing",
                "type": "expense",
                "schedule": {"monthly": 1},
                "amount": {"fixed": 2500.0},
            },
            {
                "name": "Coffee",
                "category": "coffee",
                "type": "expense",
                "schedule": {"daily": True},
                "amount": {"fixed": 5.0},
            },
        ],
    )

    result = run_sensitivity_analysis(scenario, delta_pct=0.15)
    assert not result.table.empty
    # Spreads should be descending
    spreads = list(result.table["spread"])
    assert spreads == sorted(spreads, reverse=True)


def test_analytics_dataframes() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=45,
        seed=42,
        accounts={"checking": {"kind": "checking", "balance": 3000.0}},
        flows=[
            {
                "name": "Salary",
                "type": "income",
                "category": "salary",
                "schedule": {"biweekly": "fri", "anchor": date(2026, 1, 2)},
                "amount": {"fixed": 2500.0},
            },
            {
                "name": "Groceries",
                "type": "expense",
                "category": "food",
                "schedule": {"weekly": "sat"},
                "amount": {"fixed": 150.0},
            },
        ],
    )
    ledger = run(scenario)
    monthly_df = monthly_rollup_df(ledger)
    assert not monthly_df.empty
    assert "income" in monthly_df.columns
    assert "expenses" in monthly_df.columns

    cat_df = category_summary_df(ledger)
    assert not cat_df.empty
    assert "category" in cat_df.columns
    assert "total" in cat_df.columns


def test_real_dollars_deflation() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=365 * 3,
        inflation={"rate": 0.10, "volatility": 0.0},
        accounts={"checking": {"kind": "checking", "balance": 10000.0}},
        flows=[],
    )
    ledger = run(scenario)

    nominal_df = ledger.daily_df()
    real_df = ledger.real_df(scenario.start)

    nominal_end_nw = nominal_df.iloc[-1]["total_net_worth"]
    real_end_nw = real_df.iloc[-1]["total_net_worth"]

    assert nominal_end_nw == 10000.0
    assert real_end_nw < nominal_end_nw
    assert abs(real_end_nw - (10000.0 / ((1.10) ** (3.0)))) < 100.0

def test_historical_crisis_simulate() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        days=365 * 5,
        seed=100,
        accounts={
            "checking": {"kind": "checking", "balance": 5000.0},
            "brokerage": {
                "kind": "investment",
                "balance": 100000.0,
                "expected_return": 0.08,
                "volatility": 0.15,
            },
        },
        flows=[],
    )

    from lifesim.montecarlo import simulate_historical_crisis

    result_1929 = simulate_historical_crisis(scenario, "1929_depression")
    assert result_1929["crisis_type"] == "1929_depression"
    assert result_1929["max_drawdown_pct"] > 10.0

    result_gfc = simulate_historical_crisis(scenario, "2008_gfc")
    assert result_gfc["crisis_type"] == "2008_gfc"

    with pytest.raises(ValueError):
        simulate_historical_crisis(scenario, "unknown_crisis")
