import matplotlib.pyplot as plt
import pandas as pd

def plot_balances(df: pd.DataFrame, filename: str):
    if df.empty:
        return

    plt.figure(figsize=(10, 6))

    for account, data in df.groupby('account'):
        plt.step(data['date'], data['balance'], where='post', label=account)

    plt.xlabel('Date')
    plt.ylabel('Balance ($)')
    plt.title('Account Balances')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    plt.savefig(filename)
    plt.close()
