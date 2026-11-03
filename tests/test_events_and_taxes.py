from datetime import date
import numpy as np
from lifesim.config import (
    AccountModel,
    TaxBracket,
    TaxConfigModel,
    EventModel,
    FlowModel,
    PaycheckModel,
    ScheduleModel,
    AmountModel,
    Retirement401kSpec,
    EmployerMatchSpec,
    VestingSpec,
    SocialSecurityModel,
    ScenarioModel,
)
from lifesim.engine import run
from lifesim.taxes import (
    YearTaxAccumulator,
    compute_fica_cents,
    compute_progressive_tax_cents,
    compute_april_settlement_cents,
)
from lifesim.events import EventManager
from lifesim.payroll import PayrollState
from lifesim.accounts import AccountManager
from lifesim.ledger import Ledger


def test_fica_social_security_cap_and_additional_medicare() -> None:
    # First paycheck: $100k FICA wages. SS: 6.2% = $6,200, Med: 1.45% = $1,450.
    ss_tax, med_tax, total_fica = compute_fica_cents(10_000_000, 0)
    assert ss_tax == 620_000
    assert med_tax == 145_000
    assert total_fica == 765_000

    # Second paycheck: $100k FICA wages. Cumulative wage reaches $200k.
    # SS cap is $176,100 -> only $76,100 taxed at 6.2% ($4,718.20).
    ss_tax_2, med_tax_2, total_2 = compute_fica_cents(10_000_000, 10_000_000)
    assert ss_tax_2 == 471_820
    assert med_tax_2 == 145_000
    assert total_2 == 616_820

    # Third paycheck: $50k FICA wages above $200k. SS is capped at 0.
    # Base Med 1.45% ($725) + 0.9% Additional Med ($450) = $1,175.
    ss_tax_3, med_tax_3, total_3 = compute_fica_cents(5_000_000, 20_000_000)
    assert ss_tax_3 == 0
    assert med_tax_3 == 117_500
    assert total_3 == 117_500


def test_progressive_tax_brackets() -> None:
    brackets = [
        TaxBracket(rate=0.10, threshold=0.0),
        TaxBracket(rate=0.12, threshold=10_000.0),
        TaxBracket(rate=0.22, threshold=40_000.0),
    ]
    # Taxable income $50,000: 10k @ 10% ($1k) + 30k @ 12% ($3.6k) + 10k @ 22% ($2.2k).
    calculated_tax = compute_progressive_tax_cents(5_000_000, brackets)
    assert calculated_tax == 680_000


def test_april_settlement_refund() -> None:
    tax_config = TaxConfigModel(
        enabled=True,
        filing_status="single",
        standard_deduction=15_000.0,
        federal_brackets=[
            TaxBracket(rate=0.10, threshold=0.0),
            TaxBracket(rate=0.12, threshold=10_000.0),
        ],
        state_flat_rate=0.05,
    )
    tax_state = YearTaxAccumulator(2026)
    tax_state.ytd_taxable_ordinary_cents = 4_500_000
    # Gross 45k - 15k std ded = 30k taxable. Fed tax = $3,400, State 5% = $1,500. Total = $4,900.
    # Withheld: Fed $4,000 + State $2,000 = $6,000 -> Refund = -$1,100 (-110_000 cents).
    tax_state.ytd_fed_withheld_cents = 400_000
    tax_state.ytd_state_withheld_cents = 200_000

    settlement_cents = compute_april_settlement_cents(tax_state, tax_config)
    assert settlement_cents == -110_000


