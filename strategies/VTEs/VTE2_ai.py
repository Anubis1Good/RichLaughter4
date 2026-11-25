from strategies.BaseTE import BaseTE
from for_strategies.zai_vsa_indicators import add_stopping_volume, add_no_demand_supply, add_climax_churn, add_volume_absorption
from for_strategies.zai_volume_indicators import add_relative_volume
from for_strategies.classic_indicators import add_sma, add_donchan_channel
from for_strategies.zigzag_indicators import add_zigzag_window_260926, add_drop_last_wzp, add_pattern18_zzw_260926, add_zzw_levels_260926, add_stop_loss_p18zzw_260926
from for_strategies.fix_params import fix_two_periods_hm, fix_three_periods_hm

"""
VTE2_ai — VSA-стратегии на побарном анализе спреда/закрытия/объёма + улучшенные версии
VTE1_EARTH и VTE1_MOON (авторские замечания в VTE1.py: EARTH «частит», MOON «слишком рано
закрывает сделки»).

Каузальность: все индикаторы — конечные скользящие окна (zai_vsa, rvol, Donchian, SMA) либо
инвариантный к окну оконный зигзаг add_zigzag_window_260926 (проверено: цепочка
zigzag_window -> drop_last -> pattern18_zzw -> zzw_levels даёт байт-в-байт одинаковые значения
на полном df и на срезе). Кумулятивные зигзаги (add_percent_zz190826/add_dzz_peaks) в новые
стратегии не включены — их история пивотов зависит от точки старта расчёта.

Гистерезис: входы — только на редких VSA-событиях у локальных экстремумов (с подтверждением
следующим баром либо закрытием обратно за уровень), выходы — центр канала / пробой уровня
с запасом exit_buff либо встроенные stop/take.
"""


