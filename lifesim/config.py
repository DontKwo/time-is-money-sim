import os
import logging
import datetime as dt
from datetime import date, timedelta
from typing import Optional, Dict, List, Any, Union, Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RateStepModel(BaseModel):
    start: date
    end: Optional[date] = None
    rate: float
    volatility: Optional[float] = None


class CardAutopaySpec(BaseModel):
    enabled: bool = True
    from_account: str = "checking"
    mode: Literal["statement_balance", "minimum_due", "full_balance", "fixed"] = "statement_balance"
    fixed_amount: float = 0.0


class AccountModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: Literal[
        "checking", "savings", "hysa", "cd",
        "investment", "traditional_401k", "roth_401k",
        "traditional_ira", "roth_ira", "hsa", "529",
        "credit_card", "loan", "mortgage", "student_loan", "auto_loan"
    ] = "checking"
    balance: float = 0.0
    principal: Optional[float] = None
    initial_cost_basis: Optional[float] = None
    # Checking & overdraft
    overdraft_limit: Optional[float] = None
    overdraft_fee: Optional[float] = 0.0
    max_overdraft_fees_per_day: int = 3
    min_balance_for_fee_waiver: float = 0.0
    monthly_maintenance_fee: float = 0.0
    # Savings / HYSA / CD / Investment return rates
    annual_growth_rate: float = 0.0
    apy: Optional[float] = None
    expected_return: Optional[float] = None
    volatility: float = 0.0
    expense_ratio: float = 0.0
    dividend_yield: float = 0.0
    dividend_schedule: Literal["monthly", "quarterly"] = "quarterly"
    drip: bool = True
    dividend_to_account: Optional[str] = None
    return_includes_dividends: bool = True
    interest_posting: Literal["daily", "monthly"] = "daily"
    rate_steps: List[RateStepModel] = Field(default_factory=list)
    cd_maturity_date: Optional[date] = None
    cd_penalty_days_interest: int = 90
    annual_contribution_limit: Optional[float] = None
    # Credit card fields
    apr: float = 0.0
    promo_apr: Optional[float] = None
    promo_end: Optional[date] = None
    credit_limit: Optional[float] = None
    statement_day: int = 25
    due_day: int = 20
    min_payment_pct: float = 0.02
    min_payment_floor: float = 25.0
    late_fee: float = 35.0
    annual_fee: float = 0.0
    annual_fee_month: int = 1
    cashback_pct: float = 0.0
    category_cashback: Dict[str, float] = Field(default_factory=dict)
    rewards_to_account: Optional[str] = None
    autopay: Optional[CardAutopaySpec] = None
    # Loan & mortgage fields
    term_months: Optional[int] = None
    monthly_payment: Optional[float] = None
    payment_day: int = 1
    payment_from_account: Optional[str] = None
    payment_start: Optional[date] = None
    payment_end: Optional[date] = None
    extra_monthly_principal: float = 0.0
    # Physical asset & mortgage escrow fields
    asset_value: float = 0.0
    asset_appreciation_rate: float = 0.0
    property_tax_annual_pct: float = 0.0
    home_insurance_annual: float = 0.0
    pmi_annual_pct: float = 0.0
    pmi_drop_ltv: float = 0.78


class GasEstimate(BaseModel):
    mpg: float
    cost_per_gallon: float
    miles_per_period: float


class GroceryEstimate(BaseModel):
    people: int
    cost_per_person_per_period: float


class HourlyPayEstimate(BaseModel):
    hourly_rate: float
    hours_per_period: Union[float, List[float]]  # fixed float or [mean, sd]
    overtime_threshold: float = 40.0
    overtime_multiplier: float = 1.5


class PercentOfFlowSpec(BaseModel):
    flow: str
    pct: float  # e.g. 0.10 for 10%


class PercentOfAccountSpec(BaseModel):
    account: str
    pct: float  # e.g. 0.04 for 4% annual withdrawal
    divisor: float = 1.0  # set 12.0 for monthly 1/12th of 4%


