def calculate_pia_cents(aime_cents: int, bend_point1_cents: int = 1174_00, bend_point2_cents: int = 7078_00) -> int:
    # 90% of first bend point, 32% between, 15% above
    if aime_cents <= bend_point1_cents:
        return int(round(0.90 * aime_cents))
    elif aime_cents <= bend_point2_cents:
        part1 = 0.90 * bend_point1_cents
        part2 = 0.32 * (aime_cents - bend_point1_cents)
        return int(round(part1 + part2))
    else:
        part1 = 0.90 * bend_point1_cents
        part2 = 0.32 * (bend_point2_cents - bend_point1_cents)
        part3 = 0.15 * (aime_cents - bend_point2_cents)
        return int(round(part1 + part2 + part3))

def calculate_claiming_multiplier(claiming_age: float, fra: float = 67.0) -> float:
    # Reduced if claiming early, increased if delayed up to age 70
    if claiming_age == fra:
        return 1.0
    elif claiming_age < fra:
        months_early = (fra - claiming_age) * 12
        if months_early <= 36:
            return 1.0 - (months_early * (5.0 / 9.0 / 100.0))
        else:
            return 1.0 - (36.0 * (5.0 / 9.0 / 100.0)) - ((months_early - 36.0) * (5.0 / 12.0 / 100.0))
    else:
        years_delayed = min(claiming_age, 70.0) - fra
        if years_delayed > 0:
            return 1.0 + (years_delayed * 0.08)
        return 1.0

def calculate_taxable_benefits_cents(
    ss_benefits_cents: int,
    other_income_cents: int,
    filing_status: str = "single",
) -> int:
    # Provisional income determines 0%, 50%, or 85% taxable portion
    provisional_income_cents = other_income_cents + int(round(0.5 * ss_benefits_cents))

    if filing_status == "married_joint":
        base1_cents, base2_cents = 32000_00, 44000_00
    else:
        base1_cents, base2_cents = 25000_00, 34000_00

    if provisional_income_cents <= base1_cents:
        return 0
    elif provisional_income_cents <= base2_cents:
        return min(
            int(round(0.5 * ss_benefits_cents)),
            int(round(0.5 * (provisional_income_cents - base1_cents)))
        )
    else:
        part1 = int(round(0.85 * (provisional_income_cents - base2_cents)))
        part2 = min(
            int(round(0.5 * ss_benefits_cents)),
            int(round(0.5 * (base2_cents - base1_cents)))
        )
        return min(
            int(round(0.85 * ss_benefits_cents)),
            part1 + part2
        )