class VTE2_STOPPINGVOL(BaseTE):
    """stop=None, take=None, period=30, vol_period=20, exit_period=20, exit_buff=0.003, max_period=70

    Stopping Volume / кульминация у локального экстремума с подтверждением: на прошлом баре —
    аномальный объём на узком теле после падения (sv_stopping) или кульминация продаж
    (sv_down_climax) прямо на локальном минимуме period баров; вход в лонг на СЛЕДУЮЩЕМ баре
    при развороте закрытия вверх. Шорт — зеркально от локального максимума (sv_up_climax).
    Выход — возврат через SMA с запасом exit_buff либо stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=30, vol_period=20, exit_period=20, exit_buff=0.003, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.vol_period, self.exit_period = fix_three_periods_hm(period, vol_period, exit_period, max_period)
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_stopping_volume(df, self.vol_period)
        df = add_sma(df, self.exit_period)
        df['sv_stopping_prev'] = df['sv_stopping'].shift(1)
        df['sv_down_climax_prev'] = df['sv_down_climax'].shift(1)
        df['sv_up_climax_prev'] = df['sv_up_climax'].shift(1)
        df['low_prev'] = df['low'].shift(1)
        df['high_prev'] = df['high'].shift(1)
        df['close_prev'] = df['close'].shift(1)
        df['zai_lo_ext'] = df['low'].rolling(self.period).min().shift(1)
        df['zai_hi_ext'] = df['high'].rolling(self.period).max().shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход против кульминации у локального экстремума при подтверждении разворота;
        # цена уже вернулась за уровень экстремума (guard против входа в продолжении коллапса)
        if row['low_prev'] <= row['zai_lo_ext'] and (row['sv_stopping_prev'] or row['sv_down_climax_prev']) \
                and row['close'] > row['close_prev'] and row['close'] > row['zai_lo_ext']:
            return 'open_long'
        if row['high_prev'] >= row['zai_hi_ext'] and row['sv_up_climax_prev'] \
                and row['close'] < row['close_prev'] and row['close'] < row['zai_hi_ext']:
            return 'open_short'
        # цель — возврат через SMA (выше для лонга); стоп — пробой локального экстремума
        if row['close'] >= row['sma'] * (1.0 + self.exit_buff):
            return 'close_long'
        if row['close'] <= row['sma'] * (1.0 - self.exit_buff):
            return 'close_short'
        if row['close'] < row['zai_lo_ext'] * (1.0 - self.exit_buff):
            return 'close_long'
        if row['close'] > row['zai_hi_ext'] * (1.0 + self.exit_buff):
            return 'close_short'
        return None


class VTE2_NODEMAND(BaseTE):
    """stop=None, take=None, period=15, rng_period=20, vol_period=20, spread_mult=1.0, vol_k=0.9, exit_buff=0.003, max_period=70

    No Demand / No Supply на тесте локального экстремума: шорт, когда цена тестирует максимум
    period баров узкой растущей свечой (спред <= spread_mult * средний) на падающем объёме
    (nds_low_vol) и закрывается обратно под уровнем — покупатель на тесте отсутствует.
    Лонг — зеркально: узкая падающая свеча на низком объёме у локального минимума, закрытие
    удержало уровень (No Supply). Выход — цель: середина диапазона (с запасом exit_buff),
    стоп: решительный пробой протестированного уровня.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=15, rng_period=20, vol_period=20, spread_mult=1.0, vol_k=0.9,
                 exit_buff=0.003, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.rng_period, self.vol_period = fix_three_periods_hm(period, rng_period, vol_period, max_period)
        self.spread_mult = spread_mult
        self.vol_k = vol_k
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_no_demand_supply(df, self.vol_period, self.vol_k)
        df['zai_rng_ma'] = (df['high'] - df['low']).rolling(self.rng_period).mean()
        df['zai_narrow'] = (df['high'] - df['low']) <= self.spread_mult * df['zai_rng_ma']
        df['zai_hi_ext'] = df['high'].rolling(self.period).max().shift(1)
        df['zai_lo_ext'] = df['low'].rolling(self.period).min().shift(1)
        df['zai_mid'] = (df['zai_hi_ext'] + df['zai_lo_ext']) / 2.0
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # вход: тест экстремума узкой свечой на слабом объёме с закрытием обратно за уровень
        if row['high'] >= row['zai_hi_ext'] and row['nds_low_vol'] and row['zai_narrow'] \
                and row['close'] > row['open'] and row['close'] <= row['zai_hi_ext']:
            return 'open_short'
        if row['low'] <= row['zai_lo_ext'] and row['nds_low_vol'] and row['zai_narrow'] \
                and row['close'] < row['open'] and row['close'] >= row['zai_lo_ext']:
            return 'open_long'
        # цель — середина диапазона; стоп — решительный пробой протестированного уровня
        if row['close'] <= row['zai_mid'] * (1.0 - self.exit_buff):
            return 'close_short'
        if row['close'] >= row['zai_mid'] * (1.0 + self.exit_buff):
            return 'close_long'
        if row['close'] > row['zai_hi_ext'] * (1.0 + self.exit_buff):
            return 'close_short'
        if row['close'] < row['zai_lo_ext'] * (1.0 - self.exit_buff):
            return 'close_long'
        return None


