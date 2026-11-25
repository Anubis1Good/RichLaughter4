from strategies.BaseTE import BaseTE
from for_strategies.zai_classic_indicators import add_ichimoku, add_aroon, add_donchian_width, add_elder_ray, add_vortex, add_chaikin_money_flow
from for_strategies.fix_params import fix_two_periods_hm, fix_three_periods_hm

"""
LTE4_ai — осцилляторные, адаптивные и контртрендовые стратегии на индикаторах zai_classic_indicators
(Aroon, Vortex, Chaikin Money Flow, Elder Ray, Ichimoku-облако, Donchian Width/Squeeze).

Все стратегии чисто каузальны: только строка текущего бара в _get_action_from_row, индикаторы —
конечные скользящие окна, поэтому check_strategy_faster и check_strategy_window дают одинаковый результат.
"""

# 25.11.26 наверное надо перевернуть
class LTE4_VORTEXFALL(BaseTE):
    """stop=None, take=None, period=14, cmf_period=20, threshold_enter=0.05, threshold_exit=0.02, sig_cmf=0.02, use_stop=1, max_period=70

    Импульсные развороты по Vortex с подтверждением деньгами (CMF): вход при развороте вихря за
    threshold_enter и значимом притоке/оттоке (|cmf| > sig_cmf); выход при возврате vtx_diff через
    0 на величину threshold_exit. Все пороги вместо сравнения с нулём — устойчивость к float-шуму.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=14, cmf_period=20, threshold_enter=0.05, threshold_exit=0.02, sig_cmf=0.02, use_stop=1, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.cmf_period = fix_two_periods_hm(period, cmf_period, max_period)
        self.threshold_enter = threshold_enter
        self.threshold_exit = threshold_exit
        self.sig_cmf = sig_cmf
        self.use_stop = use_stop

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_vortex(df, self.period)
        df = add_chaikin_money_flow(df, self.cmf_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        diff = row['vtx_diff']
        cmf = row['cmf_value']

        if diff > self.threshold_enter and cmf > self.sig_cmf:
            return 'open_long'
        if diff < -self.threshold_enter and cmf < -self.sig_cmf:
            return 'open_short'
        if self.use_stop:
            if diff <= -self.threshold_exit:
                return 'close_long'
            if diff >= self.threshold_exit:
                return 'close_short'
        return None

# 25.11.26 наверное надо перевернуть
class LTE4_SQUEEZEPOP(BaseTE):
    """stop=None, take=None, period=20, squeeze_period=30, aroon_period=15, recent_period=5, threshold=75, exit_threshold=50, max_period=70

    Адаптивный пробой после сжатия: если канал Дончиана был «сжат» в последние recent_period баров
    (dcw_squeeze_recent), вход в сторону пробоя — Aroon подтверждает новый экстремум
    (aroon_up >= threshold при aroon_down <= 100-threshold). Выход при затухании Aroon.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=20, squeeze_period=30, aroon_period=15, recent_period=5,
                 threshold=75.0, exit_threshold=50.0, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.squeeze_period, self.aroon_period = fix_three_periods_hm(period, squeeze_period, aroon_period, max_period)
        self.recent_period = recent_period
        self.threshold = threshold
        self.exit_threshold = exit_threshold
        # полный прогрев squeeze-цепочки: ширина канала + квантиль + окно «недавности»
        self.squeeze_full_period = self.period + self.squeeze_period + self.recent_period

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchian_width(df, self.period, self.squeeze_period)
        df = add_aroon(df, self.aroon_period)
        df['dcw_squeeze_recent'] = df['dcw_squeeze'].astype(float).rolling(self.recent_period).max()
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        was_squeezed = row['dcw_squeeze_recent'] == 1.0
        up = row['aroon_up']
        dn = row['aroon_down']

        if was_squeezed and up >= self.threshold and dn <= 100.0 - self.threshold:
            return 'open_long'
        if was_squeezed and dn >= self.threshold and up <= 100.0 - self.threshold:
            return 'open_short'
        if up <= self.exit_threshold:
            return 'close_long'
        if dn <= self.exit_threshold:
            return 'close_short'
        return None

