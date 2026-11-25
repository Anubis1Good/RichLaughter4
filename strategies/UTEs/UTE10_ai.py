from strategies.BaseTE import BaseTE
from for_strategies.zai_smc_indicators import add_fvg, add_swing_points, add_order_blocks, add_liquidity_sweep, add_premium_discount
from for_strategies.classic_indicators import add_sma, add_adx, add_bollinger, add_chop
from for_strategies.classic_indicators2 import add_fractal_dimension_index
from for_strategies.pva_indicators import add_plus_delta_fc_window
from for_strategies.fix_params import fix_three_periods_hm

"""
UTE10_ai — стратегии на концепциях Smart Money и зонального трейдинга
(Fair Value Gap, Liquidity Sweep, Order Block, Premium/Discount, структурный слом BOS)
+ улучшенные версии UTE6_SHERIFF и UTE4_FALCON2 (добавлен фильтр рыночного режима и
SMC-зон для отсечения ложных входов).

Каузальность: все SMC-индикаторы zai_smc_indicators строго каузальны (FVG фиксируется на
3-й свече, свинги с задержкой подтверждения left_bars, уровни хранятся ограниченным
ffill(limit)); classic_indicators/classic_indicators2 — конечные rolling-окна
(ewm/рекурсивные фильтры не используются). Гистерезис: входы по событиям (ретест, закол,
касание зоны) с подтверждением, выходы — пробой уровня с запасом exit_buff либо stop/take.
"""


class UTE10_FVGRETEST(BaseTE):
    """stop=None, take=None, sma_period=30, ffill_limit=20, exit_buff=0.003

    Тест подтверждённого имбаланса: последний бычий Fair Value Gap (середина гэпа хранится
    ограниченным ffill) выступает поддержкой; вход в лонг, когда цена ретестает середину
    гэпа сверху (low каснулась, close удержалась выше) в контексте импульса вверх
    (close > sma). Выход — решительное закрытие под серединой гэпа (зона перекрыта)
    либо stop/take. Шорт — зеркально от медвежьего гэпа.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 sma_period=30, ffill_limit=20, exit_buff=0.003):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.sma_period = sma_period
        self.ffill_limit = ffill_limit
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_fvg(df)
        df = add_sma(df, self.sma_period)
        df['zai_fvg_up_last'] = df['fvg_bull_mid'].ffill(limit=self.ffill_limit)
        df['zai_fvg_dn_last'] = df['fvg_bear_mid'].ffill(limit=self.ffill_limit)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход: ретест середины гэпа с удержанием и импульсом в сторону гэпа
        if row['low'] <= row['zai_fvg_up_last'] and row['close'] > row['zai_fvg_up_last'] \
                and row['close'] > row['sma']:
            return 'open_long'
        if row['high'] >= row['zai_fvg_dn_last'] and row['close'] < row['zai_fvg_dn_last'] \
                and row['close'] < row['sma']:
            return 'open_short'
        # выход: зона перекрыта (решительное закрытие за серединой гэпа)
        if row['close'] < row['zai_fvg_up_last'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['zai_fvg_dn_last'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None


class UTE10_LIQSWEEP(BaseTE):
    """stop=None, take=None, swing_period=3, memory=20

    Разворот после снятия ликвидности: sweep_down — бар заколол предыдущий подтверждённый
    свинг-минимум (уровень строго из прошлого) и закрылся обратно выше — вход в лонг;
    sweep_up — закол свинг-максимума с закрытием обратно ниже — шорт. Выход — зеркальный
    sweep (противоположная ликвидность снята) либо stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 swing_period=3, memory=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.swing_period = swing_period
        self.memory = memory

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_liquidity_sweep(df, self.swing_period, self.memory)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # sweep_down - лонг (закол минимума с возвратом); он же реверсирует шорт.
        # sweep_up - шорт (закол максимума с возвратом); он же реверсирует лонг.
        if row['sweep_down']:
            return 'open_long'
        if row['sweep_up']:
            return 'open_short'
        return None


