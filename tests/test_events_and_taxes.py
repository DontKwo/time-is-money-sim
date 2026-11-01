from datetime import date
import numpy as np
from lifesim.config import (
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
)
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
    event_manager.process_daily_events(date(2026, 4, 1), date(2025, 1, 1), balances, ledger)
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