class VTE2_CLIMAXCHURN(BaseTE):
    """stop=None, take=None, period=30, vol_period=20, vol_q=0.8, spread_k=1.2, pos_thr=0.7, exit_buff=0.004, max_period=70

    Climax Churn на границе канала Дончиана: огромный объём при минимальном продвижении цены
    (churn_bar: объём в верхнем vol_q-квантиле при спреде <= spread_k * среднего) в верхней
    четверти канала после растущего бара — вход в шорт против предшествующего импульса;
    в нижней четверти после падающего бара — лонг. Выход — пересечение центра канала
    с запасом exit_buff либо stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=30, vol_period=20, vol_q=0.8, spread_k=1.2, pos_thr=0.7, exit_buff=0.004, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.vol_period = fix_two_periods_hm(period, vol_period, max_period)
        self.vol_q = vol_q
        self.spread_k = spread_k
        self.pos_thr = pos_thr
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_climax_churn(df, self.vol_period, self.vol_q, self.spread_k)
        df = add_donchan_channel(df, self.period)
        rng = (df['max_hb'] - df['min_hb']).replace(0, 1e-12)
        df['zai_ch_pos'] = (df['close'] - df['min_hb']) / rng
        df['close_prev'] = df['close'].shift(1)
        df['open_prev'] = df['open'].shift(1)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # топтание на огромном объёме у границы канала — вход против импульса
        if row['churn_bar'] and row['zai_ch_pos'] >= self.pos_thr and row['close_prev'] > row['open_prev']:
            return 'open_short'
        if row['churn_bar'] and row['zai_ch_pos'] <= 1.0 - self.pos_thr and row['close_prev'] < row['open_prev']:
            return 'open_long'
        # выход — центр канала с запасом
        if row['close'] >= row['avarege'] * (1.0 + self.exit_buff):
            return 'close_long'
        if row['close'] <= row['avarege'] * (1.0 - self.exit_buff):
            return 'close_short'
        return None


class VTE2_ABSORPTION(BaseTE):
    """stop=None, take=None, period=20, vol_period=20, vol_mult=2.0, lookback=20, strict_pos=0.3, exit_buff=0.004, max_period=70

    Поглощение объёмом на локальном экстремуме (ложный пробой): бар на объёме >= vol_mult *
    среднего пробивает экстремум последних lookback баров, но закрывается в противоположной
    половине диапазона — агрессию поглотили (abs_at_top -> шорт, abs_at_bottom -> лонг).
    Выход — центр канала Дончиана с запасом exit_buff либо stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period=20, vol_period=20, vol_mult=2.0, lookback=20, strict_pos=0.3, exit_buff=0.004, max_period=70):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period, self.vol_period = fix_two_periods_hm(period, vol_period, max_period)
        self.vol_mult = vol_mult
        self.lookback = lookback
        self.strict_pos = strict_pos
        self.exit_buff = exit_buff

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_volume_absorption(df, self.vol_period, self.vol_mult, self.lookback)
        df = add_donchan_channel(df, self.period)
        rng = (df['high'] - df['low']).replace(0, 1e-12)
        df['zai_close_pos'] = (df['close'] - df['low']) / rng
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        # усиленный гейт: закрытие поглощённого бара глубоко против пробоя
        if row['abs_at_bottom'] and row['zai_close_pos'] >= 1.0 - self.strict_pos:
            return 'open_long'
        if row['abs_at_top'] and row['zai_close_pos'] <= self.strict_pos:
            return 'open_short'
        # выход — центр канала с запасом
        if row['close'] >= row['avarege'] * (1.0 + self.exit_buff):
            return 'close_long'
        if row['close'] <= row['avarege'] * (1.0 - self.exit_buff):
            return 'close_short'
        return None


