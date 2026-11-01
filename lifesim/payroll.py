import math
from datetime import date
from typing import Optional, Dict, Any, Tuple, List
import numpy as np
from .config import (
    PaycheckModel,
    RSUGrantModel,
    BonusSpec,
    TaxConfigModel,
    MatchTier,
    default_single_federal_brackets,
)
from .macro import MacroState
from .taxes import (
    compute_fica_cents,
    compute_progressive_tax_cents,
)
from .amounts import get_amount, _sample_base_dollars


class PayrollState:
    def __init__(self, year: int) -> None:
        self.year = year
        self.ytd_gross_cents: int = 0
        self.ytd_gross_by_job_cents: Dict[str, int] = {}
        self.ytd_fica_wages_cents: int = 0
        self.ytd_taxable_ordinary_cents: int = 0
        self.ytd_emp_401k_cents: int = 0
        self.ytd_emp_401k_by_job_cents: Dict[str, int] = {}
        self.ytd_total_401k_by_job_cents: Dict[str, int] = {}
        self.ytd_employer_match_by_job_cents: Dict[str, int] = {}
        self.ytd_hsa_cents: int = 0
        self.ytd_espp_by_job_cents: Dict[str, int] = {}
        self.ytd_fed_withheld_cents: int = 0
        self.ytd_state_withheld_cents: int = 0
        self.ytd_fica_withheld_cents: int = 0
        self.unclaimed_401k_match_cents: int = 0
        self.paycheck_counts_this_year: Dict[str, int] = {}
        self.unvested_match_by_job_cents: Dict[str, int] = {}

    def reset_year(self, new_year: int) -> None:
        self.year = new_year
        self.ytd_gross_cents = 0
        self.ytd_gross_by_job_cents.clear()
        self.ytd_fica_wages_cents = 0
        self.ytd_taxable_ordinary_cents = 0
        self.ytd_emp_401k_cents = 0
        self.ytd_emp_401k_by_job_cents.clear()
        self.ytd_total_401k_by_job_cents.clear()
        self.ytd_employer_match_by_job_cents.clear()
        self.ytd_hsa_cents = 0
        self.ytd_espp_by_job_cents.clear()
        self.ytd_fed_withheld_cents = 0
        self.ytd_state_withheld_cents = 0
        self.ytd_fica_withheld_cents = 0
        self.paycheck_counts_this_year.clear()


def _infer_pay_periods(paycheck: PaycheckModel) -> int:
    if paycheck.pay_periods_per_year is not None:
        return paycheck.pay_periods_per_year
    sched = paycheck.schedule
    if sched.weekly is not None:
        return 52
    if sched.biweekly is not None:
        return 26
    if sched.semimonthly is not None:
        return 24
    if sched.monthly is not None:
        return 12
    return 26


def _resolve_annual_salary(
    paycheck: PaycheckModel,
    current_date: date,
    sim_start: date,
) -> float:
    base_salary = paycheck.annual_salary if paycheck.annual_salary is not None else 0.0
    effective_anchor = paycheck.schedule.start or sim_start

    # Check for active salary step
    if paycheck.salary_steps:
        matching = [s for s in paycheck.salary_steps if s.start <= current_date]
        if matching:
            latest_step = max(matching, key=lambda s: s.start)
            base_salary = latest_step.annual_salary
            effective_anchor = latest_step.start

    # Count raise occurrences passed between anchor and current date
    raise_count = 0
    if paycheck.annual_raise_pct > 0.0:
        for year_val in range(effective_anchor.year, current_date.year + 1):
            raise_date = date(year_val, paycheck.raise_month, paycheck.raise_day)
            if effective_anchor < raise_date <= current_date:
                raise_count += 1

    raise_multiplier = (1.0 + paycheck.annual_raise_pct) ** raise_count
    return base_salary * raise_multiplier