class SeasonalitySpec(BaseModel):
    monthly: Optional[Dict[int, float]] = None  # {1: 1.35, 7: 1.40, ...}
    winter: float = 1.0  # Dec, Jan, Feb
    spring: float = 1.0  # Mar, Apr, May
    summer: float = 1.0  # Jun, Jul, Aug
    fall: float = 1.0    # Sep, Oct, Nov


class AmountModel(BaseModel):
    fixed: Optional[float] = None
    normal: Optional[List[float]] = None
    uniform: Optional[List[float]] = None
    lognormal: Optional[List[float]] = None          # [mu_log, sigma_log]
    lognormal_dollars: Optional[List[float]] = None  # [median_dollars, sigma_log]
    triangular: Optional[List[float]] = None         # [low, mode, high]
    choice: Optional[List[List[float]]] = None       # [[amount, weight], ...]
    gas_estimate: Optional[GasEstimate] = None
    grocery_estimate: Optional[GroceryEstimate] = None
    hourly_pay: Optional[HourlyPayEstimate] = None
    percent_of_flow: Optional[PercentOfFlowSpec] = None
    percent_of_account: Optional[PercentOfAccountSpec] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    round_to: Optional[float] = None  # e.g. 1.0 rounds to whole dollars


class NthWeekdaySpec(BaseModel):
    nth: int  # 1, 2, 3, 4, 5, or -1 for last occurrence in month
    weekday: str  # mon..sun
    months: Optional[List[int]] = None  # 1..12; None means every month


class EveryNWeeksSpec(BaseModel):
    n: int  # >= 1
    weekdays: List[str]  # e.g. ["mon", "thu"]
    anchor: Optional[date] = None


class EveryNMonthsSpec(BaseModel):
    n: int  # >= 1
    day: Union[int, str] = 1  # 1..31, -1, or "last"
    anchor_year: Optional[int] = None
    anchor_month: Optional[int] = None


class QuarterlySpec(BaseModel):
    day: Union[int, str] = 1
    months: List[int] = Field(default_factory=lambda: [1, 4, 7, 10])


class YearlySpec(BaseModel):
    month: int  # 1..12
    day: Union[int, str]  # 1..31, -1, or "last"


class DateWindowSpec(BaseModel):
    start: date
    end: date


class DateRangeSpec(BaseModel):
    start: date
    end: date
    mode: Literal["daily", "spread_evenly", "first_day", "last_day"] = "daily"