class VTE2_SPRINGZIGZAG(BaseTE):
    """stop=None, take=None, period_wzz=55, frac_wzz=0.1, n_wzp=6, exit_period=30, exit_buff=0.004, rvol_period=20, rvol_mode=1, rvol_thr=1.2, exit_mode='swing', min_width=0.005

    Spring / Upthrust на инвариантном оконном зигзаге: swing-уровни — минимум/максимум двух
    последних подтверждённых пивотов (add_drop_last_wzp убирает недоформированную точку).
    Spring: бар закалывает swing_low (low < уровня), но закрывается обратно выше — вход в лонг.
    Upthrust: прокол swing_high с закрытием обратно ниже — шорт. Выход — зеркальный паттерн
    (реверс), возврат через SMA с запасом exit_buff либо stop/take.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period_wzz=55, frac_wzz=0.1, n_wzp=6, exit_period=30, exit_buff=0.004,
                 rvol_period=20, rvol_mode=1, rvol_thr=1.2, exit_mode='swing', min_width=0.005):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_wzz = period_wzz
        self.frac_wzz = frac_wzz
        self.n_wzp = n_wzp
        self.exit_period = exit_period
        self.exit_buff = exit_buff
        self.rvol_period = rvol_period
        self.rvol_mode = rvol_mode
        self.rvol_thr = rvol_thr
        self.exit_mode = exit_mode
        self.min_width = min_width
        # add_drop_last_wzp удаляет последний (недоформированный) столбец wzp{n};
        # после дропа последние два ПОДТВЕРЖДЁННЫХ пивота — wzp{n-2} и wzp{n-1}
        self.wzp_a = f'wzp{n_wzp - 2}'
        self.wzp_b = f'wzp{n_wzp - 1}'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_zigzag_window_260926(df, self.period_wzz, self.frac_wzz, self.n_wzp)
        df = add_drop_last_wzp(df)
        df['zai_swing_low'] = df[[self.wzp_a, self.wzp_b]].min(axis=1)
        df['zai_swing_high'] = df[[self.wzp_a, self.wzp_b]].max(axis=1)
        df['zai_swing_width'] = (df['zai_swing_high'] - df['zai_swing_low']) / df['close']
        # стабильность структуры: свинги не перекрасились между барами (иначе цель/стопы
        # пересчитываются прямо под позицией и дают мгновенные выходы)
        df['zai_swing_stable'] = (df['zai_swing_low'] == df['zai_swing_low'].shift(1)) & \
                                 (df['zai_swing_high'] == df['zai_swing_high'].shift(1))
        df = add_sma(df, self.exit_period)
        df = add_relative_volume(df, self.rvol_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _vol_ok(self, row):
        # rvol_mode: 1 — закол на объёме (климакс-закол), -1 — на тонком рынке
        # (нет давления за пробой), 0 — без фильтра
        if self.rvol_mode == 1:
            return row['rvol_ratio'] >= self.rvol_thr
        if self.rvol_mode == -1:
            return row['rvol_ratio'] <= self.rvol_thr
        return True

    def _get_action_from_row(self, row):
        # ложный закол уровня с быстрым возвратом — реверс при зеркальном паттерне
        if row['low'] < row['zai_swing_low'] and row['close'] > row['zai_swing_low'] \
                and row['zai_swing_stable'] and row['zai_swing_width'] >= self.min_width and self._vol_ok(row):
            return 'open_long'
        if row['high'] > row['zai_swing_high'] and row['close'] < row['zai_swing_high'] \
                and row['zai_swing_stable'] and row['zai_swing_width'] >= self.min_width and self._vol_ok(row):
            return 'open_short'
        if self.exit_mode == 'swing':
            # цель — противоположный свинг зигзага; при перекраске структуры (уровни
            # перескочили/сжались) цель не считается валидной — позицию не закрываем
            valid = row['zai_swing_stable'] and row['zai_swing_width'] >= self.min_width
            if valid and row['close'] >= row['zai_swing_high'] * (1.0 - self.exit_buff):
                return 'close_long'
            if valid and row['close'] <= row['zai_swing_low'] * (1.0 + self.exit_buff):
                return 'close_short'
        else:
            # выход: возврат через SMA с запасом
            if row['close'] < row['sma'] * (1.0 - self.exit_buff):
                return 'close_long'
            if row['close'] > row['sma'] * (1.0 + self.exit_buff):
                return 'close_short'
        return None


class VTE2_EARTHPRO(BaseTE):
    """stop=None, take=None, period_wzz=55, frac_wzz=0.1, n_wzp=8, threshold_p18=0.1, drop_last=1, buff=0.1, divider=2, vol_period=20, min_rvol=0.5, min_width=0.001, leg_width=0.002, stop_buff=0.001, use_stop=0

    Улучшенная VTE1_EARTH (авторские проблемы: «частит», «мельчит при низкой волатильности»).
    Логика диспетчера pattern18 сохранена, добавлено:
    1) входы только на ПЕРЕХОДЕ паттерна (pattern18 != pattern18_prev) — устранение дребезга;
    2) фильтр объёма rvol_ratio >= min_rvol — отсев сигналов на «пустом» рынке;
    3) фильтр ширины структуры (bzp1-bzp4)/close >= min_width — отсев микродиапазонов;
    4) структурные стопы ssl/lsl отключены (use_stop=0): уровень на середине ноги
       зигзага мгновенно выносит контртрендовый вход у экстремума (дребезг);
       контроль риска — stop/take BaseTE; закрытия по сужению структуры требуют
       2-барного подтверждения паттерна.
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 period_wzz=55, frac_wzz=0.1, n_wzp=8, threshold_p18=0.1, drop_last=1,
                 buff=0.1, divider=2, vol_period=20, min_rvol=0.5, min_width=0.001, leg_width=0.002, stop_buff=0.001, use_stop=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_wzz = period_wzz
        self.frac_wzz = frac_wzz
        self.n_wzp = n_wzp
        self.threshold_p18 = threshold_p18
        self.drop_last = drop_last
        self.buff = buff
        self.divider = divider
        self.vol_period = vol_period
        self.min_rvol = min_rvol
        self.min_width = min_width
        self.leg_width = leg_width
        self.stop_buff = stop_buff
        self.use_stop = use_stop

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_zigzag_window_260926(df, self.period_wzz, self.frac_wzz, self.n_wzp)
        if self.drop_last:
            df = add_drop_last_wzp(df)
        df = add_pattern18_zzw_260926(df, self.threshold_p18)
        df = add_zzw_levels_260926(df, self.buff)
        df = add_stop_loss_p18zzw_260926(df, self.divider)
        df = add_relative_volume(df, self.vol_period)
        df['pattern18_prev'] = df['pattern18'].shift(1)
        # ширина последней ноги зигзага: при узкой ноге все уровни (стопы/цели) сжаты
        # и позиция мгновенно закрывается — вход только при достаточно широкой ноге
        # после add_drop_last_wzp столбец wzp{n} удалён; последняя нога — wzp{n-2}->wzp{n-1}
        self.wzp_leg_a = f'wzp{self.n_wzp - 2}'
        self.wzp_leg_b = f'wzp{self.n_wzp - 1}'
        df['zai_leg_width'] = (df[self.wzp_leg_a] - df[self.wzp_leg_b]).abs() / df['close']
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _entry_ok(self, row):
        """Гейт входа: переход паттерна + реальный объём + достаточная ширина структуры
        и последней ноги зигзага."""
        if row['pattern18'] == row['pattern18_prev']:
            return False
        if row['rvol_ratio'] < self.min_rvol:
            return False
        if (row['bzp1'] - row['bzp4']).__abs__() / row['close'] < self.min_width:
            return False
        if row['zai_leg_width'] < self.leg_width:
            return False
        return True

    def stop_loss_action(self, row):
        # стоп требует ДВУХ баров за уровнем (текущий + предыдущий) — однобарная wiggle
        # не закрывает позицию (анти-дребезг)
        if self.use_stop:
            if row['close'] > row['ssl'] * (1.0 + self.stop_buff) and row['close_prev_ssl_ok']:
                return 'close_short'
            if row['close'] < row['lsl'] * (1.0 - self.stop_buff) and row['close_prev_lsl_ok']:
                return 'close_long'
        return None

    def _get_action_from_row(self, row):
        ok = self._entry_ok(row)
        # закрытия по сужению структуры требуют, чтобы паттерн продержался >= 2 баров
        persisted = row['pattern18'] == row['pattern18_prev']
        # long
        if row['pattern18'] == 'joc':
            if ok and row['bzp3'] < row['close'] <= row['bzp2']:
                return 'open_long'

        if row['pattern18'] == 'btc':
            if ok and row['zp4'] <= row['close'] <= row['bzp4']:
                return 'open_long'

        # short
        if row['pattern18'] == 'bui':
            if ok and row['bzp3'] > row['close'] >= row['bzp2']:
                return 'open_short'

        if row['pattern18'] == 'bti':
            if ok and row['zp4'] >= row['close'] >= row['bzp4']:
                return 'open_short'

        # range
        if row['pattern18'] in ('top_range', 'double_top', 'weak_long'):
            if ok and row['bzp1'] <= row['close'] <= row['bzp3']:
                return 'open_long'
            if ok and row['bzp2'] >= row['close'] >= row['bzp4']:
                return 'open_short'

        if row['pattern18'] in ('bottom_range', 'double_bottom', 'weak_short'):
            if ok and row['bzp1'] >= row['close'] >= row['bzp3']:
                return 'open_short'
            if ok and row['bzp2'] <= row['close'] <= row['bzp4']:
                return 'open_long'

        if row['pattern18'] == 'narrowing_up':
            if persisted and row['bzp1'] >= row['close'] >= row['bzp3']:
                return 'close_long'
            if persisted and row['bzp2'] <= row['close'] <= row['zp2']:
                return 'close_short'

        if row['pattern18'] == 'narrowing_down':
            if persisted and row['bzp1'] <= row['close'] <= row['bzp3']:
                return 'close_short'
            if persisted and row['bzp2'] >= row['close'] >= row['zp2']:
                return 'close_long'

        if row['pattern18'] == 'upthrust':
            if ok and row['zp3'] >= row['close'] >= row['bzp3']:
                return 'open_short'
            if ok and row['bzp2'] <= row['close'] <= row['bzp4']:
                return 'open_long'

        if row['pattern18'] == 'spring':
            if ok and row['zp3'] <= row['close'] <= row['bzp3']:
                return 'open_long'
            if ok and row['bzp2'] >= row['close'] >= row['bzp4']:
                return 'open_short'

        if row['pattern18'] == 'sow':
            if ok and row['bzp3'] > row['close'] >= row['bzp2']:
                return 'open_short'

        if row['pattern18'] == 'sos':
            if ok and row['bzp3'] < row['close'] <= row['bzp2']:
                return 'open_long'

        return self.stop_loss_action(row)


