from strategies.PAIRTEs.PUTE1 import UTEP1_SPARTACUS, UTEP2_PROMETHEUS
from strategies.PAIRTEs.PLTE1 import LTEP1_SINGULARITY

# Формат: (КлассСтратегии, [диапазоны_параметров_после_symbol2])
pair_group = (
    (
        UTEP1_SPARTACUS,
        [
            (0.05, 0.5, 0.05),        # min_desc: порог расхождения для входа (%)
            (0.0, 0.15, 0.01),        # buff_0: порог закрытия к нулю (%)
            (30, 200, 15),            # window: окно расчёта спреда
            [None, 5, 10, 20],        # smooth: сглаживание
            ['close', 'middle'],      # kind: тип цены
            [False, True],            # reverse_pos: переворот без закрытия в 0,                      # funding: 0 (без переноса),                     # hour_fund,                     # minute_fund
        ]
    ),
    (
        UTEP2_PROMETHEUS,
        [
            [(0.08, 0.16, 0.25), (0.1, 0.2, 0.35), (0.15, 0.3, 0.5)],  # desc_lvls: сетка уровней
            (0.0, 0.05, 0.01),        # buff_0
            (30, 200, 15),            # window
            [None, 5, 10],            # smooth
            ['close', 'middle'],      # kind
            [False, True],            # reverse_pos,                      # funding,                     # hour_fund,                     # minute_fund
            [False, True],            # keep_pos
        ]
    ),
    (
        LTEP1_SINGULARITY,
        [
            ('*low_price',),          # start: нижняя граница сетки
            ('*high_price',),         # end: верхняя граница сетки
            (3, 10, 1),               # amount_lvl: количество уровней сетки
            ('*overbuf_price',),      # uh_lvl: верхний уровень хеджа
            ('*subbuf_price',),       # dh_lvl: нижний уровень хеджа
            [False, True],            # first_long
            [True, False],            # keep_hedge
            [False, True],            # keep_pos
            [True, False],            # last_point
        ]
    ),

)
