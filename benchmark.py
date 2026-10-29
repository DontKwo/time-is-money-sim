import time
from lifesim.config import ScenarioModel, FlowModel, AccountModel, ScheduleModel, AmountModel
from lifesim.engine import run
import datetime

def make_scenario():
    accounts = {
        'checking': AccountModel(balance=1000.0)
    }
    flows = [
        FlowModel(name=f'flow_{i}', type='expense', amount=AmountModel(type='exact', value=1.0), schedule=ScheduleModel(type='daily')) for i in range(1000)
    ]
    return ScenarioModel(
        start=datetime.date(2023, 1, 1),
        days=1000,
        accounts=accounts,
        flows=flows
    )

def main():
    scenario = make_scenario()

    # Warmup
    run(scenario)

    start = time.time()
    for _ in range(5):
        run(scenario)
    end = time.time()

    print(f"Time taken: {end - start:.4f} seconds")

if __name__ == '__main__':
    main()
