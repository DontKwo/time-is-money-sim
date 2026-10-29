import numpy as np
from .config import AmountModel

def get_amount(amount: AmountModel, rng: np.random.Generator = None) -> int:
    if rng is None:
        rng = np.random.default_rng()

    if amount.fixed is not None:
        val = amount.fixed
    elif amount.normal is not None and len(amount.normal) == 2:
        val = rng.normal(amount.normal[0], amount.normal[1])
    elif amount.uniform is not None and len(amount.uniform) == 2:
        val = rng.uniform(amount.uniform[0], amount.uniform[1])
    elif amount.lognormal is not None and len(amount.lognormal) == 2:
        val = rng.lognormal(amount.lognormal[0], amount.lognormal[1])
    elif amount.gas_estimate is not None:
        if amount.gas_estimate.mpg <= 0:
            gallons = 0
        else:
            gallons = amount.gas_estimate.miles_per_period / amount.gas_estimate.mpg
        val = gallons * amount.gas_estimate.cost_per_gallon
    elif amount.grocery_estimate is not None:
        val = amount.grocery_estimate.people * amount.grocery_estimate.cost_per_person_per_period
    else:
        val = 0.0

    return max(0, int(round(val * 100)))
