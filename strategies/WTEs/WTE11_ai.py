from strategies.BaseTE import BaseTE
from for_strategies.zai_volume_indicators import add_vwap_daily, add_obv_net, add_force_index, add_relative_volume
from for_strategies.vsa_indicators import add_vsai
from for_strategies.classic_indicators import add_sma
from for_strategies.fix_params import fix_two_periods_hm, fix_three_periods_hm

"""
WTE11_ai — объёмные стратегии на конкретных рыночных паттернах.

Библиотеки: zai_volume_indicators (дневной VWAP со std-полосами, оконный OBV с сигнальной
линией, Force Index, Relative Volume / Volume Z-Score) и vsa_indicators (vsai — «усилие на
единицу хода»). Скользящие средние — SMA (add_sma), а не EMA: рекурсивные/ewm-фильтры не
инвариантны к окну и ломают равенство check_strategy_faster и check_strategy_window
(PROJECT_CONTEXT.md §11.1 п.9).

Важно про дневной VWAP (add_vwap_daily): значение привязано к началу торгового дня по ms.
Для идентичности fast/window тестов окно тестера должно накрывать ВЕСЬ текущий день
(для TATN 5m максимум 203 бара/день -> window >= ~233).
"""

# 25.11.26 ну да, но надо доработать
class WTE11_VWAP_REVERSION(BaseTE):
    """stop=None, take=None, band=2.0, vol_period=20, fade_rvol=1.0, min_gap=0.003

    Возврат к дневному VWAP при аномальном отклонении: вход в лонг, когда цена ВЫХОДИЛА за
    нижнюю std-полосу VWAP на прошлом баре (close_prev < vwap_dn_prev) и вернулась внутрь
    полосы (close >= vwap_dn) при затухающем объёме (rvol_ratio < fade_rvol — кульминация
    отклонения выдохлась), при этом до линии VWAP остаётся ход не менее min_gap (иначе
    сделка бессмысленна — гистерезис против дребезга у самой цели). Выход — возврат цены к
    линии VWAP (close >= vwap_value). Шорт — зеркально от верхней полосы.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 band=2.0, vol_period=20, fade_rvol=1.0, min_gap=0.003):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.band = band
        self.vol_period = vol_period
        self.fade_rvol = fade_rvol
        self.min_gap = min_gap

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_vwap_daily(df, self.band)
        df = add_relative_volume(df, self.vol_period)
        df['vwap_dn_prev'] = df['vwap_dn'].shift(1)
        df['vwap_up_prev'] = df['vwap_up'].shift(1)
        df['close_prev'] = df['close'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход: возврат внутрь полосы после экстремального отклонения при затухании объёма;
        # guard close < vwap_value — цель ещё не достигнута (нет входа «в лоб» через VWAP)
        if row['close'] >= row['vwap_dn'] and row['close'] < row['vwap_value'] \
                and row['close_prev'] < row['vwap_dn_prev'] and row['rvol_ratio'] < self.fade_rvol:
            return 'open_long'
        if row['close'] <= row['vwap_up'] and row['close'] > row['vwap_value'] \
                and row['close_prev'] > row['vwap_up_prev'] and row['rvol_ratio'] < self.fade_rvol:
            return 'open_short'
        # выход: пересечение линии VWAP — цель сделки
        if row['close'] >= row['vwap_value']:
            return 'close_long'
        if row['close'] <= row['vwap_value']:
            return 'close_short'
        return None

# 25.11.26 ну тоже ничего
class WTE11_CLIMAX_FADE(BaseTE):
    """stop=None, take=None, vol_period=20, rng_period=20, vsai_period=20, z_thr=2.0, candle_mult=1.5, max_period=70

    Разворот после кульминации объёма (VSA-климакс): кульминационная свеча — длинный бар
    (тело >= candle_mult * средний диапазон) на объёмном выбросе (rvol_z >= z_thr) с
    аномальным «усилием на ход» (vsai >= vsaima) против закрытия. Вход ПРОТИВ кульминации
    только на следующем баре-подтверждении остановки (close развернулся против кульминации).
    Выход — появление зеркальной кульминации, плюс встроенные stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 vol_period=20, rng_period=20, vsai_period=20, z_thr=2.0, candle_mult=1.5, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.vol_period, self.rng_period, self.vsai_period = fix_three_periods_hm(vol_period, rng_period, vsai_period, max_period)
        self.z_thr = z_thr
        self.candle_mult = candle_mult

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_relative_volume(df, self.vol_period)
        df = add_vsai(df, self.vsai_period)
        df['zai_body'] = (df['close'] - df['open']).abs()
        df['zai_rng_ma'] = (df['high'] - df['low']).rolling(self.rng_period).mean()
        df['close_prev'] = df['close'].shift(1)
        df['open_prev'] = df['open'].shift(1)
        df['zai_body_prev'] = df['zai_body'].shift(1)
        df['zai_rng_ma_prev'] = df['zai_rng_ma'].shift(1)
        df['rvol_z_prev'] = df['rvol_z'].shift(1)
        df['vsai_prev'] = df['vsai'].shift(1)
        df['vsaima_prev'] = df['vsaima'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _climax(self, row, prefix):
        """Кульминационная свеча: длинное тело + объёмный выброс + аномальное усилие (vsai).

        prefix: '' — текущий бар, '_prev' — предыдущий (shift-колонки preprocessing).
        """
        return (row[f'rvol_z{prefix}'] >= self.z_thr
                and row[f'zai_body{prefix}'] >= self.candle_mult * row[f'zai_rng_ma{prefix}']
                and row[f'vsai{prefix}'] >= row[f'vsaima{prefix}'])

    def _get_action_from_row(self, row):
        # зеркальная кульминация закрывает позицию (выход по обратному импульсу)
        if row['close'] < row['open'] and self._climax(row, ''):
            return 'close_long'
        if row['close'] > row['open'] and self._climax(row, ''):
            return 'close_short'
        # вход против вчерашней кульминации при подтверждении остановки
        if row['close'] > row['close_prev'] and row['close_prev'] < row['open_prev'] and self._climax(row, '_prev'):
            return 'open_long'
        if row['close'] < row['close_prev'] and row['close_prev'] > row['open_prev'] and self._climax(row, '_prev'):
            return 'open_short'
        return None

# 25.11.26 плохо
class WTE11_OBV_BREAKOUT(BaseTE):
    """stop=None, take=None, period=30, obv_period=20, sig_period=50, exit_buff=0.005, max_period=100

    Подтверждённый пробой с фильтром ложных выносов: вход в лонг только когда цена
    закрывается выше максимума ПРЕДЫДУЩИХ period баров (кроссовер по shift-колонкам) И
    оконный OBV (obv_net) выше своей сигнальной линии (obv_net_sig — SMA, ewm-фильтры
    неинвариантны к окну). Выход — объёмная поддержка ушла (obv_net ниже сигнальной) И цена
    вернулась под уровень пробоя с запасом exit_buff — ложный вынос закрыт. Шорт — зеркально.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=30, obv_period=20, sig_period=50, exit_buff=0.005, max_period=100):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.obv_period, self.sig_period = fix_three_periods_hm(period, obv_period, sig_period, max_period)
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_obv_net(df, self.obv_period, self.sig_period)
        df['hi_prev'] = df['high'].rolling(self.period).max().shift(1)
        df['hi_2prev'] = df['high'].rolling(self.period).max().shift(2)
        df['lo_prev'] = df['low'].rolling(self.period).min().shift(1)
        df['lo_2prev'] = df['low'].rolling(self.period).min().shift(2)
        df['close_prev'] = df['close'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        obv_up = row['obv_net'] > row['obv_net_sig']
        # пробой локального максимума с подтверждением объёма
        if row['close'] > row['hi_prev'] and row['close_prev'] <= row['hi_2prev'] and obv_up:
            return 'open_long'
        if row['close'] < row['lo_prev'] and row['close_prev'] >= row['lo_2prev'] and not obv_up:
            return 'open_short'
        # объёмная поддержка ушла и цена вернулась под уровень пробоя с запасом — ложный вынос
        if not obv_up and row['close'] < row['hi_prev'] * (1.0 - self.exit_buff):
            return 'close_long'
        if obv_up and row['close'] > row['lo_prev'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None

# 25.11.26 плохо
class WTE11_FORCE_PULLBACK(BaseTE):
    """stop=None, take=None, fi_period=13, sma_period=30, flush_window=10, fi_thr=0.3, turn_eps=0.05, trend_buff=0.002, exit_buff=0.004, max_period=70

    Откат в сильном тренде по Force Index: тренд — цена выше медленной SMA с запасом
    trend_buff. Глубокое вытряхивание — нормированный Force Index (fi_norm) провалился ниже
    -fi_thr за последние flush_window баров (rolling min); вход — разворот FI вверх минимум
    на turn_eps (покупка паники слабых рук в тренде). Выход — потеря тренда: цена ушла под
    SMA с запасом exit_buff. Шорт — зеркально. Гистерезис: повторный вход требует НОВОГО
    глубокого провала FI.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 fi_period=13, sma_period=30, flush_window=10, fi_thr=0.3, turn_eps=0.05,
                 trend_buff=0.002, exit_buff=0.004, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.fi_period, self.sma_period = fix_two_periods_hm(fi_period, sma_period, max_period)
        self.flush_window = flush_window
        self.fi_thr = fi_thr
        self.turn_eps = turn_eps
        self.trend_buff = trend_buff
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_force_index(df, self.fi_period)
        df = add_sma(df, self.sma_period)
        df = df.rename(columns={'sma': 'sma_tr'})
        df['fi_norm_prev'] = df['fi_norm'].shift(1)
        df['fi_norm_min'] = df['fi_norm'].rolling(self.flush_window).min()
        df['fi_norm_max'] = df['fi_norm'].rolling(self.flush_window).max()
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        up_trend = row['close'] > row['sma_tr'] * (1.0 + self.trend_buff)
        dn_trend = row['close'] < row['sma_tr'] * (1.0 - self.trend_buff)

        # свежее вытряхивание (экстремум FI за окно за порогом) разворачивается против паники
        if up_trend and row['fi_norm_min'] < -self.fi_thr and row['fi_norm'] > row['fi_norm_prev'] + self.turn_eps:
            return 'open_long'
        if dn_trend and row['fi_norm_max'] > self.fi_thr and row['fi_norm'] < row['fi_norm_prev'] - self.turn_eps:
            return 'open_short'
        # потеря тренда
        if row['close'] < row['sma_tr'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['sma_tr'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None

# 25.11.26 плохо
class WTE11_VOL_SQUEEZE_STEP(BaseTE):
    """stop=None, take=None, vol_period=20, quiet_rvol=0.5, spike_z=2.5, step_mult=25

    Маркет-мейкерские качели в фазе низкого объёма: тихий рынок (rvol_ratio <= quiet_rvol) —
    лимитные заявки 'spred_all_step_N' со сдвигом step_mult тиков от лучшей цены. Резкий
    всплеск объёма (rvol_z >= spike_z) — 'close_all': фаза тишины кончилась, пришёл движок.
    Гистерезис: качели возобновляются только когда объём снова затихает ниже quiet_rvol.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 vol_period=20, quiet_rvol=0.5, spike_z=2.5, step_mult=25):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.vol_period = vol_period
        self.quiet_rvol = quiet_rvol
        self.spike_z = spike_z
        self.step_mult = int(step_mult)

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_relative_volume(df, self.vol_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # всплеск объёма — качели стоп
        if row['rvol_z'] >= self.spike_z:
            return 'close_all'
        # тихий флэт — лимитные качели со сдвигом от лучшей цены
        if row['rvol_ratio'] <= self.quiet_rvol:
            return f'spred_all_step_{self.step_mult}'
        return None
