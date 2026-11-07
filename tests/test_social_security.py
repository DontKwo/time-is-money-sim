import pytest
from lifesim.social_security import (
    calculate_pia_cents,
    calculate_claiming_multiplier,
    calculate_taxable_benefits_cents,
)

def test_calculate_pia_cents() -> None:
    # AIME below first bend point
    assert calculate_pia_cents(1000_00) == 900_00

    # AIME between bend points
    assert calculate_pia_cents(2000_00, 1174_00, 7078_00) == 132092

    # AIME above second bend point
    assert calculate_pia_cents(10000_00, 1174_00, 7078_00) == 338418

def test_calculate_claiming_multiplier() -> None:
    # FRA
    assert calculate_claiming_multiplier(67.0) == 1.0

    # Delay past FRA (8% per year)
    assert calculate_claiming_multiplier(70.0) == 1.24

    # Claim past 70 (capped at 70)
    assert calculate_claiming_multiplier(72.0) == 1.24

    # 1 year early (66) -> 6.666% reduction
    assert calculate_claiming_multiplier(66.0, 67.0) == pytest.approx(0.9333333333333333)

    # 3 years early (64) -> 20% reduction
    assert calculate_claiming_multiplier(64.0, 67.0) == pytest.approx(0.8)

    # 5 years early (62) -> 30% reduction
    assert calculate_claiming_multiplier(62.0, 67.0) == pytest.approx(0.7)

def test_calculate_taxable_benefits_cents() -> None:
    # Single, no tax
    assert calculate_taxable_benefits_cents(10000_00, 10000_00, "single") == 0

    # Single, 50% bracket
    assert calculate_taxable_benefits_cents(10000_00, 25000_00, "single") == 2500_00

    # Single, 85% bracket
    assert calculate_taxable_benefits_cents(10000_00, 40000_00, "single") == 8500_00

    # Married joint, 50% bracket
    assert calculate_taxable_benefits_cents(10000_00, 35000_00, "married_joint") == 4000_00
