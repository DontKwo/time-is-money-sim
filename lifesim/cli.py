import argparse
from pathlib import Path
from lifesim.config import load_scenario
from lifesim.engine import run
from lifesim.plots import plot_balances

def main():
    parser = argparse.ArgumentParser(description='Life Money Simulator')
    parser.add_argument('scenario', type=str, help='Path to scenario YAML file')
    parser.add_argument('--out-ledger', type=str, default='ledger.csv', help='Output ledger CSV path')
    parser.add_argument('--out-plot', type=str, default='balances.png', help='Output plot PNG path')

    args = parser.parse_args()

    # Load and run
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        print(f"Error: Scenario file {args.scenario} not found.")
        return

    print(f"Loading scenario from {args.scenario}...")
    scenario = load_scenario(args.scenario)

    print(f"Running simulation for {scenario.days} days...")
    ledger = run(scenario)
    df = ledger.to_df()

    print(f"Exporting ledger to {args.out_ledger}...")
    df.to_csv(args.out_ledger, index=False)

    print(f"Generating plot to {args.out_plot}...")
    plot_balances(df, args.out_plot)

    print("Done!")

if __name__ == '__main__':
    main()
