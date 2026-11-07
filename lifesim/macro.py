import math
from datetime import date
from typing import Optional
import numpy as np
from pydantic import BaseModel


class InflationModel(BaseModel):
    rate: float = 0.0
    volatility: float = 0.0
    index_irs_limits: bool = True


class MacroState:
    def __init__(self, model: InflationModel, sim_start: date, rng: Optional[np.random.Generator] = None, exchange_rates: Optional[dict[str, float]] = None) -> None:
        self.model = model
        self.sim_start = sim_start
        self.macro_rng = rng if rng is not None else np.random.default_rng(42)
        self.inflation_index: float = 1.0
        self.active_annual_rate: float = model.rate
        self.current_year: int = sim_start.year
        self.exchange_rates: dict[str, float] = exchange_rates if exchange_rates is not None else {}

    def advance_day(self, current_date: date) -> None:
        if current_date > self.sim_start and current_date.month == 1 and current_date.day == 1:
            if current_date.year != self.current_year:
                self.current_year = current_date.year
                if self.model.volatility > 0.0:
                    drawn_rate = float(self.macro_rng.normal(self.model.rate, self.model.volatility))
                    self.active_annual_rate = max(-0.10, drawn_rate)

        if self.active_annual_rate != 0.0:
            daily_factor = (1.0 + self.active_annual_rate) ** (1.0 / 365.25)
            self.inflation_index *= daily_factor

    def get_indexed_limit(self, base_limit: float, round_increment: float = 500.0) -> float:
        if not self.model.index_irs_limits or self.model.rate <= 0.0:
            return base_limit
        scaled_limit = base_limit * self.inflation_index
        return round(scaled_limit / round_increment) * round_increment


def convert_currency(amount_cents: int, from_currency: str, to_currency: str, rate: float) -> int:
    if from_currency == to_currency:
        return amount_cents
    return int(round(amount_cents * rate))