def _compute_gross_pay_cents(
    paycheck: PaycheckModel,
    current_date: date,
    sim_start: date,
    active_rng: np.random.Generator,
) -> int:
    if paycheck.gross_per_period is not None:
        return get_amount(paycheck.gross_per_period, active_rng)

    if paycheck.hourly_pay is not None:
        h_spec = paycheck.hourly_pay
        if isinstance(h_spec.hours_per_period, (int, float)):
            hours = float(h_spec.hours_per_period)
        else:
            hours = max(0.0, float(active_rng.normal(h_spec.hours_per_period[0], h_spec.hours_per_period[1])))
        regular_hours = min(hours, h_spec.overtime_threshold)
        ot_hours = max(0.0, hours - h_spec.overtime_threshold)
        regular_dollars = regular_hours * h_spec.hourly_rate
        ot_rate = h_spec.hourly_rate * h_spec.overtime_multiplier
        ot_dollars = ot_hours * ot_rate
        return int(round((regular_dollars + ot_dollars) * 100.0))

    active_salary = _resolve_annual_salary(paycheck, current_date, sim_start)
    periods = _infer_pay_periods(paycheck)
    gross_period_dollars = active_salary / periods
    return int(round(gross_period_dollars * 100.0))


def process_paycheck(
    paycheck: PaycheckModel,
    current_date: date,
    sim_start: date,
    payroll_state: PayrollState,
    balances: Dict[str, int],
    ledger: Any,
    tax_config: Optional[TaxConfigModel] = None,
    macro_state: Optional[MacroState] = None,
    rng: Optional[np.random.Generator] = None,
) -> None:
    active_rng = rng if rng is not None else np.random.default_rng()
    job_name = paycheck.name
    current_count = payroll_state.paycheck_counts_this_year.get(job_name, 0)
    payroll_state.paycheck_counts_this_year[job_name] = current_count + 1
    is_first_paycheck = payroll_state.paycheck_counts_this_year[job_name] == 1

    # 1. Gross Pay
    gross_cents = _compute_gross_pay_cents(paycheck, current_date, sim_start, active_rng)
    payroll_state.ytd_gross_cents += gross_cents
    current_job_gross = payroll_state.ytd_gross_by_job_cents.get(job_name, 0)
    payroll_state.ytd_gross_by_job_cents[job_name] = current_job_gross + gross_cents

    # 2. Pre-tax Medical & HSA
    pretax_med_cents = min(gross_cents, int(round(paycheck.pretax_deductions_per_period * 100.0)))
    emp_hsa_cents = 0
    er_hsa_cents = 0

    if paycheck.hsa and paycheck.hsa.enabled:
        hsa_spec = paycheck.hsa
        annual_cap = hsa_spec.annual_limit
        if macro_state:
            annual_cap = macro_state.get_indexed_limit(annual_cap, 50.0)
        hsa_limit_cents = int(round(annual_cap * 100.0))
        hsa_room = max(0, hsa_limit_cents - payroll_state.ytd_hsa_cents)

        seed_cents = int(round(hsa_spec.employer_annual_seed * 100.0)) if is_first_paycheck else 0
        desired_er = int(round(hsa_spec.employer_per_period * 100.0)) + seed_cents
        er_hsa_cents = min(hsa_room, desired_er)
        hsa_room = max(0, hsa_room - er_hsa_cents)

        fixed_emp_hsa = int(round(hsa_spec.employee_per_period * 100.0))
        pct_emp_hsa = int(round(gross_cents * hsa_spec.employee_pct))
        desired_emp = fixed_emp_hsa + pct_emp_hsa
        allowed_emp = min(hsa_room, max(0, gross_cents - pretax_med_cents))
        emp_hsa_cents = min(desired_emp, allowed_emp)

        payroll_state.ytd_hsa_cents += er_hsa_cents + emp_hsa_cents
        to_acc = hsa_spec.to_account
        if er_hsa_cents > 0:
            balances[to_acc] = balances.get(to_acc, 0) + er_hsa_cents
            ledger.append(current_date, f"{job_name} HSA Employer", er_hsa_cents, to_acc, balances[to_acc])
        if emp_hsa_cents > 0:
            balances[to_acc] = balances.get(to_acc, 0) + emp_hsa_cents
            ledger.append(current_date, f"{job_name} HSA Employee", emp_hsa_cents, to_acc, balances[to_acc])

    # 3. Employee 401(k) Traditional & Roth deferrals
    trad_401k_cents = 0
    roth_401k_cents = 0
    total_415c_cap_cents = 7_000_000

    if paycheck.retirement_401k and paycheck.retirement_401k.enabled:
        ret_spec = paycheck.retirement_401k
        anchor_year = (paycheck.schedule.start or sim_start).year
        years_elapsed = max(0, current_date.year - anchor_year)
        escalated_trad = ret_spec.traditional_pct + years_elapsed * ret_spec.auto_escalate_pct_per_year
        trad_pct = min(ret_spec.auto_escalate_max_pct, escalated_trad)
        desired_trad = int(round(gross_cents * trad_pct)) + int(round(ret_spec.traditional_fixed * 100.0))
        desired_roth = int(round(gross_cents * ret_spec.roth_pct)) + int(round(ret_spec.roth_fixed * 100.0))

        emp_limit = ret_spec.annual_employee_limit + ret_spec.catch_up_limit
        total_limit = ret_spec.annual_total_limit
        if macro_state:
            emp_limit = macro_state.get_indexed_limit(emp_limit, 500.0)
            total_limit = macro_state.get_indexed_limit(total_limit, 500.0)
        total_415c_cap_cents = int(round(total_limit * 100.0))

        emp_cap_cents = int(round(emp_limit * 100.0))
        emp_room = max(0, emp_cap_cents - payroll_state.ytd_emp_401k_cents)
        job_total_401k = payroll_state.ytd_total_401k_by_job_cents.get(job_name, 0)
        room_415c = max(0, total_415c_cap_cents - job_total_401k)
        available_salary = max(0, gross_cents - pretax_med_cents - emp_hsa_cents)
        effective_room = min(emp_room, room_415c, available_salary)

        trad_401k_cents = min(desired_trad, effective_room)
        roth_401k_cents = min(desired_roth, effective_room - trad_401k_cents)

        payroll_state.ytd_emp_401k_cents += trad_401k_cents + roth_401k_cents
        payroll_state.ytd_emp_401k_by_job_cents[job_name] = (
            payroll_state.ytd_emp_401k_by_job_cents.get(job_name, 0) + trad_401k_cents + roth_401k_cents
        )
        payroll_state.ytd_total_401k_by_job_cents[job_name] = job_total_401k + trad_401k_cents + roth_401k_cents

        if trad_401k_cents > 0:
            trad_acc = ret_spec.traditional_account
            balances[trad_acc] = balances.get(trad_acc, 0) + trad_401k_cents
            ledger.append(current_date, f"{job_name} 401k Traditional", trad_401k_cents, trad_acc, balances[trad_acc])
        if roth_401k_cents > 0:
            roth_acc = ret_spec.roth_account
            balances[roth_acc] = balances.get(roth_acc, 0) + roth_401k_cents
            ledger.append(current_date, f"{job_name} 401k Roth", roth_401k_cents, roth_acc, balances[roth_acc])

    # 4. Employer 401(k) Match
    er_match_total_cents = 0
    if (
        paycheck.retirement_401k
        and paycheck.retirement_401k.enabled
        and paycheck.retirement_401k.employer_match
        and paycheck.retirement_401k.employer_match.enabled
    ):
        match_spec = paycheck.retirement_401k.employer_match
        tiers = (
            match_spec.tiers
            if match_spec.tiers
            else [MatchTier(match_rate=match_spec.match_rate, band_pct=match_spec.up_to_pct)]
        )
        emp_deferral_cents = trad_401k_cents + roth_401k_cents
        actual_emp_pct = emp_deferral_cents / gross_cents if gross_cents > 0 else 0.0

        remaining_emp_pct = actual_emp_pct
        matched_pct = 0.0
        max_possible_match_pct = 0.0
        for tier in tiers:
            max_possible_match_pct += tier.band_pct * tier.match_rate
            band_used = min(remaining_emp_pct, tier.band_pct)
            matched_pct += band_used * tier.match_rate
            remaining_emp_pct = max(0.0, remaining_emp_pct - band_used)

        raw_match_cents = int(round(gross_cents * matched_pct))
        max_match_cents = int(round(gross_cents * max_possible_match_pct))
        unclaimed = max(0, max_match_cents - raw_match_cents)
        payroll_state.unclaimed_401k_match_cents += unclaimed

        fixed_er_cents = int(round(gross_cents * match_spec.employer_fixed_pct))
        room_415c = max(0, total_415c_cap_cents - payroll_state.ytd_total_401k_by_job_cents.get(job_name, 0))
        er_match_total_cents = min(raw_match_cents + fixed_er_cents, room_415c)

        payroll_state.ytd_employer_match_by_job_cents[job_name] = (
            payroll_state.ytd_employer_match_by_job_cents.get(job_name, 0) + er_match_total_cents
        )
        payroll_state.ytd_total_401k_by_job_cents[job_name] += er_match_total_cents

        if er_match_total_cents > 0:
            to_acc = match_spec.to_account
            balances[to_acc] = balances.get(to_acc, 0) + er_match_total_cents
            ledger.append(
                current_date, f"{job_name} 401k Employer Match", er_match_total_cents, to_acc, balances[to_acc]
            )

    # 5. FICA and Income Tax Withholding
    fica_wages_cents = max(0, gross_cents - pretax_med_cents - emp_hsa_cents)
    ss_wage_base = tax_config.ss_wage_base if tax_config else 176_100.0
    if macro_state:
        ss_wage_base = macro_state.get_indexed_limit(ss_wage_base, 500.0)
    ss_base_cents = int(round(ss_wage_base * 100.0))

    ss_tax_cents, med_tax_cents, total_fica_cents = compute_fica_cents(
        fica_wages_cents, payroll_state.ytd_fica_wages_cents, ss_base_cents
    )
    payroll_state.ytd_fica_wages_cents += fica_wages_cents
    payroll_state.ytd_fica_withheld_cents += total_fica_cents

    taxable_period_wages_cents = max(0, fica_wages_cents - trad_401k_cents)
    payroll_state.ytd_taxable_ordinary_cents += taxable_period_wages_cents

    withhold = paycheck.withholding
    if withhold.mode == "none":
        fed_withheld_cents = 0
        state_withheld_cents = 0
    elif withhold.mode == "effective_rate":
        fed_withheld_cents = int(round(taxable_period_wages_cents * withhold.effective_federal_rate))
        combined_state = withhold.effective_state_rate + withhold.local_tax_rate
        state_withheld_cents = int(round(taxable_period_wages_cents * combined_state))
    else:
        periods = _infer_pay_periods(paycheck)
        annual_projected = taxable_period_wages_cents * periods
        std_ded_dollars = tax_config.standard_deduction if tax_config and tax_config.standard_deduction else 15000.0
        std_ded_cents = int(round(std_ded_dollars * 100.0))
        fed_brackets = tax_config.federal_brackets if tax_config else default_single_federal_brackets()
        annual_fed_tax = compute_progressive_tax_cents(max(0, annual_projected - std_ded_cents), fed_brackets)
        fed_withheld_cents = int(round(annual_fed_tax / periods))

        if tax_config and tax_config.state_brackets:
            taxable_state = max(0, annual_projected - std_ded_cents)
            annual_state_tax = compute_progressive_tax_cents(taxable_state, tax_config.state_brackets)
        else:
            state_rate = tax_config.state_flat_rate if tax_config else 0.0
            annual_state_tax = int(round(annual_projected * state_rate))
        state_withheld_cents = int(round(annual_state_tax / periods))

    payroll_state.ytd_fed_withheld_cents += fed_withheld_cents
    payroll_state.ytd_state_withheld_cents += state_withheld_cents
    taxes_cents = (total_fica_cents if withhold.include_fica else 0) + fed_withheld_cents + state_withheld_cents

    # 6. Post-tax deductions, Mega-Backdoor Roth, ESPP, and Net Direct Deposit
    after_tax_roth_cents = 0
    if paycheck.retirement_401k and paycheck.retirement_401k.enabled:
        ret_spec = paycheck.retirement_401k
        if ret_spec.after_tax_roth_pct > 0.0:
            desired_after_tax = int(round(gross_cents * ret_spec.after_tax_roth_pct))
            room_415c = max(0, total_415c_cap_cents - payroll_state.ytd_total_401k_by_job_cents.get(job_name, 0))
            after_tax_roth_cents = min(desired_after_tax, room_415c)
            payroll_state.ytd_total_401k_by_job_cents[job_name] += after_tax_roth_cents
            if after_tax_roth_cents > 0:
                roth_acc = ret_spec.roth_account
                balances[roth_acc] = balances.get(roth_acc, 0) + after_tax_roth_cents
                ledger.append(
                    current_date, f"{job_name} Mega-Backdoor Roth 401k", after_tax_roth_cents, roth_acc, balances[roth_acc]
                )

    espp_cents = 0
    if paycheck.espp and paycheck.espp.enabled:
        espp_cents = int(round(gross_cents * paycheck.espp.contribution_pct))
        current_espp = payroll_state.ytd_espp_by_job_cents.get(job_name, 0)
        payroll_state.ytd_espp_by_job_cents[job_name] = current_espp + espp_cents

    posttax_ded_cents = int(round(paycheck.posttax_deductions_per_period * 100.0))
    deductions_sum = (
        pretax_med_cents
        + emp_hsa_cents
        + trad_401k_cents
        + taxes_cents
        + roth_401k_cents
        + after_tax_roth_cents
        + espp_cents
        + posttax_ded_cents
    )
    net_pay_cents = max(0, gross_cents - deductions_sum)

    # Direct deposit routing
    splits = paycheck.direct_deposit
    if not splits:
        default_account = "checking"
        balances[default_account] = balances.get(default_account, 0) + net_pay_cents
        ledger.append(current_date, f"{job_name} Net Pay", net_pay_cents, default_account, balances[default_account])
    else:
        remaining_net = net_pay_cents
        for split in splits:
            if split.remainder:
                allocated = remaining_net
            elif split.fixed is not None:
                allocated = min(remaining_net, int(round(split.fixed * 100.0)))
            elif split.pct is not None:
                allocated = min(remaining_net, int(round(net_pay_cents * split.pct)))
            else:
                allocated = remaining_net

            target_account = split.to
            balances[target_account] = balances.get(target_account, 0) + allocated
            ledger.append(current_date, f"{job_name} Net Pay", allocated, target_account, balances[target_account])
            remaining_net = max(0, remaining_net - allocated)


