from typing import List, Tuple
from lifesim.config import TaxBracket, TaxConfigModel


class YearTaxAccumulator:
    def __init__(self, year: int) -> None:
        self.year = year
        self.ytd_gross_cents: int = 0
        self.ytd_fica_wages_cents: int = 0
        self.ytd_taxable_ordinary_cents: int = 0
        self.ytd_taxable_interest_cents: int = 0
        self.ytd_qualified_dividends_cents: int = 0
        self.ytd_realized_cap_gains_cents: int = 0
        self.ytd_traditional_ira_deductible_cents: int = 0
        self.ytd_mortgage_interest_cents: int = 0
        self.ytd_property_tax_cents: int = 0
        self.ytd_fed_withheld_cents: int = 0
        self.ytd_state_withheld_cents: int = 0
        self.ytd_fica_withheld_cents: int = 0


def compute_fica_cents(
    period_fica_wages_cents: int,
    ytd_prior_fica_wages_cents: int,
    ss_wage_base_cents: int = 17_610_000,
    additional_medicare_threshold_cents: int = 20_000_000,
) -> Tuple[int, int, int]:
    if period_fica_wages_cents <= 0:
        return (0, 0, 0)

    # Social Security: 6.2% up to annual wage base
    ss_remaining_room = max(0, ss_wage_base_cents - ytd_prior_fica_wages_cents)
    ss_taxable_cents = min(period_fica_wages_cents, ss_remaining_room)
    ss_tax_cents = int(round(ss_taxable_cents * 0.062))

    # Base Medicare: 1.45% on all FICA wages
    medicare_base_cents = int(round(period_fica_wages_cents * 0.0145))

    # Additional Medicare: 0.9% on wages above threshold
    prior_wages = ytd_prior_fica_wages_cents
    new_wages = prior_wages + period_fica_wages_cents
    if new_wages > additional_medicare_threshold_cents:
        subject_floor = max(prior_wages, additional_medicare_threshold_cents)
        additional_taxable = new_wages - subject_floor
        medicare_additional_cents = int(round(additional_taxable * 0.009))
    else:
        medicare_additional_cents = 0

    total_medicare_cents = medicare_base_cents + medicare_additional_cents
    total_fica_cents = ss_tax_cents + total_medicare_cents
    return (ss_tax_cents, total_medicare_cents, total_fica_cents)


def compute_progressive_tax_cents(taxable_income_cents: int, brackets: List[TaxBracket]) -> int:
    if taxable_income_cents <= 0 or not brackets:
        return 0

    sorted_brackets = sorted(brackets, key=lambda item: item.threshold)
    total_tax_cents = 0

    for idx, bracket in enumerate(sorted_brackets):
        floor_cents = int(round(bracket.threshold * 100.0))
        if taxable_income_cents <= floor_cents:
            continue

        if idx + 1 < len(sorted_brackets):
            ceiling_cents = int(round(sorted_brackets[idx + 1].threshold * 100.0))
            taxable_chunk = min(taxable_income_cents, ceiling_cents) - floor_cents
        else:
            taxable_chunk = taxable_income_cents - floor_cents

        tax_cents = int(round(taxable_chunk * bracket.rate))
        total_tax_cents += tax_cents

    return total_tax_cents


def compute_ltcg_tax_cents(ordinary_taxable_cents: int, ltcg_cents: int, brackets: List[TaxBracket]) -> int:
    if ltcg_cents <= 0 or not brackets:
        return 0

    start_cents = max(0, ordinary_taxable_cents)
    end_cents = start_cents + ltcg_cents
    sorted_brackets = sorted(brackets, key=lambda item: item.threshold)
    total_tax_cents = 0

    for idx, bracket in enumerate(sorted_brackets):
        floor_cents = int(round(bracket.threshold * 100.0))
        if end_cents <= floor_cents:
            continue

        if idx + 1 < len(sorted_brackets):
            ceiling_cents = int(round(sorted_brackets[idx + 1].threshold * 100.0))
            bracket_end = min(end_cents, ceiling_cents)
        else:
            bracket_end = end_cents

        bracket_start = max(start_cents, floor_cents)
        if bracket_end > bracket_start:
            taxable_chunk = bracket_end - bracket_start
            tax_cents = int(round(taxable_chunk * bracket.rate))
            total_tax_cents += tax_cents

    return total_tax_cents


def compute_april_settlement_cents(
    tax_state: YearTaxAccumulator,
    config: TaxConfigModel,
    inflation_index: float = 1.0,
) -> int:
    # Resolve standard deduction based on filing status
    if config.standard_deduction is not None:
        standard_deduction_dollars = config.standard_deduction
    elif config.filing_status == "married_joint":
        standard_deduction_dollars = 30000.0
    elif config.filing_status == "head_of_household":
        standard_deduction_dollars = 22500.0
    else:
        standard_deduction_dollars = 15000.0

    standard_deduction_cents = int(round(standard_deduction_dollars * 100.0))

    # Resolve SALT deduction cap based on configuration or filing status
    if config.salt_cap is not None:
        salt_cap_cents = int(round(config.salt_cap * 100.0))
    elif config.filing_status == "married_separate":
        salt_cap_cents = 500_000
    else:
        salt_cap_cents = 1_000_000

    allowable_salt_cents = min(salt_cap_cents, tax_state.ytd_property_tax_cents)
    itemized_deductions_cents = tax_state.ytd_mortgage_interest_cents + allowable_salt_cents
    deductions_cents = (
        max(standard_deduction_cents, itemized_deductions_cents)
        + tax_state.ytd_traditional_ira_deductible_cents
    )

    ordinary_gross_cents = tax_state.ytd_taxable_ordinary_cents + tax_state.ytd_taxable_interest_cents
    taxable_ordinary_cents = max(0, ordinary_gross_cents - deductions_cents)

    fed_ordinary_tax_cents = compute_progressive_tax_cents(taxable_ordinary_cents, config.federal_brackets)
    total_ltcg_cents = tax_state.ytd_realized_cap_gains_cents + tax_state.ytd_qualified_dividends_cents
    fed_ltcg_tax_cents = compute_ltcg_tax_cents(taxable_ordinary_cents, total_ltcg_cents, config.ltcg_brackets)
    total_fed_tax_cents = fed_ordinary_tax_cents + fed_ltcg_tax_cents

    combined_state_taxable = taxable_ordinary_cents + total_ltcg_cents
    if config.state_brackets:
        total_state_tax_cents = compute_progressive_tax_cents(combined_state_taxable, config.state_brackets)
    else:
        total_state_tax_cents = int(round(combined_state_taxable * config.state_flat_rate))

    total_tax_liability_cents = total_fed_tax_cents + total_state_tax_cents
    total_withheld_cents = tax_state.ytd_fed_withheld_cents + tax_state.ytd_state_withheld_cents
    return total_tax_liability_cents - total_withheld_cents