# 25.11.26 мало сдело
class LTE4_CLOUDFADE(BaseTE):
    """stop=None, take=None, tenkan_period=8, kijun_period=16, senkou_b_period=24, displacement_period=7, threshold=0.3, threshold_turn=0.05, use_stop=1

    Контртренд к Ichimoku-облаку: цена ушла ниже/выше облака на threshold процентов, Vortex
    разворачивается обратно на threshold_turn (буфер от нуля против float-шума на границе знака) —
    вход против движения; выход при возврате цены в облако (за cloud_bottom/cloud_top).
    Senkou-линии сдвинуты вперёд (shift+displacement) — будущего нет.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 tenkan_period=8, kijun_period=16, senkou_b_period=24, displacement_period=7,
                 threshold=0.3, threshold_turn=0.05, use_stop=1):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_b_period = senkou_b_period
        self.displacement_period = displacement_period
        # полный прогрев облака: senkou_b_period + сдвиг displacement вперёд
        self.senkou_total_period = senkou_b_period + displacement_period
        self.threshold = threshold
        self.threshold_turn = threshold_turn
        self.use_stop = use_stop

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_ichimoku(df, self.tenkan_period, self.kijun_period, self.senkou_b_period, self.displacement_period)
        df = add_vortex(df, self.tenkan_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        close = row['close']
        top = row['ichi_cloud_top']
        bot = row['ichi_cloud_bottom']

        if close < bot and (bot - close) / close * 100.0 >= self.threshold and row['vtx_diff'] > self.threshold_turn:
            return 'open_long'
        if close > top and (close - top) / close * 100.0 >= self.threshold and row['vtx_diff'] < -self.threshold_turn:
            return 'open_short'
        if self.use_stop:
            if close >= bot:
                return 'close_long'
            if close <= top:
                return 'close_short'
        return None

# 25.11.26 наверное надо перевернуть
class LTE4_TRIPLEOSC(BaseTE):
    """stop=None, take=None, period=25, cmf_period=20, elder_period=13, solution=2, exit_level=75, sig_cmf=0.05, max_period=70

    Осцилляторный «счёт» из трёх независимых сигналов возврата к среднему: подавленный Aroon,
    Elder Ray (медведи/быки давят сильнее шага цены) и значимый приток/отток денег по CMF
    (|cmf| > sig_cmf). Вход при score >= solution, выход при восстановлении Aroon до exit_level.
    Пороги вместо сравнения с нулём — устойчивость к float-шуму на границе знака.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=25, cmf_period=20, elder_period=13, solution=2, exit_level=75.0, sig_cmf=0.05, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.cmf_period, self.elder_period = fix_three_periods_hm(period, cmf_period, elder_period, max_period)
        self.solution = solution
        self.exit_level = exit_level
        self.sig_cmf = sig_cmf
        # Порог силы Elder Ray — 1.5 шага цены. Значения elder_* всегда лежат на сетке
        # step/period (разности тиковых цен и их SMA), поэтому порог на полуцелом шаге
        # недостижим точно и сравнение детерминировано при любом объёме истории
        # (накопительный float-шум pandas rolling ~1e-13 не решает исход).
        self.pow_eps = (self.price_step if self.price_step is not None else 0.0) * 1.5

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_aroon(df, self.period)
        df = add_chaikin_money_flow(df, self.cmf_period)
        df = add_elder_ray(df, self.elder_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        weak_up = row['aroon_up'] < 100.0 - self.exit_level
        weak_dn = row['aroon_down'] < 100.0 - self.exit_level

        # int() обязателен: np.bool_ + np.bool_ — это логическое ИЛИ, а не сумма
        score_long = int(weak_up) + int(row['elder_bear'] > self.pow_eps) + int(row['cmf_value'] > self.sig_cmf)
        if score_long >= self.solution:
            return 'open_long'
        score_short = int(weak_dn) + int(row['elder_bull'] < -self.pow_eps) + int(row['cmf_value'] < -self.sig_cmf)
        if score_short >= self.solution:
            return 'open_short'
        if row['aroon_up'] >= self.exit_level:
            return 'close_long'
        if row['aroon_down'] >= self.exit_level:
            return 'close_short'
        return None

# 25.11.26 наверное надо перевернуть
class LTE4_FADER(BaseTE):
    """stop=None, take=None, period=25, cmf_period=20, strong_cmf=0.15, threshold_turn=0.05, neutral_cmf=0.02, max_period=70

    Лестница усреднения против экстремума (числовая целевая позиция): умеренный контртрендовый
    сигнал (|cmf| > neutral_cmf) -> 1/-1 юнит, усиление сигнала (экстремальный Aroon + сильный CMF
    + разворот Vortex за threshold_turn) -> добор до 2/-2 юнитов, нейтральная зона Aroon или
    |cmf| <= neutral_cmf -> 0 (выход). Пороги вместо сравнения с нулём — детерминированность.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=25, cmf_period=20, strong_cmf=0.15, threshold_turn=0.05, neutral_cmf=0.02, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.cmf_period = fix_two_periods_hm(period, cmf_period, max_period)
        self.strong_cmf = strong_cmf
        self.threshold_turn = threshold_turn
        self.neutral_cmf = neutral_cmf

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_aroon(df, self.period)
        df = add_chaikin_money_flow(df, self.cmf_period)
        df = add_vortex(df, self.period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        a_up = row['aroon_up']
        a_dn = row['aroon_down']
        cmf = row['cmf_value']
        vd = row['vtx_diff']

        if a_up <= 10.0 and cmf > self.strong_cmf and vd > self.threshold_turn:
            return 2
        if a_up <= 30.0 and cmf > self.neutral_cmf:
            return 1
        if a_dn <= 10.0 and cmf < -self.strong_cmf and vd < -self.threshold_turn:
            return -2
        if a_dn <= 30.0 and cmf < -self.neutral_cmf:
            return -1
        return 0

# 25.11.26 наверное надо перевернуть
class LTE4_SPREADEATER(BaseTE):
    """stop=None, take=None, period=25, cmf_period=20, trend_threshold=50, extreme_cmf=0.3, step_mult=2, max_period=70

    Маркет-мейкерские качели по шагам от стакана (spred_*_step_N): в боковике (|Aroon diff| <
    trend_threshold) работает спред обеими сторонами; в трендовом рынке качели только по тренду
    (spred_long/spred_short); при экстремальном денежном потоке (|cmf| >= extreme_cmf) — close_all.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=25, cmf_period=20, trend_threshold=50.0, extreme_cmf=0.3, step_mult=2, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.cmf_period = fix_two_periods_hm(period, cmf_period, max_period)
        self.trend_threshold = trend_threshold
        self.extreme_cmf = extreme_cmf
        self.step_mult = int(step_mult)

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_aroon(df, self.period)
        df = add_chaikin_money_flow(df, self.cmf_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        diff = row['aroon_up'] - row['aroon_down']
        cmf = row['cmf_value']

        if abs(cmf) >= self.extreme_cmf:
            return 'close_all'
        if abs(diff) < self.trend_threshold:
            return f'spred_all_step_{self.step_mult}'
        if diff >= self.trend_threshold:
            return f'spred_long_step_{self.step_mult}'
        return f'spred_short_step_{self.step_mult}'

# 25.11.26 наверное надо перевернуть
class LTE4_LEVELFADE(BaseTE):
    """stop=None, take=None, tenkan_period=9, kijun_period=20, senkou_b_period=28, displacement_period=7, squeeze_period=20, squeeze_q=0.25, use_squeeze=1

    Контртренд по динамическим уровням Ichimoku-облака: границы облака пишутся в pdata['levels']
    (и в test_top_level/test_bottom_level для быстрого теста), стратегия торгует
    'spred_all_level' — лимитные качели от нижней границы к верхней. Во время «сжатия» канала
    (dcw_squeeze) торговля отключается — уровни ненадёжны.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 tenkan_period=9, kijun_period=20, senkou_b_period=28, displacement_period=7,
                 squeeze_period=20, squeeze_q=0.25, use_squeeze=1):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_b_period = senkou_b_period
        self.displacement_period = displacement_period
        # полный прогрев облака: senkou_b_period + сдвиг displacement вперёд
        self.senkou_total_period = senkou_b_period + displacement_period
        self.squeeze_period = squeeze_period
        self.squeeze_q = squeeze_q
        self.use_squeeze = use_squeeze
        # полный прогрев squeeze-цепочки add_donchian_width: ширина + квантиль
        self.sq_full_period = squeeze_period + squeeze_period

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_ichimoku(df, self.tenkan_period, self.kijun_period, self.senkou_b_period, self.displacement_period)
        df = add_donchian_width(df, self.squeeze_period, self.squeeze_period, self.squeeze_q)
        df['test_top_level'] = df['ichi_cloud_top'].copy()
        df['test_bottom_level'] = df['ichi_cloud_bottom'].copy()
        df = self.add_slice_df(df)
        pdata['chart'] = df
        top_level = df['test_top_level'].iat[-1]
        bottom_level = df['test_bottom_level'].iat[-1]
        pdata['levels'] = [top_level, bottom_level]
        return pdata

    def _get_action_from_row(self, row):
        if self.use_squeeze and row['dcw_squeeze']:
            return None
        return 'spred_all_level'
