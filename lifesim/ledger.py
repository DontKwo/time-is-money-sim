from datetime import date
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd


class Ledger:
    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.daily_records: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
        self.goal_results: List[Dict[str, Any]] = []

    def append(
        self,
        tx_date: date,
        flow_name: str,
        amount: int,
        account: str,
        balance: int,
        category: str = "uncategorized",
        tx_kind: str = "flow",
    ) -> None:
        self.records.append({
            "date": tx_date,
            "flow": flow_name,
            "amount": amount / 100.0,
            "account": account,
            "balance": balance / 100.0,
            "category": category,
            "tx_kind": tx_kind,
        })

    def to_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    def daily_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.daily_records)

    def export_jsonl(
        self,
        filepath: str,
        daily_filepath: Optional[str] = None,
        include_daily_events: bool = False,
    ) -> None:
        target_path = Path(filepath)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with target_path.open("w", encoding="utf-8") as file_handle:
            for record in self.records:
                tx_payload = {
                    "date": record["date"].isoformat() if hasattr(record["date"], "isoformat") else str(record["date"]),
                    "flow": record["flow"],
                    "amount": float(record["amount"]),
                    "account": record["account"],
                    "balance": float(record["balance"]),
                    "category": record.get("category", "uncategorized"),
                    "tx_kind": record.get("tx_kind", "flow"),
                }
                if include_daily_events:
                    tx_payload["event_type"] = "transaction"
                file_handle.write(json.dumps(tx_payload) + "\n")

            if include_daily_events:
                for daily_record in self.daily_records:
                    balance_date = daily_record["date"]
                    formatted_date = balance_date.isoformat() if hasattr(balance_date, "isoformat") else str(balance_date)
                    daily_payload = {
                        "event_type": "daily_balance",
                        "date": formatted_date,
                        "balances": {
                            key: float(value)
                            for key, value in daily_record.items()
                            if key != "date" and value is not None
                        },
                    }
                    file_handle.write(json.dumps(daily_payload) + "\n")

        if daily_filepath is not None:
            daily_target_path = Path(daily_filepath)
            daily_target_path.parent.mkdir(parents=True, exist_ok=True)
            with daily_target_path.open("w", encoding="utf-8") as daily_file_handle:
                for daily_record in self.daily_records:
                    balance_date = daily_record["date"]
                    formatted_date = balance_date.isoformat() if hasattr(balance_date, "isoformat") else str(balance_date)
                    daily_payload = {
                        "date": formatted_date,
                        **{
                            key: float(value)
                            for key, value in daily_record.items()
                            if key != "date" and value is not None
                        },
                    }
                    daily_file_handle.write(json.dumps(daily_payload) + "\n")
