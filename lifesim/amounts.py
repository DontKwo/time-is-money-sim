from .config import AmountModel

def get_amount(amount: AmountModel) -> int:
    if amount.fixed is not None:
        return int(round(amount.fixed * 100))
    return 0
