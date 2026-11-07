from lifesim.debt import calc_idr_monthly_payment

def test_idr_below_threshold() -> None:
    # Income below 2.25 * poverty line
    annual_income = 20_000_00
    poverty_line = 10_000_00
    payment = calc_idr_monthly_payment(annual_income, poverty_line)
    assert payment == 0

def test_idr_above_threshold() -> None:
    # discretionary = 27,500.00
    # payment = 27,500.00 * 0.10 / 12 = 229.166... = 22917 cents
    annual_income = 50_000_00
    poverty_line = 10_000_00
    payment = calc_idr_monthly_payment(annual_income, poverty_line)
    assert payment == 22917

def test_idr_custom_pct() -> None:
    # 27,500.00 * 0.15 / 12 = 343.75 = 34375 cents
    annual_income = 50_000_00
    poverty_line = 10_000_00
    payment = calc_idr_monthly_payment(annual_income, poverty_line, 0.15)
    assert payment == 34375
