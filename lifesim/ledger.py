import pandas as pd
from datetime import date

class Ledger:
    def __init__(self):
        self.records = []

    def append(self, tx_date: date, flow_name: str, amount: int, account: str, balance: int):
        self.records.append({
            'date': tx_date,
            'flow': flow_name,
            'amount': amount / 100.0,
            'account': account,
            'balance': balance / 100.0
        })

    def to_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)
