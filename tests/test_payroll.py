from datetime import date, timedelta
from lifesim.config import (
    PaycheckModel,
    ScheduleModel,
    Retirement401kSpec,
    EmployerMatchSpec,
    MatchTier,
    HSASpec,
    WithholdingSpec,
)
from lifesim.payroll import (
    PayrollState,
    process_paycheck,
    process_year_end_true_up,
)
from lifesim.ledger import Ledger


def test_flat_401k_match() -> None:
    paycheck = PaycheckModel(
        name="Software Engineer",
        schedule=ScheduleModel(biweekly="fri"),
        annual_salary=104_000.0,  # $4,000.00 per 26 periods
        pay_periods_per_year=26,
        retirement_401k=Retirement401kSpec(
            traditional_pct=0.06,
            employer_match=EmployerMatchSpec(match_rate=1.0, up_to_pct=0.06),
        ),
        withholding=WithholdingSpec(mode="none"),
    )
    payroll_state = PayrollState(2026)
    balances = {"checking": 0, "traditional_401k": 0}
    ledger = Ledger()

    process_paycheck(
        paycheck, date(2026, 1, 2), date(2026, 1, 1), payroll_state, balances, ledger
    )

    # Gross $4,000. 6% employee is $240 (24_000 cents). Match is $240 (24_000 cents).
    assert payroll_state.ytd_emp_401k_cents == 24_000
    assert balances["traditional_401k"] == 48_000
    assert payroll_state.unclaimed_401k_match_cents == 0


def test_partial_match_unclaimed_tracking() -> None:
    paycheck = PaycheckModel(
        name="Engineer",
        schedule=ScheduleModel(biweekly="fri"),
        annual_salary=104_000.0,
        pay_periods_per_year=26,
        retirement_401k=Retirement401kSpec(
            traditional_pct=0.02,
            employer_match=EmployerMatchSpec(match_rate=1.0, up_to_pct=0.06),
        ),
        withholding=WithholdingSpec(mode="none"),
    )
    payroll_state = PayrollState(2026)
    balances = {"checking": 0, "traditional_401k": 0}
    ledger = Ledger()

    process_paycheck(
        paycheck, date(2026, 1, 2), date(2026, 1, 1), payroll_state, balances, ledger
    )

    # 2% employee = $80 (8_000 cents). Match received = $80. Unclaimed = $160 (16_000 cents).
    assert balances["traditional_401k"] == 16_000
    assert payroll_state.unclaimed_401k_match_cents == 16_000


def test_multi_tier_match() -> None:
    tiers = [
        MatchTier(match_rate=1.0, band_pct=0.03),
        MatchTier(match_rate=0.5, band_pct=0.02),
    ]
    paycheck = PaycheckModel(
        name="Tiered Job",
        schedule=ScheduleModel(biweekly="fri"),
        annual_salary=104_000.0,
        pay_periods_per_year=26,
        retirement_401k=Retirement401kSpec(
            traditional_pct=0.10,
            employer_match=EmployerMatchSpec(tiers=tiers),
        ),
        withholding=WithholdingSpec(mode="none"),
    )
    payroll_state = PayrollState(2026)
    balances = {"checking": 0, "traditional_401k": 0}
    ledger = Ledger()

    process_paycheck(
        paycheck, date(2026, 1, 2), date(2026, 1, 1), payroll_state, balances, ledger
    )

    # 3% * 1.0 + 2% * 0.5 = 4% match on $4,000 = $160 (16_000 cents)
    assert payroll_state.ytd_employer_match_by_job_cents["Tiered Job"] == 16_000


def test_irs_cap_and_december_true_up() -> None:
    paycheck = PaycheckModel(
        name="Tech Job",
        schedule=ScheduleModel(biweekly="fri"),
        annual_salary=104_000.0,
        pay_periods_per_year=26,
        retirement_401k=Retirement401kSpec(
            traditional_pct=0.25,
            annual_employee_limit=23_500.0,
            employer_match=EmployerMatchSpec(match_rate=1.0, up_to_pct=0.06, annual_true_up=True),
        ),
        withholding=WithholdingSpec(mode="none"),
    )
    payroll_state = PayrollState(2026)
    balances = {"checking": 0, "traditional_401k": 0}
    ledger = Ledger()

    # Simulate 26 biweekly paychecks
    for pay_index in range(26):
        pay_date = date(2026, 1, 2) + timedelta(days=pay_index * 14)
        process_paycheck(
            paycheck, pay_date, date(2026, 1, 1), payroll_state, balances, ledger
        )

    # Employee cap 23_500.00 reached: 23 * 1,000 + 1 * 500 + 2 * 0
    assert payroll_state.ytd_emp_401k_cents == 2_350_000
    # Match received during 24 funded paychecks: 24 * 24_000 = 576_000
    assert payroll_state.ytd_employer_match_by_job_cents["Tech Job"] == 576_000

    # Dec 31 True-Up deposits remaining 48_000 cents ($480)
    process_year_end_true_up(
        paycheck, date(2026, 12, 31), payroll_state, balances, ledger
    )
    assert payroll_state.ytd_employer_match_by_job_cents["Tech Job"] == 624_000


def test_hsa_annual_cap_clamping() -> None:
    paycheck = PaycheckModel(
        name="HSA Job",
        schedule=ScheduleModel(biweekly="fri"),
        annual_salary=52_000.0,
        pay_periods_per_year=26,
        hsa=HSASpec(
            employer_annual_seed=1000.0,
            employer_per_period=100.0,
            employee_per_period=200.0,
            annual_limit=4300.0,
        ),
        withholding=WithholdingSpec(mode="none"),
    )
    payroll_state = PayrollState(2026)
    balances = {"hsa": 0, "checking": 0}
    ledger = Ledger()

    for pay_index in range(26):
        pay_date = date(2026, 1, 2) + timedelta(days=pay_index * 14)
        process_paycheck(
            paycheck, pay_date, date(2026, 1, 1), payroll_state, balances, ledger
        )

    # Combined HSA deposits should be exactly clamped at 4300.00 (430_000 cents)
    assert payroll_state.ytd_hsa_cents == 430_000
    assert balances["hsa"] == 430_000