def process_year_end_true_up(
    paycheck: PaycheckModel,
    current_date: date,
    payroll_state: PayrollState,
    balances: Dict[str, int],
    ledger: Any,
) -> None:
    job_name = paycheck.name
    if not (
        paycheck.retirement_401k
        and paycheck.retirement_401k.enabled
        and paycheck.retirement_401k.employer_match
        and paycheck.retirement_401k.employer_match.enabled
        and paycheck.retirement_401k.employer_match.annual_true_up
    ):
        return

    match_spec = paycheck.retirement_401k.employer_match
    ytd_gross = payroll_state.ytd_gross_by_job_cents.get(job_name, 0)
    if ytd_gross <= 0:
        return

    ytd_emp = payroll_state.ytd_emp_401k_by_job_cents.get(job_name, 0)
    annual_emp_pct = ytd_emp / ytd_gross
    tiers = (
        match_spec.tiers
        if match_spec.tiers
        else [MatchTier(match_rate=match_spec.match_rate, band_pct=match_spec.up_to_pct)]
    )

    remaining_emp_pct = annual_emp_pct
    annual_matched_pct = 0.0
    for tier in tiers:
        band_used = min(remaining_emp_pct, tier.band_pct)
        annual_matched_pct += band_used * tier.match_rate
        remaining_emp_pct = max(0.0, remaining_emp_pct - band_used)

    entitled_match_cents = int(round(ytd_gross * annual_matched_pct))
    received_match_cents = payroll_state.ytd_employer_match_by_job_cents.get(job_name, 0)

    if entitled_match_cents > received_match_cents:
        shortfall_cents = entitled_match_cents - received_match_cents
        total_415c_cap = int(round(paycheck.retirement_401k.annual_total_limit * 100.0))
        room_415c = max(0, total_415c_cap - payroll_state.ytd_total_401k_by_job_cents.get(job_name, 0))
        true_up_cents = min(shortfall_cents, room_415c)

        if true_up_cents > 0:
            payroll_state.ytd_employer_match_by_job_cents[job_name] += true_up_cents
            payroll_state.ytd_total_401k_by_job_cents[job_name] += true_up_cents
            net_unclaimed = payroll_state.unclaimed_401k_match_cents - true_up_cents
            payroll_state.unclaimed_401k_match_cents = max(0, net_unclaimed)
            to_acc = match_spec.to_account
            balances[to_acc] = balances.get(to_acc, 0) + true_up_cents
            ledger.append(
                current_date, f"{job_name} 401k Employer True-Up", true_up_cents, to_acc, balances[to_acc]
            )