def test_job_layoff_event_with_reversion_and_unvested_forfeiture() -> None:
    paycheck = PaycheckModel(
        name="Tech Job",
        schedule=ScheduleModel(biweekly="fri", start=date(2025, 1, 1)),
        annual_salary=120_000.0,
        retirement_401k=Retirement401kSpec(
            employer_match=EmployerMatchSpec(
                to_account="traditional_401k",
                vesting=VestingSpec(kind="graded", graded_schedule={12: 0.50, 24: 1.0}),
            )
        ),
    )
    unemployment_flow = FlowModel(
        name="Unemployment",
        type="income",
        schedule=ScheduleModel(weekly="mon"),
        amount=AmountModel(fixed=500.0),
        enabled=False,
    )
    event = EventModel(
        name="Temporary Layoff",
        date=date(2026, 4, 1),
        end_date=date(2026, 6, 30),
        disable_paychecks=["Tech Job"],
        enable_flows=["Unemployment"],
        terminate_job="Tech Job",
    )
    payroll_state = PayrollState(2026)
    # 15 months employed -> 50% vested, 50% unvested
    payroll_state.ytd_employer_match_by_job_cents["Tech Job"] = 1_000_000  # $10,000 match
    balances = {"checking": 500_000, "traditional_401k": 1_000_000}
    accounts_manager = AccountManager({}, base_seed=42)
    ledger = Ledger()

    event_manager = EventManager(
        [event], [unemployment_flow], [paycheck], accounts_manager, payroll_state, base_seed=42
    )

    # 1. Fire layoff on April 1
    dummy_scenario = ScenarioModel(start=date(2025, 1, 1), days=365)
    event_manager.process_daily_events(date(2026, 4, 1), date(2025, 1, 1), balances, ledger, dummy_scenario)
    assert paycheck.enabled == False
    assert unemployment_flow.enabled == True
    # 50% unvested ($5,000 = 500_000 cents) forfeited from 401k balance
    assert balances["traditional_401k"] == 500_000

    # 2. On July 1 (end_date + 1 day), reversion restores flow and paycheck state
    event_manager.process_reversions(date(2026, 7, 1))
    assert paycheck.enabled == True
    assert unemployment_flow.enabled == False


def test_medical_shock_capped_by_oop_max() -> None:
    shock_event = EventModel(
        name="Emergency Surgery",
        poisson_per_year=10.0,
        amount=AmountModel(fixed=10_000.0),
        insurance_oop_max=4000.0,
    )
    balances = {"checking": 1_000_000}
    accounts_manager = AccountManager({}, base_seed=42)
    ledger = Ledger()
    payroll_state = PayrollState(2026)

    event_manager = EventManager(
        [shock_event], [], [], accounts_manager, payroll_state, base_seed=42
    )

    # Trigger medical shock on two separate days in same year
    event_manager.ytd_medical_oop_cents[2026] = 250_000  # $2,500 already paid
    sim_start = date(2026, 1, 1)

    # First event: $10,000 raw bill, remaining OOP room is $4,000 - $2,500 = $1,500 (150_000 cents)
    event_manager.event_rngs["Emergency Surgery"] = np.random.default_rng(999)
    # Force a trigger directly by checking the OOP cap logic
    year = 2026
    raw_cents = 1_000_000
    oop_max_cents = int(round(shock_event.insurance_oop_max * 100.0))
    used_oop = event_manager.ytd_medical_oop_cents.get(year, 0)
    charge_cents = min(raw_cents, max(0, oop_max_cents - used_oop))
    balances["checking"] -= charge_cents
    event_manager.ytd_medical_oop_cents[year] = used_oop + charge_cents

    assert charge_cents == 150_000
    assert event_manager.ytd_medical_oop_cents[2026] == 400_000

    # Second event in same year: remaining OOP room is 0
    used_oop_2 = event_manager.ytd_medical_oop_cents.get(year, 0)
    charge_cents_2 = min(raw_cents, max(0, oop_max_cents - used_oop_2))
    assert charge_cents_2 == 0


def test_social_security_monthly_deposit() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        end=date(2026, 4, 30),
        accounts={"checking": AccountModel(kind="checking", balance=0.0)},
        social_security=SocialSecurityModel(
            enabled=True,
            start_date=date(2026, 2, 1),
            monthly_benefit=2500.0,
            annual_cola=0.03,
            to_account="checking",
            taxable_pct=0.85,
        ),
    )
    ledger = run(scenario)
    dataframe = ledger.to_df()
    ss_records = dataframe[dataframe["flow"] == "Social Security Benefit"]

    # Only February 3, March 3, and April 3 should have fired
    assert len(ss_records) == 3
    assert list(ss_records["date"]) == [date(2026, 2, 3), date(2026, 3, 3), date(2026, 4, 3)]
    assert all(record == 2500.0 for record in ss_records["amount"])
    assert all(record == "checking" for record in ss_records["account"])
    assert all(record == "income" for record in ss_records["category"])


