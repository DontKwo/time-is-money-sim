def calc_idr_monthly_payment(
    annual_income_cents: int,
    poverty_line_cents: int,
    discretionary_pct: float = 0.10,
) -> int:
    """Calculates Income-Driven Repayment monthly payment."""
    threshold_cents = int(poverty_line_cents * 2.25)
    discretionary_cents = max(0, annual_income_cents - threshold_cents)
    payment_cents = round(discretionary_cents * discretionary_pct / 12.0)
    return int(payment_cents)