class ScheduleModel(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None
    pause_windows: List[DateWindowSpec] = Field(default_factory=list)
    daily: bool = False
    every_n_days: Optional[int] = None
    biweekly: Optional[str] = None  # mon..sun
    anchor: Optional[date] = None
    weekly: Optional[Union[str, List[str]]] = None
    every_n_weeks: Optional[EveryNWeeksSpec] = None
    semimonthly: Optional[List[Union[int, str]]] = None
    monthly: Optional[Union[int, str, List[Union[int, str]]]] = None
    nth_weekday: Optional[NthWeekdaySpec] = None
    quarterly: Optional[QuarterlySpec] = None
    every_n_months: Optional[EveryNMonthsSpec] = None
    yearly: Optional[Union[Dict[str, Union[int, str]], List[Dict[str, Union[int, str]]]]] = None
    once: Optional[Union[str, date]] = None
    dates: Optional[List[date]] = None
    date_range: Optional[DateRangeSpec] = None
    daily_prob: Optional[float] = None
    random_per_week: Optional[float] = None
    random_per_month: Optional[float] = None
    random_per_year: Optional[float] = None
    weekday_weights: Optional[Dict[str, float]] = None
    allow_multiple_per_day: bool = False
    weekdays_only: bool = False
    weekends_only: bool = False
    allowed_weekdays: Optional[List[str]] = None
    excluded_dates: Optional[List[date]] = None
    weekend_rule: Literal["ignore", "before", "after"] = "ignore"
    respect_us_holidays: bool = False


class FlowStepModel(BaseModel):
    start: date
    end: Optional[date] = None
    amount: AmountModel


class InflationModel(BaseModel):
    rate: float = 0.0
    volatility: float = 0.0
    index_irs_limits: bool = True


class SalaryStepModel(BaseModel):
    start: date
    annual_salary: float


class BonusSpec(BaseModel):
    name: str
    enabled: bool = True
    schedule: ScheduleModel
    gross_amount: Optional[AmountModel] = None
    target_pct_of_salary: Optional[float] = None
    multiplier: Optional[AmountModel] = None
    supplemental_federal_rate: float = 0.22
    apply_401k: bool = False


class MatchTier(BaseModel):
    match_rate: float
    band_pct: float


class VestingSpec(BaseModel):
    kind: Literal["immediate", "cliff", "graded"] = "immediate"
    hire_date: Optional[date] = None
    cliff_months: int = 0
    graded_schedule: Dict[int, float] = Field(default_factory=dict)


class EmployerMatchSpec(BaseModel):
    enabled: bool = True
    match_rate: float = 1.0
    up_to_pct: float = 0.0
    tiers: List[MatchTier] = Field(default_factory=list)
    employer_fixed_pct: float = 0.0
    annual_true_up: bool = False
    to_account: str = "traditional_401k"
    vesting: Optional[VestingSpec] = None


class Retirement401kSpec(BaseModel):
    enabled: bool = True
    traditional_pct: float = 0.0
    roth_pct: float = 0.0
    after_tax_roth_pct: float = 0.0
    traditional_fixed: float = 0.0
    roth_fixed: float = 0.0
    auto_escalate_pct_per_year: float = 0.0
    auto_escalate_max_pct: float = 1.0
    traditional_account: Optional[str] = "traditional_401k"
    roth_account: Optional[str] = None
    employer_match: Optional[EmployerMatchSpec] = None
    annual_employee_limit: float = 23500.0
    catch_up_limit: float = 0.0
    annual_total_limit: float = 70000.0


class HSASpec(BaseModel):
    enabled: bool = True
    to_account: str = "hsa"
    employee_per_period: float = 0.0
    employee_pct: float = 0.0
    employer_per_period: float = 0.0
    employer_annual_seed: float = 0.0
    annual_limit: float = 4300.0


class ESPPSpec(BaseModel):
    enabled: bool = False
    contribution_pct: float = 0.0
    discount_pct: float = 0.15
    purchase_months: List[int] = Field(default_factory=lambda: [6, 12])
    annual_irs_limit: float = 25000.0
    to_account: str = "brokerage"


class WithholdingSpec(BaseModel):
    mode: Literal["brackets", "effective_rate", "none"] = "brackets"
    effective_federal_rate: float = 0.0
    effective_state_rate: float = 0.0
    local_tax_rate: float = 0.0
    include_fica: bool = True


class DirectDepositSplit(BaseModel):
    to: str
    fixed: Optional[float] = None
    pct: Optional[float] = None
    remainder: bool = False


class PaycheckModel(BaseModel):
    name: str
    enabled: bool = True
    schedule: ScheduleModel
    annual_salary: Optional[float] = None
    gross_per_period: Optional[AmountModel] = None
    hourly_pay: Optional[HourlyPayEstimate] = None
    pay_periods_per_year: Optional[int] = None
    annual_raise_pct: float = 0.0
    raise_month: int = 1
    raise_day: int = 1
    salary_steps: List[SalaryStepModel] = Field(default_factory=list)
    bonuses: List[BonusSpec] = Field(default_factory=list)
    retirement_401k: Optional[Retirement401kSpec] = None
    hsa: Optional[HSASpec] = None
    pretax_deductions_per_period: float = 0.0
    posttax_deductions_per_period: float = 0.0
    espp: Optional[ESPPSpec] = None
    withholding: WithholdingSpec = Field(default_factory=WithholdingSpec)
    direct_deposit: List[DirectDepositSplit] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=lambda: ["payday", "salary"])


class RSUGrantModel(BaseModel):
    name: str
    enabled: bool = True
    schedule: ScheduleModel
    gross_vest_amount: Optional[AmountModel] = None
    shares_per_vest: Optional[float] = None
    initial_share_price: Optional[float] = None
    growth_rate: float = 0.0
    withhold_tax_rate: float = 0.30
    to_account: str = "brokerage"
    auto_sell_to_account: Optional[str] = None