class UTE10_ORDERBLOCK(BaseTE):
    """stop=None, take=None, vol_period=20, vol_mult=1.1, ffill_limit=20, exit_buff=0.003

    Отскок от активного Order Block: последний бычий OB (тело падающей свечи перед
    объёмным импульсом с FVG) хранится ограниченным ffill; вход в лонг при касании зоны
    (low <= ob_top) с бычьим закрытием выше дна зоны (подтверждение направлением свечи).
    Выход — зона слита (решительное закрытие под дном OB) либо stop/take. Шорт — зеркально
    от медвежьего OB.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 vol_period=20, vol_mult=1.1, ffill_limit=20, exit_buff=0.003):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.vol_period = vol_period
        self.vol_mult = vol_mult
        self.ffill_limit = ffill_limit
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_order_blocks(df, self.vol_period, self.vol_mult)
        df['zai_ob_bull_top_last'] = df['ob_bull_top'].ffill(limit=self.ffill_limit)
        df['zai_ob_bull_bot_last'] = df['ob_bull_bot'].ffill(limit=self.ffill_limit)
        df['zai_ob_bear_top_last'] = df['ob_bear_top'].ffill(limit=self.ffill_limit)
        df['zai_ob_bear_bot_last'] = df['ob_bear_bot'].ffill(limit=self.ffill_limit)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход: касание зоны + бычья/медвежья свеча с удержанием границы
        if row['low'] <= row['zai_ob_bull_top_last'] and row['close'] > row['open'] \
                and row['close'] > row['zai_ob_bull_bot_last']:
            return 'open_long'
        if row['high'] >= row['zai_ob_bear_bot_last'] and row['close'] < row['open'] \
                and row['close'] < row['zai_ob_bear_top_last']:
            return 'open_short'
        # выход: зона слита
        if row['close'] < row['zai_ob_bull_bot_last'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['zai_ob_bear_top_last'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None


class UTE10_PREMDISCOUNT(BaseTE):
    """stop=None, take=None, period=50, deep_thr=0.15, premium_thr=0.85

    Зональный возврат к среднему: глубокая Discount (pd_pos <= deep_thr нижней части
    скользящего диапазона) с разворотом закрытия вверх — лонг; глубокая Premium
    (pd_pos >= premium_thr) с разворотом вниз — шорт. Выход — возврат позиции цены к
    равновесию (pd_pos пересёк 0.5 — верхняя/нижняя половина диапазона) либо stop/take.
    Гистерезис: вход у края зоны (<=0.15), выход на середине (>=0.5).
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=50, deep_thr=0.15, premium_thr=0.85):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.deep_thr = deep_thr
        self.premium_thr = premium_thr

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_premium_discount(df, self.period)
        df['close_prev'] = df['close'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход: глубокая зона + разворот закрытия
        if row['pd_pos'] <= self.deep_thr and row['close'] > row['close_prev']:
            return 'open_long'
        if row['pd_pos'] >= self.premium_thr and row['close'] < row['close_prev']:
            return 'open_short'
        # выход: цена вернулась к равновесию диапазона
        if row['pd_pos'] >= 0.5:
            return 'close_long'
        if row['pd_pos'] <= 0.5:
            return 'close_short'
        return None


class UTE10_SWINGBREAK(BaseTE):
    """stop=None, take=None, swing_period=3, memory=20, hurst_period=60, adx_period=14, adx_min=25, fdi_max=1.5, exit_buff=0.003

    Структурный слом (BOS) с фильтром трендового режима: вход в лонг при закрытии выше
    последнего подтверждённого swing-хая (кроссовер по shift-колонкам) только в трендовом
    режиме (adx >= adx_min и fdi <= fdi_max — низкая фрактальная размерность). Выход —
    структурный слом против позиции: закрытие под swing-low с запасом exit_buff, либо
    stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 swing_period=3, memory=20, hurst_period=60, adx_period=14, adx_min=25.0,
                 fdi_max=1.5, exit_buff=0.003):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.swing_period = swing_period
        self.memory = memory
        self.hurst_period = hurst_period
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.fdi_max = fdi_max
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_swing_points(df, self.swing_period, self.memory)
        df = add_adx(df, self.adx_period)
        df = add_fractal_dimension_index(df, self.hurst_period)
        # кроссовер BOS: предыдущее закрытие было по другую сторону уровня
        df['zai_bos_up_prev'] = (df['close'] <= df['smc_swing_high_last']).shift(1, fill_value=False)
        df['zai_bos_dn_prev'] = (df['close'] >= df['smc_swing_low_last']).shift(1, fill_value=False)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _trend_ok(self, row):
        return row['adx'] >= self.adx_min and row['fdi'] <= self.fdi_max

    def _get_action_from_row(self, row):
        # вход: BOS — закрытие за подтверждённым свингом (кроссовер) в трендовом режиме
        if row['close'] > row['smc_swing_high_last'] and row['zai_bos_up_prev'] and self._trend_ok(row):
            return 'open_long'
        if row['close'] < row['smc_swing_low_last'] and row['zai_bos_dn_prev'] and self._trend_ok(row):
            return 'open_short'
        # выход: структурный слом против позиции с запасом
        if row['close'] < row['smc_swing_low_last'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['smc_swing_high_last'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None


class UTE10_FALCONPRO(BaseTE):
    """stop=None, take=None, period_window=55, period_fractal_free=5, n_fractals=3, allowance=0.1, adx_period=14, adx_min=25, pd_period=50

    Улучшенная UTE4_FALCON2 (автор: «хорошо работает на тренде и плохо на флете»).
    Логика фрактального канала сохранена (fade границ pdf_up/pdf_down при allowance),
    добавлено:
    1) трендовый фильтр adx >= adx_min — входы только при подтверждённом тренде;
    2) SMC-зоны: лонг только в нижней половине диапазона (pd_pos <= 0.5), шорт — в верхней
       (pd_pos >= 0.5) — отсечка контртрендовых входов против зоны;
    3) добавлен выход на середине фрактального канала (в оригинале выходов не было).
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period_window=55, period_fractal_free=5, n_fractals=3, allowance=0.1,
                 adx_period=14, adx_min=25.0, pd_period=50):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_window = period_window
        self.period_fractal_free = period_fractal_free
        self.n_fractals = n_fractals
        self.allowance = allowance
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.pd_period = pd_period

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_plus_delta_fc_window(df, self.period_window, self.period_fractal_free, self.n_fractals)
        df['pdf_diff_percent'] = ((df['pdf_up'] - df['pdf_down']) / df['pdf_down']) * 100
        df['allowance'] = df['pdf_diff_percent'] > self.allowance
        df = add_adx(df, self.adx_period)
        df = add_premium_discount(df, self.pd_period)
        df['zai_pdf_mid'] = (df['pdf_up'] + df['pdf_down']) / 2.0
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход — fade границы канала в трендовом режиме и в правильной SMC-зоне
        if row['allowance'] and row['adx'] >= self.adx_min \
                and row['close'] <= row['pdf_down'] and row['pd_pos'] <= 0.5:
            return 'open_long'
        if row['allowance'] and row['adx'] >= self.adx_min \
                and row['close'] >= row['pdf_up'] and row['pd_pos'] >= 0.5:
            return 'open_short'
        # выход — середина фрактального канала (в оригинале выходов не было)
        if row['close'] >= row['zai_pdf_mid']:
            return 'close_long'
        if row['close'] <= row['zai_pdf_mid']:
            return 'close_short'
        return None


