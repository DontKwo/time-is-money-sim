import pytest
from lifesim.real_estate import MortgageSchedule


def test_calc_monthly_payment() -> None:
    # 30-year fixed $300k at 5%
    payment = MortgageSchedule.calc_monthly_payment(300_000_00, 0.05, 360)
    # Payment should be around $1610.46
    assert payment == 1610_46

    # 15-year fixed $200k at 3%
    payment_15yr = MortgageSchedule.calc_monthly_payment(200_000_00, 0.03, 180)
    assert payment_15yr == 1381_16

    # 0% interest case
    payment_0_interest = MortgageSchedule.calc_monthly_payment(360_000_00, 0.0, 360)
    assert payment_0_interest == 1000_00


def test_amortize_payment() -> None:
    # First payment of $300k at 5%
    # Interest should be 300k * (0.05 / 12) = 1250_00
    principal, interest, new_balance = MortgageSchedule.amortize_payment(
        300_000_00, 1610_46, 0.05
    )
    assert interest == 1250_00
    assert principal == 360_46
    assert new_balance == 299_639_54

    # Last payment where balance + interest < monthly payment
    # Total required = 1004_17
    principal_final, interest_final, new_balance_final = MortgageSchedule.amortize_payment(
        1000_00, 1610_46, 0.05
    )
    assert interest_final == 4_17
    assert principal_final == 1000_00
    assert new_balance_final == 0
