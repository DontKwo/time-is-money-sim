class MortgageSchedule:
    @staticmethod
    def calc_monthly_payment(principal_cents: int, annual_rate: float, term_months: int) -> int:
        """Calculates the monthly mortgage payment."""
        if annual_rate == 0.0:
            return int(round(principal_cents / term_months))

        monthly_rate = annual_rate / 12.0
        # Formula: P * [r * (1 + r)^n] / [(1 + r)^n - 1]
        compound_factor = (1.0 + monthly_rate) ** term_months
        payment = principal_cents * (monthly_rate * compound_factor) / (compound_factor - 1.0)
        return int(round(payment))

    @staticmethod
    def amortize_payment(balance_cents: int, monthly_payment_cents: int, annual_rate: float) -> tuple[int, int, int]:
        """Calculates principal/interest. Returns (principal_paid, interest_paid, new_balance)."""
        monthly_rate = annual_rate / 12.0
        interest_paid = int(round(balance_cents * monthly_rate))

        # Total payment cannot exceed balance plus interest
        actual_payment = min(monthly_payment_cents, balance_cents + interest_paid)

        principal_paid = actual_payment - interest_paid
        new_balance = balance_cents - principal_paid

        return principal_paid, interest_paid, new_balance