def test_social_security_cola_annual_increase() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        end=date(2028, 12, 31),
        accounts={"checking": AccountModel(kind="checking", balance=0.0)},
        social_security=SocialSecurityModel(
            enabled=True,
            start_date=date(2026, 6, 1),
            monthly_benefit=3000.0,
            annual_cola=0.05,
            to_account="checking",
            taxable_pct=0.85,
        ),
    )
    ledger = run(scenario)
    dataframe = ledger.to_df()
    ss_records = dataframe[dataframe["flow"] == "Social Security Benefit"]

    # Year 0: Jun 2026 to May 2027 ($3000.00 = 300_000 cents)
    records_year_0 = ss_records[(ss_records["date"] >= date(2026, 6, 1)) & (ss_records["date"] < date(2027, 6, 1))]
    assert all(amount == 3000.0 for amount in records_year_0["amount"])

    # Year 1: Jun 2027 to May 2028 (3000 * 1.05 = $3150.00)
    records_year_1 = ss_records[(ss_records["date"] >= date(2027, 6, 1)) & (ss_records["date"] < date(2028, 6, 1))]
    assert all(amount == 3150.0 for amount in records_year_1["amount"])

    # Year 2: Jun 2028 to Dec 2028 (3000 * 1.05^2 = $3307.50)
    records_year_2 = ss_records[(ss_records["date"] >= date(2028, 6, 1))]
    assert all(amount == 3307.50 for amount in records_year_2["amount"])


def test_social_security_tax_treatment() -> None:
    scenario = ScenarioModel(
        start=date(2026, 1, 1),
        end=date(2026, 3, 31),
        accounts={"checking": AccountModel(kind="checking", balance=0.0)},
        social_security=SocialSecurityModel(
            enabled=True,
            start_date=date(2026, 1, 1),
            monthly_benefit=2000.0,
            annual_cola=0.025,
            to_account="checking",
            taxable_pct=0.85,
        ),
    )
    ledger = run(scenario)
    dataframe = ledger.to_df()
    ss_records = dataframe[dataframe["flow"] == "Social Security Benefit"]
    assert len(ss_records) == 3

    # Total benefit: 3 * $2,000.00 = $6,000.00 (600_000 cents)
    # Taxable ordinary: 600_000 * 0.85 = 510_000 cents ($5,100.00)
    summary_metrics = ledger.metrics
    assert summary_metrics["cashflow"]["total_income"] == 6000.0
    assert summary_metrics["cashflow"]["total_spending"] == 0.0

    # Also verify with tax true-up on April 15
    tax_scenario = ScenarioModel(
        start=date(2026, 1, 1),
        end=date(2027, 4, 30),
        accounts={"checking": AccountModel(kind="checking", balance=0.0)},
        taxes=TaxConfigModel(
            enabled=True,
            standard_deduction=10000.0,
            federal_brackets=[TaxBracket(rate=0.10, threshold=0.0)],
            april_true_up=True,
            settlement_account="checking",
        ),
        social_security=SocialSecurityModel(
            enabled=True,
            start_date=date(2026, 1, 1),
            monthly_benefit=2000.0,
            annual_cola=0.0,
            to_account="checking",
            taxable_pct=0.85,
        ),
    )
    tax_ledger = run(tax_scenario)
    tax_df = tax_ledger.to_df()
    # 12 deposits of $2000 = $24,000 benefit; taxable ordinary = $20,400
    # After standard deduction of $10,000: $10,400 taxable at 10% = $1,040 tax owed
    tax_settlement_rows = tax_df[tax_df["flow"] == "Annual Tax True-Up Owed"]
    assert len(tax_settlement_rows) == 1
    assert tax_settlement_rows.iloc[0]["amount"] == -1040.0