def process_espp_purchase(
    paycheck: PaycheckModel,
    current_date: date,
    payroll_state: PayrollState,
    balances: Dict[str, int],
    ledger: Any,
) -> None:
    job_name = paycheck.name
    if not (paycheck.espp and paycheck.espp.enabled):
        return

    escrow_cents = payroll_state.ytd_espp_by_job_cents.get(job_name, 0)
    if escrow_cents <= 0:
        return

    discount = paycheck.espp.discount_pct
    purchase_value_cents = int(round(escrow_cents / (1.0 - discount)))
    to_acc = paycheck.espp.to_account
    balances[to_acc] = balances.get(to_acc, 0) + purchase_value_cents
    ledger.append(current_date, f"{job_name} ESPP Purchase", purchase_value_cents, to_acc, balances[to_acc])
    payroll_state.ytd_espp_by_job_cents[job_name] = 0


def process_rsu_vest(
    grant: RSUGrantModel,
    current_date: date,
    sim_start: date,
    payroll_state: PayrollState,
    balances: Dict[str, int],
    ledger: Any,
    rng: Optional[np.random.Generator] = None,
    cost_bases: Optional[Dict[str, int]] = None,
) -> None:
    active_rng = rng if rng is not None else np.random.default_rng()
    if grant.gross_vest_amount is not None:
        gross_cents = get_amount(grant.gross_vest_amount, active_rng)
    elif grant.shares_per_vest is not None and grant.initial_share_price is not None:
        years_elapsed = max(0, (current_date - sim_start).days) / 365.25
        share_price = grant.initial_share_price * ((1.0 + grant.growth_rate) ** years_elapsed)
        gross_cents = int(round(grant.shares_per_vest * share_price * 100.0))
    else:
        gross_cents = 0

    if gross_cents <= 0:
        return

    withholding_cents = int(round(gross_cents * grant.withhold_tax_rate))
    net_vest_cents = gross_cents - withholding_cents
    payroll_state.ytd_taxable_ordinary_cents += gross_cents
    payroll_state.ytd_fed_withheld_cents += withholding_cents

    to_acc = grant.to_account
    balances[to_acc] = balances.get(to_acc, 0) + net_vest_cents
    if cost_bases is not None:
        cost_bases[to_acc] = cost_bases.get(to_acc, 0) + net_vest_cents
    ledger.append(current_date, f"{grant.name} RSU Vest", net_vest_cents, to_acc, balances[to_acc])