class VTE2_MOONPRO(BaseTE):
    """stop=None, take=None, divider_buff=5, period_wzz=55, frac_wzz=0.1, n_wzp=6, threshold_p18=0.1, vol_period=20, min_rvol=0.8, leg_width=0.002, stop_divider=2, stop_buff=0.001, use_stop=0

    Улучшенная VTE1_MOON (авторские проблемы: «слишком рано закрывает сделки», частит).
    Изменения относительно оригинала:
    1) выключены выходы по середине ноги (close_mid_range=0, close_mid_weak=0) — позиции
       ведутся структурой, а не серединой зигзага (лечение «ранних закрытий»);
    2) входы только на переходе паттерна (pattern18 != pattern18_prev) и при
       rvol_ratio >= min_rvol — устранение дребезга (оригинал: 305 сделок);
    3) структурные стопы ssl/lsl отключены (use_stop=0): уровень на середине ноги
       зигзага мгновенно выносит вход у экстремума; контроль риска — stop/take BaseTE;
       ext-закрытия требуют 2-барного подтверждения (анти-дребезг).
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None,
                 divider_buff=5, period_wzz=55, frac_wzz=0.1, n_wzp=6, threshold_p18=0.1,
                 vol_period=20, min_rvol=0.8, leg_width=0.002, stop_divider=2, stop_buff=0.001, use_stop=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.divider_buff = divider_buff
        self.period_wzz = period_wzz
        self.frac_wzz = frac_wzz
        self.n_wzp = n_wzp
        self.threshold_p18 = threshold_p18
        self.vol_period = vol_period
        self.min_rvol = min_rvol
        self.leg_width = leg_width
        self.stop_divider = stop_divider
        self.stop_buff = stop_buff
        self.use_stop = use_stop
        self.wzp2 = f'wzp{n_wzp - 2}'
        self.wzp3 = f'wzp{n_wzp - 1}'
        self.wzp4 = f'wzp{n_wzp}'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_zigzag_window_260926(df, self.period_wzz, self.frac_wzz, self.n_wzp)
        df = add_pattern18_zzw_260926(df, self.threshold_p18)
        df['buffer'] = ((df[self.wzp2] - df[self.wzp3]) / self.divider_buff).abs()
        df['pbzp2'] = df[self.wzp2] + df['buffer']
        df['mbzp2'] = df[self.wzp2] - df['buffer']
        df['pbzp3'] = df[self.wzp3] + df['buffer']
        df['mbzp3'] = df[self.wzp3] - df['buffer']
        df['pbzp4'] = df[self.wzp4] + df['buffer']
        df['mbzp4'] = df[self.wzp4] - df['buffer']
        df['mid_wzp23'] = (df[self.wzp2] + df[self.wzp3]) / 2
        df['mid_wzp34'] = (df[self.wzp3] + df[self.wzp4]) / 2
        df = add_stop_loss_p18zzw_260926(df, self.stop_divider)
        df = add_relative_volume(df, self.vol_period)
        df['pattern18_prev'] = df['pattern18'].shift(1)
        # двухбарные подтверждения: однобарная wiggle за стопом/структурным уровнем
        # не закрывает позицию (анти-дребезг)
        df['close_prev_ssl_ok'] = (df['close'] > df['ssl'] * (1.0 + self.stop_buff)).shift(1, fill_value=False)
        df['close_prev_lsl_ok'] = (df['close'] < df['lsl'] * (1.0 - self.stop_buff)).shift(1, fill_value=False)
        df['close_prev_pbzp4_ok'] = (df['close'] <= df['pbzp4']).shift(1, fill_value=False)
        df['close_prev_mbzp4_ok'] = (df['close'] >= df['mbzp4']).shift(1, fill_value=False)
        # направление паттерна: +1 лонг-бias, -1 шорт-бias, 0 смешанные. Вход разрешён
        # только при стабильном направлении 2 бара — флэппинг не даёт реверс-входов
        pat_dir = {'joc': 1, 'sos': 1, 'btc': 1, 'bui': -1, 'bti': -1, 'sow': -1}
        df['zai_pat_dir'] = df['pattern18'].map(lambda p: pat_dir.get(p, 0))
        df['zai_pat_dir_prev'] = df['zai_pat_dir'].shift(1)
        # ширина последней ноги зигзага (wzp{n-1} -> wzp{n}): защита от мгновенных
        # закрытий на сжатой структуре (стопы/цели слишком близко к входу)
        df['zai_leg_width'] = (df[self.wzp3] - df[self.wzp4]).abs() / df['close']
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata

    def _entry_ok(self, row):
        # переход паттерна + реальный объём + достаточная ширина последней ноги зигзага
        if row['pattern18'] == row['pattern18_prev']:
            return False
        if row['rvol_ratio'] < self.min_rvol:
            return False
        if row['zai_leg_width'] < self.leg_width:
            return False
        return True

    def stop_loss_action(self, row):
        # стоп требует ДВУХ баров за уровнем (текущий + предыдущий) — анти-дребезг
        if self.use_stop:
            if row['close'] > row['ssl'] * (1.0 + self.stop_buff) and row['close_prev_ssl_ok']:
                return 'close_short'
            if row['close'] < row['lsl'] * (1.0 - self.stop_buff) and row['close_prev_lsl_ok']:
                return 'close_long'
        return None

    def _get_action_from_row(self, row):
        pattern = row['pattern18']
        close = row['close']
        ok = self._entry_ok(row)
        if pattern == 'bui':
            if ok and close >= row['mbzp2']:
                return 'open_short'
            if close <= row['pbzp4'] and row['close_prev_pbzp4_ok']:
                return 'close_short'
        if pattern == 'joc':
            if ok and close <= row['pbzp2']:
                return 'open_long'
            if close >= row['mbzp4'] and row['close_prev_mbzp4_ok']:
                return 'close_long'
        if pattern == 'weak_short':
            if ok and close >= row['mbzp3']:
                return 'open_short'
            if ok and close <= row['pbzp2']:
                return 'open_long'
        if pattern == 'weak_long':
            if ok and close <= row['pbzp3']:
                return 'open_long'
            if ok and close >= row['mbzp2']:
                return 'open_short'
        if pattern == 'narrowing_up':
            if ok and close >= row['mbzp3']:
                return 'open_short'
            if ok and close <= row['mid_wzp23']:
                return 'open_long'
        if pattern == 'narrowing_down':
            if ok and close <= row['pbzp3']:
                return 'open_long'
            if ok and close >= row['mid_wzp23']:
                return 'open_short'
        if pattern == 'bottom_range' or pattern == 'double_top' or pattern == 'upthrust':
            if ok and close >= row['mbzp3']:
                return 'open_short'
            if ok and close <= row['pbzp2']:
                return 'open_long'
        if pattern == 'top_range' or pattern == 'double_bottom' or pattern == 'spring':
            if ok and close <= row['pbzp3']:
                return 'open_long'
            if ok and close >= row['mbzp2']:
                return 'open_short'
        if pattern == 'sow':
            if ok and close >= row['mid_wzp34']:
                return 'open_short'
            if close <= row['pbzp4'] and row['close_prev_pbzp4_ok']:
                return 'close_short'
        if pattern == 'sos':
            if ok and close <= row['mid_wzp34']:
                return 'open_long'
            if close >= row['mbzp4'] and row['close_prev_mbzp4_ok']:
                return 'close_long'
        if pattern == 'bti':
            if ok and close >= row['mid_wzp23']:
                return 'open_short'
        if pattern == 'btc':
            if ok and close <= row['mid_wzp23']:
                return 'open_long'
        return self.stop_loss_action(row)