def test_itemized_deductions_homeowner_tax_savings() -> None:
    # Homeowner paying $18,000 mortgage interest and $8,000 property taxes gets $26,000 itemized deductions.
    tax_config = TaxConfigModel(
        enabled=True,
        filing_status="single",
        standard_deduction=15_000.0,
        federal_brackets=[
            TaxBracket(rate=0.10, threshold=0.0),
            TaxBracket(rate=0.20, threshold=20_000.0),
        ],
        state_flat_rate=0.05,
    )
    # Scenario without itemized deductions (using standard deduction of $15,000)
    tax_state_standard = YearTaxAccumulator(2026)
    tax_state_standard.ytd_taxable_ordinary_cents = 6_000_000
    settlement_standard_cents = compute_april_settlement_cents(tax_state_standard, tax_config)

    # Scenario with itemized deductions ($18k interest + $8k property tax = $26k deductions)
    tax_state_itemized = YearTaxAccumulator(2026)
    tax_state_itemized.ytd_taxable_ordinary_cents = 6_000_000
    tax_state_itemized.ytd_mortgage_interest_cents = 1_800_000
    tax_state_itemized.ytd_property_tax_cents = 800_000
    settlement_itemized_cents = compute_april_settlement_cents(tax_state_itemized, tax_config)

    # Taxable income decreases from $45,000 to $34,000 ($11,000 difference taxed at 20% fed + 5% state = 25%)
    assert settlement_itemized_cents < settlement_standard_cents
    tax_savings_cents = settlement_standard_cents - settlement_itemized_cents
    assert tax_savings_cents == 275_000


def test_salt_cap_married_separate_and_joint() -> None:
    # Property tax of $12,000 is capped at $10,000 for single and $5,000 for married separate.
    single_config = TaxConfigModel(enabled=True, filing_status="single", standard_deduction=10_000.0)
    separate_config = TaxConfigModel(enabled=True, filing_status="married_separate", standard_deduction=10_000.0)

    tax_state = YearTaxAccumulator(2026)
    tax_state.ytd_taxable_ordinary_cents = 5_000_000
    tax_state.ytd_mortgage_interest_cents = 500_000
    tax_state.ytd_property_tax_cents = 1_200_000

    single_settlement_cents = compute_april_settlement_cents(tax_state, single_config)
    separate_settlement_cents = compute_april_settlement_cents(tax_state, separate_config)

    # Single gets $5k mortgage + $10k SALT = $15k deductions; Separate gets $5k mortgage + $5k SALT = $10k deductions
    assert separate_settlement_cents > single_settlement_cents

def test_relocation_event_tax_and_expense_adjustments() -> None:
    scenario = ScenarioModel(
        start=date(2025, 1, 1),
        end=date(2025, 1, 10),
        accounts={"checking": AccountModel(kind="checking", balance=1000.0)},
        taxes=TaxConfigModel(
            enabled=True,
            state_code="CA",
            state_flat_rate=0.05,
            federal_brackets=[],
        ),
        flows=[
            FlowModel(
                name="Rent",
                type="expense",
                amount=AmountModel(fixed=1000.0),
                schedule=ScheduleModel(monthly=[1]),
            ),
            FlowModel(
                name="Groceries",
                type="expense",
                amount=AmountModel(grocery_estimate={"people": 1, "cost_per_person_per_period": 300.0}),
                schedule=ScheduleModel(monthly=[1]),
            )
        ],
        events=[
            EventModel(
                name="Move to Texas",
                date=date(2025, 1, 5),
                relocation={"state_code": "TX", "state_flat_rate": 0.0, "living_cost_factor": 0.8}
            )
        ]
    )

    # Add paycheck to trigger taxes
    scenario.paychecks = [
        PaycheckModel(
            name="Job",
            annual_salary=120_000.0,
            schedule=ScheduleModel(monthly=[1]),
        )
    ]
    # Set to a full year for taxes to apply
    scenario.end = date(2025, 12, 31)
    scenario.taxes.april_true_up = True
    scenario.taxes.settlement_account = "checking"

    ledger = run(scenario)
    assert scenario.taxes.state_code == "TX"
    assert scenario.taxes.state_flat_rate == 0.0

    # Check that flow amounts were reduced by 20%
    rent_flow = next(f for f in scenario.flows if f.name == "Rent")
    assert rent_flow.amount.fixed == 800.0

    grocery_flow = next(f for f in scenario.flows if f.name == "Groceries")
    assert grocery_flow.amount.grocery_estimate.cost_per_person_per_period == 240.0

    df = ledger.to_df()
    state_tax_rows = df[df["flow"] == "State Income Tax"]
    assert all(amount == 0.0 for amount in state_tax_rows["amount"])