def process_bonus(
    bonus: BonusSpec,
    paycheck: PaycheckModel,
    current_date: date,
    sim_start: date,
    payroll_state: PayrollState,
    balances: Dict[str, int],
    ledger: Any,
    tax_config: Optional[TaxConfigModel] = None,
    macro_state: Optional[MacroState] = None,
    rng: Optional[np.random.Generator] = None,
) -> int:
    active_rng = rng if rng is not None else np.random.default_rng()
    job_name = paycheck.name

    if bonus.gross_amount is not None:
        gross_cents = get_amount(bonus.gross_amount, active_rng)
    elif bonus.target_pct_of_salary is not None:
        base_salary = _resolve_annual_salary(paycheck, current_date, sim_start)
        multiplier_val = _sample_base_dollars(bonus.multiplier, active_rng) if bonus.multiplier else 1.0
        gross_dollars = base_salary * bonus.target_pct_of_salary * multiplier_val
        gross_cents = int(round(gross_dollars * 100.0))
    else:
        gross_cents = 0

    if gross_cents <= 0:
        return 0

    payroll_state.ytd_gross_cents += gross_cents
    current_job_gross = payroll_state.ytd_gross_by_job_cents.get(job_name, 0)
    payroll_state.ytd_gross_by_job_cents[job_name] = current_job_gross + gross_cents

    trad_401k_cents = 0
    roth_401k_cents = 0
    if (
        bonus.apply_401k
        and paycheck.retirement_401k
        and paycheck.retirement_401k.enabled
    ):
        ret_spec = paycheck.retirement_401k
        years_elapsed = max(0, current_date.year - sim_start.year)
        escalated_trad = ret_spec.traditional_pct + years_elapsed * ret_spec.auto_escalate_pct_per_year
        active_trad_pct = min(ret_spec.auto_escalate_max_pct, escalated_trad)
        desired_trad = int(round(gross_cents * active_trad_pct))
        desired_roth = int(round(gross_cents * ret_spec.roth_pct))

        emp_cap_dollars = ret_spec.annual_employee_limit + ret_spec.catch_up_limit
        if macro_state:
            emp_cap_dollars = macro_state.get_indexed_limit(emp_cap_dollars, 500.0)
        emp_cap_cents = int(round(emp_cap_dollars * 100.0))
        emp_room = max(0, emp_cap_cents - payroll_state.ytd_emp_401k_cents)

        total_415c_cap = ret_spec.annual_total_limit
        if macro_state:
            total_415c_cap = macro_state.get_indexed_limit(total_415c_cap, 500.0)
        total_415c_cap_cents = int(round(total_415c_cap * 100.0))
        job_total_401k = payroll_state.ytd_total_401k_by_job_cents.get(job_name, 0)
        room_415c = max(0, total_415c_cap_cents - job_total_401k)

        effective_room = min(emp_room, room_415c, gross_cents)
        trad_401k_cents = min(desired_trad, effective_room)
        roth_401k_cents = min(desired_roth, effective_room - trad_401k_cents)

        payroll_state.ytd_emp_401k_cents += trad_401k_cents + roth_401k_cents
        current_emp_job = payroll_state.ytd_emp_401k_by_job_cents.get(job_name, 0)
        payroll_state.ytd_emp_401k_by_job_cents[job_name] = current_emp_job + trad_401k_cents + roth_401k_cents
        payroll_state.ytd_total_401k_by_job_cents[job_name] = job_total_401k + trad_401k_cents + roth_401k_cents

        if trad_401k_cents > 0:
            trad_acc = ret_spec.traditional_account
            balances[trad_acc] = balances.get(trad_acc, 0) + trad_401k_cents
            ledger.append(current_date, f"{job_name} Bonus 401k Traditional", trad_401k_cents, trad_acc, balances[trad_acc])
        if roth_401k_cents > 0:
            roth_acc = ret_spec.roth_account
            balances[roth_acc] = balances.get(roth_acc, 0) + roth_401k_cents
            ledger.append(current_date, f"{job_name} Bonus 401k Roth", roth_401k_cents, roth_acc, balances[roth_acc])

    ss_wage_base = tax_config.ss_wage_base if tax_config else 176_100.0
    if macro_state:
        ss_wage_base = macro_state.get_indexed_limit(ss_wage_base, 500.0)
    ss_base_cents = int(round(ss_wage_base * 100.0))

    ss_tax_cents, med_tax_cents, total_fica_cents = compute_fica_cents(
        gross_cents, payroll_state.ytd_fica_wages_cents, ss_base_cents
    )
    payroll_state.ytd_fica_wages_cents += gross_cents
    payroll_state.ytd_fica_withheld_cents += total_fica_cents

    taxable_bonus_wages = max(0, gross_cents - trad_401k_cents)
    payroll_state.ytd_taxable_ordinary_cents += taxable_bonus_wages

    fed_withheld_cents = int(round(taxable_bonus_wages * bonus.supplemental_federal_rate))
    payroll_state.ytd_fed_withheld_cents += fed_withheld_cents

    deductions_sum = total_fica_cents + fed_withheld_cents + trad_401k_cents + roth_401k_cents
    net_bonus_cents = max(0, gross_cents - deductions_sum)

    target_account = paycheck.direct_deposit[0].to if paycheck.direct_deposit else "checking"
    balances[target_account] = balances.get(target_account, 0) + net_bonus_cents
    ledger.append(current_date, f"{job_name} Bonus: {bonus.name}", net_bonus_cents, target_account, balances[target_account])
    return net_bonus_cents