class SweepAllocation(BaseModel):
    to_account: str
    weight: float
    respect_annual_limit: bool = True
    overflow_to_account: Optional[str] = None


class PolicyModel(BaseModel):
    name: str
    kind: Literal[
        "shortfall_cover", "payday_skim", "emergency_fund_target",
        "excess_sweep", "debt_payoff", "portfolio_rebalance",
        "retirement_drawdown", "sinking_fund", "roth_conversion_ladder"
    ]
    enabled: bool = True
    start: Optional[date] = None
    end: Optional[date] = None
    priority: int = 100
    schedule: Optional[ScheduleModel] = None
    to_account: Optional[str] = None
    from_account: Optional[str] = None
    from_accounts: List[str] = Field(default_factory=list)
    minimum_balance: float = 0.0
    restore_to_balance: Optional[float] = None
    trigger_tag: str = "payday"
    pct_of_inflow: Optional[float] = None
    fixed_amount: Optional[float] = None
    respect_annual_limit: bool = True
    overflow_to_account: Optional[str] = None
    keep_checking_buffer: float = 2000.0
    conversion_amount: Optional[float] = None
    seasoning_years: int = 5
    target_balance: Optional[float] = None
    target_months_expenses: Optional[float] = None
    threshold: float = 5000.0
    keep_buffer: float = 3000.0
    allocations: List[SweepAllocation] = Field(default_factory=list)
    strategy: Literal["avalanche", "snowball"] = "avalanche"
    target_accounts: List[str] = Field(default_factory=list)
    extra_payment: float = 0.0
    total_monthly_budget: Optional[float] = None
    target_weights: Dict[str, float] = Field(default_factory=dict)
    drift_band: float = 0.05
    target_checking_balance: Optional[float] = None
    fixed_withdrawal: Optional[float] = None
    swr_annual_pct: Optional[float] = None
    withdrawal_order: Optional[List[str]] = None
    pretax_gross_up_rate: float = 0.15
    target_flows: List[str] = Field(default_factory=list)
    lookahead_days: int = 365


class OneTimeChargeSpec(BaseModel):
    name: Optional[str] = None
    type: Literal["income", "expense", "transfer"] = "expense"
    amount: AmountModel
    from_account: Optional[str] = None
    to_account: Optional[str] = None
    category: str = "events"


class RefinanceSpec(BaseModel):
    loan_account: str
    new_apr: float
    new_term_months: int
    closing_cost: float = 0.0
    closing_cost_from_account: str = "checking"


class EventModel(BaseModel):
    name: str
    enabled: bool = True
    date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    enable_flows: List[str] = Field(default_factory=list)
    disable_flows: List[str] = Field(default_factory=list)
    enable_paychecks: List[str] = Field(default_factory=list)
    disable_paychecks: List[str] = Field(default_factory=list)
    terminate_job: Optional[str] = None
    set_flow_amount: Dict[str, AmountModel] = Field(default_factory=dict)
    one_time_flow: Optional[OneTimeChargeSpec] = None
    open_account: Dict[str, AccountModel] = Field(default_factory=dict)
    refinance_loan: Optional[RefinanceSpec] = None
    start: Optional[dt.date] = None
    end: Optional[dt.date] = None
    poisson_per_year: Optional[float] = None
    amount: Optional[AmountModel] = None
    type: Literal["expense", "income"] = "expense"
    account: Optional[str] = None
    category: str = "shocks"
    cooldown_days: int = 0
    insurance_deductible: Optional[float] = None
    insurance_coinsurance_pct: float = 0.20
    insurance_oop_max: Optional[float] = None


class GoalModel(BaseModel):
    name: str
    kind: Literal[
        "net_worth", "liquid_net_worth", "account_balance",
        "debt_free", "emergency_months", "coast_fire",
        "financial_independence"
    ]
    target_amount: float = 0.0
    account: Optional[str] = None
    target_date: Optional[date] = None
    swr: float = 0.04
    retirement_age_years_away: Optional[float] = None
    real_return_assumption: float = 0.05


class AutoTransferModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_account: str = Field(alias="from")
    to_account: str = Field(alias="to")
    minimum_balance: float = 0.0


class FlowModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: str  # income, expense, transfer
    schedule: ScheduleModel
    amount: AmountModel
    from_account: Optional[str] = Field(default=None, alias="from")
    to_account: Optional[str] = Field(default=None, alias="to")
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    skip_prob: Optional[float] = 0.0
    enabled: bool = True
    share_fraction: float = 1.0
    inflation_adjusted: bool = False
    annual_escalation_rate: float = 0.0
    escalation_mode: Literal["anniversary", "jan_1", "smooth_daily"] = "anniversary"
    seasonality: Optional[SeasonalitySpec] = None
    steps: List[FlowStepModel] = Field(default_factory=list)
    date_range_total: bool = False
    employer_match_multiplier: float = 0.0
    employer_match_cap_per_event: Optional[float] = None


class TaxBracket(BaseModel):
    rate: float
    threshold: float  # floor of the bracket in dollars (0.0 for first bracket)


def default_single_federal_brackets() -> List[TaxBracket]:
    return [
        TaxBracket(rate=0.10, threshold=0.0),
        TaxBracket(rate=0.12, threshold=11925.0),
        TaxBracket(rate=0.22, threshold=48475.0),
        TaxBracket(rate=0.24, threshold=103350.0),
        TaxBracket(rate=0.32, threshold=197300.0),
        TaxBracket(rate=0.35, threshold=250525.0),
        TaxBracket(rate=0.37, threshold=626350.0),
    ]


def default_single_ltcg_brackets() -> List[TaxBracket]:
    return [
        TaxBracket(rate=0.00, threshold=0.0),
        TaxBracket(rate=0.15, threshold=48350.0),
        TaxBracket(rate=0.20, threshold=533400.0),
    ]


class TaxConfigModel(BaseModel):
    enabled: bool = False
    filing_status: Literal["single", "married_joint", "married_separate", "head_of_household"] = "single"
    standard_deduction: Optional[float] = None
    salt_cap: Optional[float] = None
    federal_brackets: List[TaxBracket] = Field(default_factory=default_single_federal_brackets)
    ltcg_brackets: List[TaxBracket] = Field(default_factory=default_single_ltcg_brackets)
    state_flat_rate: float = 0.0
    state_brackets: List[TaxBracket] = Field(default_factory=list)
    ss_wage_base: float = 176100.0
    additional_medicare_threshold: float = 200000.0
    april_true_up: bool = True
    settlement_account: str = "checking"


class SocialSecurityModel(BaseModel):
    enabled: bool = False
    start_date: date
    monthly_benefit: float
    annual_cola: float = 0.025
    to_account: str = "checking"
    taxable_pct: float = 0.85


class ScenarioModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: date
    days: Optional[int] = None
    end: Optional[date] = None
    seed: Optional[int] = 42
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    accounts: Dict[str, AccountModel] = Field(default_factory=dict)
    flows: List[FlowModel] = Field(default_factory=list)
    auto_transfers: List[AutoTransferModel] = Field(default_factory=list)
    inflation: InflationModel = Field(default_factory=InflationModel)
    taxes: Optional[TaxConfigModel] = None
    social_security: Optional[SocialSecurityModel] = None
    paychecks: List[PaycheckModel] = Field(default_factory=list)
    rsu_grants: List[RSUGrantModel] = Field(default_factory=list)
    policies: List[PolicyModel] = Field(default_factory=list)
    events: List[EventModel] = Field(default_factory=list)
    goals: List[GoalModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_horizon(self) -> "ScenarioModel":
        if self.days is None and self.end is None:
            raise ValueError("At least one of 'days' or 'end' must be provided.")
        if self.days is None and self.end is not None:
            day_count = (self.end - self.start).days + 1
            if day_count < 1:
                raise ValueError(f"end date {self.end} must be on or after start date {self.start}")
            self.days = day_count
        elif self.days is not None and self.end is None:
            if self.days < 1:
                raise ValueError(f"days must be >= 1, got {self.days}")
            self.end = self.start + timedelta(days=self.days - 1)
        elif self.days is not None and self.end is not None:
            expected_days = (self.end - self.start).days + 1
            if expected_days < 1:
                raise ValueError(f"end date {self.end} must be on or after start date {self.start}")
            if self.days != expected_days:
                raise ValueError(f"days ({self.days}) does not match start-to-end span ({expected_days})")
        return self

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> "ScenarioModel":
        known_accounts: set[str] = set(self.accounts.keys())
        for event in self.events:
            if event.open_account:
                known_accounts.update(event.open_account.keys())

        def check_account_name(entity_type: str, entity_name: str, account_name: Optional[str]) -> None:
            if account_name is not None and account_name not in known_accounts:
                raise ValueError(
                    f"{entity_type} '{entity_name}' references non-existent account '{account_name}'"
                )

        def check_account_names(entity_type: str, entity_name: str, account_names: Optional[List[str]]) -> None:
            if account_names:
                for target_account in account_names:
                    check_account_name(entity_type, entity_name, target_account)

        for flow in self.flows:
            check_account_name("flow", flow.name, flow.from_account)
            check_account_name("flow", flow.name, flow.to_account)

        for transfer in self.auto_transfers:
            check_account_name("auto_transfer", f"{transfer.from_account}->{transfer.to_account}", transfer.from_account)
            check_account_name("auto_transfer", f"{transfer.from_account}->{transfer.to_account}", transfer.to_account)

        for paycheck in self.paychecks:
            for deposit in paycheck.direct_deposit:
                check_account_name("paycheck", paycheck.name, deposit.to)
            if paycheck.hsa is not None:
                check_account_name("paycheck", paycheck.name, paycheck.hsa.to_account)
            if paycheck.retirement_401k is not None:
                check_account_name("paycheck", paycheck.name, paycheck.retirement_401k.traditional_account)
                check_account_name("paycheck", paycheck.name, paycheck.retirement_401k.roth_account)
                if paycheck.retirement_401k.employer_match is not None:
                    check_account_name(
                        "paycheck",
                        paycheck.name,
                        paycheck.retirement_401k.employer_match.to_account,
                    )
            if paycheck.espp is not None:
                check_account_name("paycheck", paycheck.name, paycheck.espp.to_account)

        for rsu_grant in self.rsu_grants:
            check_account_name("rsu_grant", rsu_grant.name, rsu_grant.to_account)

        for policy in self.policies:
            check_account_name("policy", policy.name, policy.to_account)
            check_account_name("policy", policy.name, policy.from_account)
            check_account_names("policy", policy.name, policy.from_accounts)
            check_account_names("policy", policy.name, policy.target_accounts)
            for allocation in policy.allocations:
                check_account_name("policy", policy.name, allocation.to_account)
                check_account_name("policy", policy.name, allocation.overflow_to_account)
            check_account_name("policy", policy.name, policy.overflow_to_account)
            check_account_names("policy", policy.name, policy.withdrawal_order)

        if self.taxes is not None:
            check_account_name("taxes", "taxes", self.taxes.settlement_account)

        for goal in self.goals:
            if goal.kind == "account_balance":
                check_account_name("goal", goal.name, goal.account)

        return self


def apply_cli_overrides(raw_data: Dict[str, Any], overrides: List[str]) -> Dict[str, Any]:
    for override in overrides:
        key_path, val_str = override.split("=", 1)
        parsed_value = yaml.safe_load(val_str)
        tokens = key_path.split(".")
        current_node: Any = raw_data

        for token in tokens[:-1]:
            if isinstance(current_node, dict):
                if token not in current_node:
                    current_node[token] = {}
                current_node = current_node[token]
            elif isinstance(current_node, list):
                if token.isdigit():
                    current_node = current_node[int(token)]
                else:
                    found_item = None
                    for list_item in current_node:
                        if isinstance(list_item, dict) and list_item.get("name") == token:
                            found_item = list_item
                            break
                    if found_item is None:
                        raise KeyError(f"Item with name '{token}' not found in list")
                    current_node = found_item
            else:
                raise TypeError(f"Cannot traverse into node of type {type(current_node)}")

        final_token = tokens[-1]
        if isinstance(current_node, dict):
            current_node[final_token] = parsed_value
        elif isinstance(current_node, list):
            if final_token.isdigit():
                current_node[int(final_token)] = parsed_value
            else:
                raise ValueError(f"Cannot set non-numeric index on list: {final_token}")
        else:
            raise TypeError(f"Cannot set attribute on node of type {type(current_node)}")

    return raw_data


def load_scenario(path: str, overrides: Optional[List[str]] = None) -> ScenarioModel:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    includes = data.get("include", [])
    excludes = set(data.get("exclude", []))

    base_dir = os.path.dirname(os.path.abspath(path))

    # find repo root by traversing up
    current_dir = base_dir
    repo_root = base_dir
    while current_dir != os.path.dirname(current_dir):
        req_path = os.path.join(current_dir, "requirements.txt")
        git_path = os.path.join(current_dir, ".git")
        if os.path.exists(req_path) or os.path.exists(git_path):
            repo_root = current_dir
            break
        current_dir = os.path.dirname(current_dir)

    merged_accounts = {}
    merged_flows = []
    merged_paychecks = []
    merged_rsu = []
    merged_policies = []
    merged_events = []
    merged_goals = []
    merged_social_security = None

    for inc in includes:
        if os.path.isabs(inc):
            inc_path = inc
        else:
            inc_path = os.path.join(repo_root, inc)
            if not os.path.exists(inc_path):
                inc_path = os.path.join(base_dir, inc)
        with open(inc_path, "r") as f:
            inc_data = yaml.safe_load(f)

            if "accounts" in inc_data:
                merged_accounts.update(inc_data["accounts"])
            if "flows" in inc_data:
                merged_flows.extend(inc_data["flows"])
            if "paychecks" in inc_data:
                merged_paychecks.extend(inc_data["paychecks"])
            if "rsu_grants" in inc_data:
                merged_rsu.extend(inc_data["rsu_grants"])
            if "policies" in inc_data:
                merged_policies.extend(inc_data["policies"])
            if "events" in inc_data:
                merged_events.extend(inc_data["events"])
            if "goals" in inc_data:
                merged_goals.extend(inc_data["goals"])
            if "social_security" in inc_data:
                merged_social_security = inc_data["social_security"]

    if "accounts" in data:
        merged_accounts.update(data["accounts"])
    if "flows" in data:
        merged_flows.extend(data["flows"])
    if "paychecks" in data:
        merged_paychecks.extend(data["paychecks"])
    if "rsu_grants" in data:
        merged_rsu.extend(data["rsu_grants"])
    if "policies" in data:
        merged_policies.extend(data["policies"])
    if "events" in data:
        merged_events.extend(data["events"])
    if "goals" in data:
        merged_goals.extend(data["goals"])
    if "social_security" in data:
        merged_social_security = data["social_security"]

    filtered_flows = [flow for flow in merged_flows if flow["name"] not in excludes]

    seen_names = {}
    for flow in filtered_flows:
        base_name = flow["name"]
        if base_name in seen_names:
            seen_names[base_name] += 1
            new_name = f"{base_name}_{seen_names[base_name]}"
            logging.warning(f"Duplicate flow name '{base_name}' found. Renaming to '{new_name}'.")
            flow["name"] = new_name
        else:
            seen_names[base_name] = 1

    data["accounts"] = merged_accounts
    data["flows"] = filtered_flows
    data["paychecks"] = merged_paychecks
    data["rsu_grants"] = merged_rsu
    data["policies"] = merged_policies
    data["events"] = merged_events
    data["goals"] = merged_goals
    if merged_social_security is not None:
        data["social_security"] = merged_social_security

    if overrides is not None:
        data = apply_cli_overrides(data, overrides)

    return ScenarioModel(**data)
