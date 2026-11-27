from optimization.PairOptimizatorOptuna import PairOptimizatorOptuna
from optimization.pair_groups.pmain_groups import pair_group
from testing.test_constants import MAIN_FEE, DAYS_MODE

# Список пар для оптимизации: (Тикер1, Тикер2, словарь_множителей_лотов)
pairs = [
    ('TATN', 'TATNP', {'TATN': 1, 'TATNP': 1}),
    ('SBER', 'SBERP', {'SBER': 1, 'SBERP': 1}),
    ('RTKM', 'RTKMP', {'RTKM': 1, 'RTKMP': 1}),
]

test_folder = r'_data_for_tests\data_stock_5m'
n_trials = 150
bottom_limit = 20
top_limit = 1000
metric = 'total_wfee'  # Доступны также: 'eq_day', 'eq_day_per_pos', 'curve_composite', 'curve_lex'

if __name__ == '__main__':
    optimizer = PairOptimizatorOptuna(
        test_folder=test_folder,
        pairs=pairs,
        fee=MAIN_FEE,
        bottom_limit=bottom_limit,
        top_limit=top_limit,
        n_trials=n_trials,
        need_plot=True,
        window_size=201,       # Должно быть больше максимального window в pair_group (240)
        use_window_test=False, # Быстрый режим для поиска параметров
        metric=metric,
        days_mode=DAYS_MODE,
    )

    for strategy_config in pair_group:
        optimizer.optimize_pair_strategy(strategy_config)