class UTE10_SHERIFFPRO(BaseTE):
    """stop=None, take=None, period=55, period_smas=2, mult_bb=2, chop_period=14, chop_min=55, pd_period=50

    Улучшенная UTE6_SHERIFF (GGD + пробой BB без какого-либо контекста рынка).
    Логика оригинала сохранена, добавлен фильтр рыночного режима и SMC-зон:
    1) GGD-контртрендовые входы внутри BB — только в боковике (chop >= chop_min) и только
       в правильной половине диапазона (лонг при pd_pos <= 0.5, шорт при pd_pos >= 0.5);
    2) пробойные входы за BB — только в трендовом режиме (chop < chop_min).
    Выходы как в оригинале отсутствуют (реверс по противоположному сигналу) + stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=55, period_smas=2, mult_bb=2, chop_period=14, chop_min=55.0, pd_period=50):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_smas = period_smas
        self.mult_bb = mult_bb
        self.chop_period = chop_period
        self.chop_min = chop_min
        self.pd_period = pd_period

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_bollinger(df, self.period, multiplier=self.mult_bb)
        df['high_sma'] = df['high'].rolling(self.period_smas).mean()
        df['low_sma'] = df['low'].rolling(self.period_smas).mean()
        df = add_chop(df, self.chop_period)
        df = add_premium_discount(df, self.pd_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        range_regime = row['chop'] >= self.chop_min
        trend_regime = row['chop'] < self.chop_min
        if row['high'] < row['bbu'] and row['low'] > row['bbd']:
            # боковик: GGD-контртренд только в правильной SMC-зоне
            if range_regime and row['pd_pos'] >= 0.5:
                if row['close'] >= row['high_sma']:
                    return 'open_short'
            if range_regime and row['pd_pos'] <= 0.5:
                if row['close'] <= row['low_sma']:
                    return 'open_long'
        else:
            # тренд: пробой BB в сторону пробоя
            if trend_regime:
                if row['low'] > row['bbu']:
                    return 'open_long'
                if row['high'] < row['bbd']:
                    return 'open_short'

        return None
