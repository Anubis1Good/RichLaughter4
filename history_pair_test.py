close_on_time = False

from testing.PairTETrader import PairTETrader
from strategies.PAIRTEs.PUTE1 import UTEP1_SPARTACUS, UTEP2_PROMETHEUS
from strategies.PAIRTEs.PLTE1 import LTEP1_SINGULARITY

dfs = {
    'TATN': '_data_for_tests\_temp\TATN_5_1794677288.parquet',
    'TATNP': '_data_for_tests\_temp\TATNP_5_1794677317.parquet',
}
# ws = (LTEP1_SINGULARITY, ('TATNP', 590, 640, 5, 720, 550, False, True, False, True))

# pt = PairTETrader(dfs, ws, quantity={'TATN': 1, 'TATNP': 1}, fee=0.0002, use_tqdm=True,close_on_time=close_on_time)
# pt.check_strategy_faster()
# pt.print_statistics()
# pt.plot_chart_and_equity()



# 1. Тест UTEP1_SPARTACUS
ws_spartacus = (
    UTEP1_SPARTACUS,
    ('TATNP', 0.2, 0.05, 145, None, 'close', False, 0, 18, 24)
)
pt1 = PairTETrader(dfs, ws_spartacus, quantity={'TATN': 1, 'TATNP': 1}, fee=0.0002, use_tqdm=True,close_on_time=close_on_time)
pt1.check_strategy_faster()
pt1.print_statistics()
pt1.plot_chart_and_equity()

pt1 = PairTETrader(dfs, ws_spartacus, quantity={'TATN': 1, 'TATNP': 1}, fee=0.0002, use_tqdm=True, window=150)
pt1.check_strategy_window()
pt1.print_statistics()
pt1.plot_chart_and_equity()

# # 2. Тест UTEP2_PROMETHEUS
# ws_prometheus = (
#     UTEP2_PROMETHEUS,
#     ('TATNP', (0.05, 0.1, 0.2), 0.01, 145, None, 'close', False, 0, 18, 24, False)
# )
# pt2 = PairTETrader(dfs, ws_prometheus, quantity={'TATN': 1, 'TATNP': 1}, fee=0.0002, use_tqdm=True,close_on_time=close_on_time)
# pt2.check_strategy_faster()
# pt2.print_statistics()
# pt2.plot_chart_and_equity()
