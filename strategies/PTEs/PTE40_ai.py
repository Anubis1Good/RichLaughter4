from strategies.BaseTE import BaseTE
from for_strategies.classic_indicators import add_donchan_channel, add_sma, add_bollinger, add_adx, add_atr, add_chop, add_keltner_channel
from for_strategies.help_indicators import add_big_volume
from for_strategies.fix_params import fix_two_periods_hm, fix_three_periods_hm

"""
PTE40_ai — классический трендовый и канальный алготрейдинг с защитой от дребезга.

Принципы всех стратегий файла:
1. Вход — только по кроссоверу/пробою с использованием сдвинутых колонок (shift(1)) и запасом
   (буфер в долях цены) — не по простому нахождению выше/ниже уровня.
2. Выход — пересечение центральной линии канала/MA с запасом exit_buff (0.3-0.5%) либо
   встроенные stop/take BaseTE.
3. Фильтр боковика: Choppiness / ADX — входы только вне флэта, качели — только во флэте.
4. Каузальность: только конечные rolling-окна и shift(+1); EMA/KAMA/Supertrend намеренно
   не используются (рекурсивные/ewm-фильтры не инвариантны к окну — ломают равенство
   check_strategy_faster и check_strategy_window).
5. Детерминированность сравнений: пороги-буферы вместо сравнения с нулём и с точными
   значениями на сетке данных (см. PROJECT_CONTEXT.md §11.1 п.9).
"""

