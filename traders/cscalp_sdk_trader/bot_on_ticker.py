from strategies.BaseTE import BaseTE
from strategies.helpTEs.helpTE import TestTE, CloseAllTE, InspectorTE
from strategies.all_tes import *

# Формат записи:
# 'TICKER': (StrategyClass, params_tuple, mode)
bot_on_ticker = {
    'LiteInvest:stockLI': {
        'APTK': (InspectorTE, tuple(), None),
        'SBER': (InspectorTE, tuple(), None),
        # # 08.11.26 ?21% +5 s -5.3 -4.7 +0.1
        # 'AFLT': (UTE6_SURVIVALIST, (None, None, 49, 9, 2.7, 1, 3.8, 5, 23, 0), None),
        # # 15.11.26 ?38% +5.4 -2.1 +16.4
        # 'ALRS': (PTE17_ALDERA, (None, None, 11, 10, 23, 61, 0, 70, 44, 23), None),
        # # 08.11.26 ?34% пд +15.5 y +3.1 +0.4 -1.2
        # 'ASTR': (PTE11_RAYMIYAMOTO, (None, None, 63, 29, 0.5, 4.4, 70, 36, 'rsi', 'velcro', 5, 70, 36, 82, 6, 15, 44, 27, 0, 0), None),
        # # 15.11.26 ?25% +2.4 -4.3 +0.9
        # 'MTLR': (PTE4_U4, (None, 41, 56, 65, 68, 70, 'VC', 'real_diff_pedals', 3, 0.08), None),
    },
    # Второй счет (бывшие AFLT2, ALRS2 и т.д.):
    'LiteInvest:stockLI_2': {
        # 15.11.26 ?18% +6.4 -6 -0.5
        'AFLT': (PTE11_RAYMIYAMOTO, (None, 28, 43, 31, 3.6, 3.9, 21, 35, 'real_wpedal', 'real_pedal', 6, 70, 66, 87, 9, 46, 37, 5, 0, 12), None),
    },
}


def init_trader(slot: str, ticker: str):
    slot_cfg = bot_on_ticker.get(slot, {})
    if ticker in slot_cfg:
        return slot_cfg[ticker]
    return (BaseTE, tuple(), None)
