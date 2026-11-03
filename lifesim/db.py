import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from .ledger import Ledger


def export_ledger_to_sqlite(ledger: Ledger, db_path: str) -> None:
    # Ensure destination directory exists before connecting.
    target_path = Path(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(target_path))
    cursor = connection.cursor()

    # Create transactions table and indexes.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            date TEXT,
            flow TEXT,
            amount REAL,
            account TEXT,
            balance REAL,
            category TEXT,
            tx_kind TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)")

    # Prepare and insert transactions records.
    tx_rows: List[tuple] = []
    for record in ledger.records:
        tx_rows.append((
            str(record["date"]),
            str(record["flow"]),
            float(record["amount"]),
            str(record["account"]),
            float(record["balance"]),
            str(record.get("category", "uncategorized")),
            str(record.get("tx_kind", "flow")),
        ))

    if tx_rows:
        cursor.executemany(
            "INSERT INTO transactions (date, flow, amount, account, balance, category, tx_kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            tx_rows,
        )

    # Determine dynamic account columns for daily_records table.
    fixed_fields = [
        "date",
        "total_net_worth",
        "liquid_net_worth",
        "vested_net_worth",
        "total_assets",
        "total_debt",
    ]
    account_names: List[str] = []
    for daily_entry in ledger.daily_records:
        for entry_key in daily_entry.keys():
            if entry_key not in fixed_fields and entry_key not in account_names:
                account_names.append(entry_key)

    daily_column_defs = [
        "date TEXT",
        "total_net_worth REAL",
        "liquid_net_worth REAL",
        "vested_net_worth REAL",
        "total_assets REAL",
        "total_debt REAL",
    ]
    for account_name in account_names:
        daily_column_defs.append(f'"{account_name}" REAL')

    daily_table_sql = f"CREATE TABLE IF NOT EXISTS daily_records ({', '.join(daily_column_defs)})"
    cursor.execute(daily_table_sql)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_records_date ON daily_records(date)")

    # Insert daily records with dynamic account balance values.
    all_daily_columns = fixed_fields + account_names
    quoted_columns = [f'"{column_name}"' for column_name in all_daily_columns]
    placeholders = ", ".join(["?"] * len(all_daily_columns))
    insert_daily_sql = f"INSERT INTO daily_records ({', '.join(quoted_columns)}) VALUES ({placeholders})"

    daily_rows: List[tuple] = []
    for daily_entry in ledger.daily_records:
        row_values: List[Any] = []
        for column_name in all_daily_columns:
            column_value = daily_entry.get(column_name)
            if column_name == "date" and column_value is not None:
                row_values.append(str(column_value))
            elif column_value is not None:
                row_values.append(float(column_value))
            else:
                row_values.append(None)
        daily_rows.append(tuple(row_values))

    if daily_rows:
        cursor.executemany(insert_daily_sql, daily_rows)

    connection.commit()
    connection.close()