# 25.11.26 перевернуть
class PTE40_DCRISE(BaseTE):
    """stop=None, take=None, period=15, chop_period=14, adx_period=14, adx_min=25, chop_max=55, enter_buff=0.0, exit_buff=0.006, max_period=70

    Черепаший пробой канала Дончиана: вход только на баре закрытия ВЫШЕ максимума канала
    ПРЕДЫДУЩЕГО бара с запасом enter_buff (кроссовер по shift(1)) и только при подтверждённом
    тренде (chop <= chop_max, adx > adx_min). Выход — возврат через центр канала с запасом
    exit_buff (гистерезис против дребезга).
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=15, chop_period=14, adx_period=14, adx_min=25.0, chop_max=55.0,
                 enter_buff=0.0, exit_buff=0.006, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.chop_period, self.adx_period = fix_three_periods_hm(period, chop_period, adx_period, max_period)
        self.adx_min = adx_min
        self.chop_max = chop_max
        self.enter_buff = enter_buff
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period)
        df = add_chop(df, self.chop_period)
        df = add_adx(df, self.adx_period)
        df['dc_top_prev'] = df['max_hb'].shift(1)
        df['dc_bot_prev'] = df['min_hb'].shift(1)
        df['close_prev'] = df['close'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        up_gate = row['dc_top_prev'] * (1.0 + self.enter_buff)
        dn_gate = row['dc_bot_prev'] * (1.0 - self.enter_buff)
        filters_ok = row['chop'] <= self.chop_max and row['adx'] > self.adx_min

        # пробой границы канала прошлого бара с запасом (кроссовер, не "нахождение выше")
        if row['close'] > up_gate and row['close_prev'] <= up_gate and filters_ok:
            return 'open_long'
        if row['close'] < dn_gate and row['close_prev'] >= dn_gate and filters_ok:
            return 'open_short'
        # выход через центр канала с запасом
        if row['close'] < row['avarege'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['avarege'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None

# 25.11.26 перевернуть
class PTE40_TWINMA(BaseTE):
    """stop=None, take=None, fast_period=10, slow_period=50, adx_period=14, adx_min=20, cross_buff=0.002, exit_buff=0.008, max_period=70

    Кроссовер двух SMA с гистерезисом и ADX-фильтром: вход при пересечении быстрой SMA
    медленной с запасом cross_buff (кроссовер по shift(1)), выход при откате быстрой ниже
    медленной на exit_buff. Широкая гистерезисная полоса между порогами входа и выхода.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 fast_period=10, slow_period=50, adx_period=14, adx_min=20.0,
                 cross_buff=0.002, exit_buff=0.008, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.fast_period, self.slow_period, self.adx_period = fix_three_periods_hm(fast_period, slow_period, adx_period, max_period)
        self.adx_min = adx_min
        self.cross_buff = cross_buff
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_sma(df, self.fast_period)
        df = df.rename(columns={'sma': 'sma_fast'})
        df = add_sma(df, self.slow_period)
        df = df.rename(columns={'sma': 'sma_slow'})
        df = add_adx(df, self.adx_period)
        df['sma_fast_prev'] = df['sma_fast'].shift(1)
        df['sma_slow_prev'] = df['sma_slow'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        adx_ok = row['adx'] > self.adx_min
        up_gate = row['sma_slow'] * (1.0 + self.cross_buff)
        dn_gate = row['sma_slow'] * (1.0 - self.cross_buff)

        # кроссовер быстрой SMA над медленной с запасом (только вне флэта)
        if adx_ok and row['sma_fast'] > up_gate and row['sma_fast_prev'] <= row['sma_slow_prev'] * (1.0 + self.cross_buff):
            return 'open_long'
        if adx_ok and row['sma_fast'] < dn_gate and row['sma_fast_prev'] >= row['sma_slow_prev'] * (1.0 - self.cross_buff):
            return 'open_short'
        # выход — откат быстрой SMA за медленную с запасом exit_buff
        if row['sma_fast'] < row['sma_slow'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['sma_fast'] > row['sma_slow'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None

# 25.11.26 перевернуть
class PTE40_KELTBREAK(BaseTE):
    """stop=None, take=None, period=30, atr_period=14, chop_period=14, adx_period=14, adx_min=28, mult_atr=2.0, chop_max=50, enter_buff=0.002, exit_buff=0.01, max_period=70

    Пробой канала Кельтнера (SMA + mult_atr*ATR): вход только на баре закрытия за границей
    канала ПРЕДЫДУЩЕГО бара с запасом enter_buff (кроссовер по shift(1)) при подтверждённом
    тренде (chop <= chop_max, adx > adx_min). Выход — возврат через середину канала
    с запасом exit_buff.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=30, atr_period=14, chop_period=14, adx_period=14, adx_min=28.0,
                 mult_atr=2.0, chop_max=50.0, enter_buff=0.002, exit_buff=0.01, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.atr_period, self.chop_period = fix_three_periods_hm(period, atr_period, chop_period, max_period)
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.mult_atr = mult_atr
        self.chop_max = chop_max
        self.enter_buff = enter_buff
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_atr(df, self.atr_period)
        df = add_keltner_channel(df, self.period, self.mult_atr)
        df = add_chop(df, self.chop_period)
        df = add_adx(df, self.adx_period)
        df['kelt_up_prev'] = df['keltner_upper'].shift(1)
        df['kelt_dn_prev'] = df['keltner_lower'].shift(1)
        df['close_prev'] = df['close'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        up_gate = row['kelt_up_prev'] * (1.0 + self.enter_buff)
        dn_gate = row['kelt_dn_prev'] * (1.0 - self.enter_buff)
        filters_ok = row['chop'] <= self.chop_max and row['adx'] > self.adx_min

        if row['close'] > up_gate and row['close_prev'] <= up_gate and filters_ok:
            return 'open_long'
        if row['close'] < dn_gate and row['close_prev'] >= dn_gate and filters_ok:
            return 'open_short'
        if row['close'] < row['keltner_middle'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['keltner_middle'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None

# 25.11.26 перевернуть
class PTE40_BBVOLUME(BaseTE):
    """stop=None, take=None, period=30, vol_period=30, mult_bb=2.0, vol_mult=2.0, enter_buff=0.002, exit_buff=0.006, max_period=70

    Пробой полосы Боллиндера с подтверждением объёмом: вход на кроссовере закрытия за
    bbu/bbd ПРЕДЫДУЩЕГО бара с запасом enter_buff (shift(1)) только на большом объёме
    (is_big). Выход — возврат через среднюю полосу (sma) с запасом exit_buff.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=30, vol_period=30, mult_bb=2.0, vol_mult=2.0, enter_buff=0.002,
                 exit_buff=0.006, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.vol_period = fix_two_periods_hm(period, vol_period, max_period)
        self.mult_bb = mult_bb
        self.vol_mult = vol_mult
        self.enter_buff = enter_buff
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_bollinger(df, self.period, 'close', self.mult_bb)
        df = add_big_volume(df, self.vol_period, self.vol_mult)
        df['bbu_prev'] = df['bbu'].shift(1)
        df['bbd_prev'] = df['bbd'].shift(1)
        df['close_prev'] = df['close'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        up_gate = row['bbu_prev'] * (1.0 + self.enter_buff)
        dn_gate = row['bbd_prev'] * (1.0 - self.enter_buff)

        if row['close'] > up_gate and row['close_prev'] <= up_gate and row['is_big']:
            return 'open_long'
        if row['close'] < dn_gate and row['close_prev'] >= dn_gate and row['is_big']:
            return 'open_short'
        if row['close'] < row['sma'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['sma'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None

# 25.11.26 перевернуть
class PTE40_TRENDRIDER(BaseTE):
    """stop=None, take=None, period=30, dc_period=30, adx_period=14, adx_min=25, adx_off=15, enter_buff=0.004, exit_buff=0.006, max_period=70

    Трендовая стратегия с пирамидингом (числовая целевая позиция): цена выше SMA с запасом
    enter_buff и ADX > adx_min -> 1 юнит; подтверждение продолжения (пробой максимума канала
    ПРЕДЫДУЩЕГО бара) -> добор до 2 юнитов. Выход в 0 при гибели тренда: ADX < adx_off
    (гистерезис adx_off < adx_min) или уход цены за SMA на exit_buff. Шорт — зеркально.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=30, dc_period=30, adx_period=14, adx_min=25.0, adx_off=15.0,
                 enter_buff=0.004, exit_buff=0.006, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.dc_period, self.adx_period = fix_three_periods_hm(period, dc_period, adx_period, max_period)
        self.adx_min = adx_min
        self.adx_off = adx_off
        self.enter_buff = enter_buff
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_sma(df, self.period)
        df = df.rename(columns={'sma': 'sma_tr'})
        df = add_donchan_channel(df, self.dc_period)
        df = add_adx(df, self.adx_period)
        df['dc_top_prev'] = df['max_hb'].shift(1)
        df['dc_bot_prev'] = df['min_hb'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        long_trend = row['close'] > row['sma_tr'] * (1.0 + self.enter_buff) and row['adx'] > self.adx_min
        short_trend = row['close'] < row['sma_tr'] * (1.0 - self.enter_buff) and row['adx'] > self.adx_min

        if long_trend and row['close'] > row['dc_top_prev']:
            return 2
        if long_trend:
            return 1
        if short_trend and row['close'] < row['dc_bot_prev']:
            return -2
        if short_trend:
            return -1
        # тренд умер (ADX-гистерезис или уход за SMA с запасом) — в плоскую
        if row['adx'] < self.adx_off or row['close'] < row['sma_tr'] * (1.0 - self.exit_buff) or row['close'] > row['sma_tr'] * (1.0 + self.exit_buff):
            return 0
        return None

# 25.11.26 перевернуть
class PTE40_STEPGUARD(BaseTE):
    """stop=None, take=None, period=50, chop_period=14, adx_period=14, step_mult=10, chop_min=55, adx_break=28, break_buff=0.003, max_period=70

    Канальные качели лимитками со сдвигом от лучшей цены: во флэте (chop >= chop_min,
    ADX спокойный) — 'spred_all_step_N' (лимитки на step_mult тиков от best bid/ask).
    Решительный пробой канала ПРЕДЫДЩЕГО бара с запасом break_buff или всплеск ADX
    (adx > adx_break) — 'close_all' (качели останавливаются на время тренда).
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=50, chop_period=14, adx_period=14, step_mult=10, chop_min=55.0,
                 adx_break=28.0, break_buff=0.003, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.chop_period, self.adx_period = fix_three_periods_hm(period, chop_period, adx_period, max_period)
        self.step_mult = int(step_mult)
        self.chop_min = chop_min
        self.adx_break = adx_break
        self.break_buff = break_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period)
        df = add_chop(df, self.chop_period)
        df = add_adx(df, self.adx_period)
        df['dc_top_prev'] = df['max_hb'].shift(1)
        df['dc_bot_prev'] = df['min_hb'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # тренд пришёл — качели стоп (гистерезис: пробой с запасом или сильный ADX)
        if row['adx'] > self.adx_break:
            return 'close_all'
        if row['close'] > row['dc_top_prev'] * (1.0 + self.break_buff):
            return 'close_all'
        if row['close'] < row['dc_bot_prev'] * (1.0 - self.break_buff):
            return 'close_all'
        # боковик — лимитные качели со сдвигом от лучшей цены
        if row['chop'] >= self.chop_min:
            return f'spred_all_step_{self.step_mult}'
        return None

# 25.11.26 перевернуть
class PTE40_LEVELTWIN(BaseTE):
    """stop=None, take=None, period=40, chop_period=14, adx_period=14, chop_min=55, adx_break=25, break_buff=0.003, max_period=70

    Качели по ценовым уровням канала Дончиана: границы канала (реальные экстремумы диапазона)
    пишутся в pdata['levels'] (и в test_top_level/test_bottom_level для быстрого теста),
    стратегия возвращает 'spred_all_level' — лимитный вход от нижней границы и выход у верхней.
    Решительный пробой границы ПРЕДЫДЩЕГО бара с запасом break_buff или ADX > adx_break —
    'close_all' (уровни пробиты, качели останавливаются).
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=40, chop_period=14, adx_period=14, chop_min=55.0,
                 adx_break=25.0, break_buff=0.003, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.chop_period, self.adx_period = fix_three_periods_hm(period, chop_period, adx_period, max_period)
        self.chop_min = chop_min
        self.adx_break = adx_break
        self.break_buff = break_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period)
        df = add_chop(df, self.chop_period)
        df = add_adx(df, self.adx_period)
        df['test_top_level'] = df['max_hb'].copy()
        df['test_bottom_level'] = df['min_hb'].copy()
        df['dc_top_prev'] = df['max_hb'].shift(1)
        df['dc_bot_prev'] = df['min_hb'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        top_level = df['test_top_level'].iat[-1]
        bottom_level = df['test_bottom_level'].iat[-1]
        pdata['levels'] = [top_level, bottom_level]
        return pdata

    def _get_action_from_row(self, row):
        if row['adx'] > self.adx_break:
            return 'close_all'
        if row['close'] > row['dc_top_prev'] * (1.0 + self.break_buff):
            return 'close_all'
        if row['close'] < row['dc_bot_prev'] * (1.0 - self.break_buff):
            return 'close_all'
        if row['chop'] >= self.chop_min:
            return 'spred_all_level'
        return None
