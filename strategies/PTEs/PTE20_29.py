from strategies.BaseTE import BaseTE
from for_strategies.classic_indicators import add_bollinger,add_rsi,add_donchan_channel,add_fractals,add_chop,add_adx,add_sma
from for_strategies.pva_indicators import add_mean_on_fractals,add_ext_on_fractals,add_smooth_channel,add_integrity_index,add_stable_ma_direction
from for_strategies.zigzag_indicators import add_dzz_peaks,add_analys_dzz,add_percent_zz_peaks,add_pattern18_dzz_czd,add_stop_loss_p18czd, add_analys_dzz180826, add_zigzag180826, add_shift_zz_peaks,add_percent_zz190826
from for_strategies.fix_params import fix_supertrend_params,fix_two_periods_hm,fix_three_periods_hm

# Попробовать написать версию на add_percent_zz190826
class PTE21_WHITEMANE(BaseTE):
    '''
    stop=None, take=None, period=20, period_rsi=20, period_fractal=10, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, use_stop=0, period_zz=20
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, period_rsi=20, period_fractal=10, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, use_stop=0, period_zz=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.period_rsi = period_rsi
        self.period_sma = period_sma
        self.period_zz = period_zz
        self.n_std = n_std
        self.threshold_trend = threshold_trend
        self.use_stop = use_stop
        self.problems = 'Mcfly_FixVanga'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period)
        df = add_rsi(df, self.period_rsi)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_zigzag180826(df, n_std=self.n_std,period=self.period_zz)
        df = add_shift_zz_peaks(df)
        df = add_analys_dzz180826(df, self.period_sma)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['low'] <= row['min_hb'] and row['oversold']:
            if row['trend_sma'] >= -self.threshold_trend:
                return 'open_long'
            else:
                return 'close_short'
        
        if row['high'] >= row['max_hb'] and row['overbought']:
            if row['trend_sma'] <= self.threshold_trend:
                return 'open_short'
            else:
                return 'close_long'
        
        if self.use_stop:
            if row['trend_sma'] < -0.8:
                return 'close_long'
            if row['trend_sma'] > 0.8:
                return 'close_short'
        
        return None

# Попробовать написать версию на add_percent_zz190826
class PTE21_AURIEL(BaseTE):
    '''
    stop=None, take=None, period=20, period_fractal=10, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, period_zz=20
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, period_fractal=10, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, period_zz=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.period_sma = period_sma
        self.period_zz = period_zz
        self.n_std = n_std
        self.threshold_trend = threshold_trend
        self.problems = 'Mcfly_FixVanga'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_rsi(df, self.period)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_zigzag180826(df, n_std=self.n_std,period=self.period_zz)
        df = add_shift_zz_peaks(df)
        df = add_analys_dzz180826(df, self.period_sma)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['oversold']:
            if row['trend_sma'] >= -self.threshold_trend:
                return 'open_long'
            else:
                return 'close_short'
        
        if row['overbought']:
            if row['trend_sma'] <= self.threshold_trend:
                return 'open_short'
            else:
                return 'close_long'
        
        return None

class PTE21_MALTHAEL(BaseTE):
    '''
    stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.5, use_stop=0
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.5, use_stop=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.percent_threshold = percent_threshold
        self.use_stop = use_stop
        self.problems = 'Mcfly'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_rsi(df, self.period)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_percent_zz190826(df, percent_threshold=self.percent_threshold,drop_last=False)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['oversold']:
            if row['zigzag_direction'] == 1:
                return 'open_long'
            elif self.use_stop:
                return 'close_all'
            else:
                return 'close_short'
        
        if row['overbought']:
            if row['zigzag_direction'] == -1:
                return 'open_short'
            elif self.use_stop:
                return 'close_all'
            else:
                return 'close_long'
        
        if self.use_stop:
            if row['zigzag_direction'] == 1:
                return 'close_short'
            if row['zigzag_direction'] == -1:
                return 'close_long'
        
        return None

# Попробовать написать версию на add_percent_zz190826
class PTE22_BERSERK(BaseTE):
    """stop=None, take=None, period_adx=27, period_fractal=10, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, period2=55, period3=20, threshold_chop=60, threshold_adx=30, period_zz=20"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_adx=27, period_fractal=10, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, period2=55, period3=20, threshold_chop=60, threshold_adx=30, period_zz=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_adx = period_adx
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.period_sma = period_sma
        self.n_std = n_std
        self.threshold_trend = threshold_trend
        self.threshold_chop = threshold_chop
        self.threshold_adx = threshold_adx
        self.period2 = period2
        self.period3 = period3
        self.period_zz = period_zz
        self.problems = 'Mcfly_FixVanga'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period3)
        df = add_rsi(df, self.period3)
        df = add_chop(df, self.period2)
        df = add_adx(df, self.period_adx)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_zigzag180826(df, n_std=self.n_std,period=self.period_zz)
        df = add_shift_zz_peaks(df)
        df = add_analys_dzz180826(df, self.period_sma)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        ranger = row['chop'] > self.threshold_chop and row['adx'] < self.threshold_adx
        
        if ranger:
            if row['low'] <= row['min_hb'] and row['oversold']:
                return 'open_long'
            if row['high'] >= row['max_hb'] and row['overbought']:
                return 'open_short'
        else:
            if row['oversold']:
                if row['trend_sma'] >= -self.threshold_trend:
                    return 'open_long'
                else:
                    return 'close_short'
            if row['overbought']:
                if row['trend_sma'] <= self.threshold_trend:
                    return 'open_short'
                else:
                    return 'close_long'
        
        return None

# Если Соня будет лучше чем Берсерк, то нужно будет сделать вариации 21 и 23 с add_percent_zz190826
class PTE22_SONYA(BaseTE):
    """stop=None, take=None, period_adx=27, period_fractal=10, period_max=55, period_sma=3, threshold_trend=0.5, period2=55, period3=20, threshold_chop=60, threshold_adx=30, percent_threshold=0.5"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_adx=27, period_fractal=10, period_max=55, period_sma=3, threshold_trend=0.5, period2=55, period3=20, threshold_chop=60, threshold_adx=30, percent_threshold=0.5):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_adx = period_adx
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.period_sma = period_sma
        self.percent_threshold = percent_threshold
        self.threshold_trend = threshold_trend
        self.threshold_chop = threshold_chop
        self.threshold_adx = threshold_adx
        self.period2 = period2
        self.period3 = period3
        self.problems = 'Mcfly'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period3)
        df = add_rsi(df, self.period3)
        df = add_chop(df, self.period2)
        df = add_adx(df, self.period_adx)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_percent_zz190826(df, percent_threshold=self.percent_threshold,drop_last=False)
        df = add_analys_dzz(df, self.period_sma)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        ranger = row['chop'] > self.threshold_chop and row['adx'] < self.threshold_adx
        
        if ranger:
            if row['low'] <= row['min_hb'] and row['oversold']:
                return 'open_long'
            if row['high'] >= row['max_hb'] and row['overbought']:
                return 'open_short'
        else:
            if row['oversold']:
                if row['trend_sma'] >= -self.threshold_trend:
                    return 'open_long'
                else:
                    return 'close_short'
            if row['overbought']:
                if row['trend_sma'] <= self.threshold_trend:
                    return 'open_short'
                else:
                    return 'close_long'
        
        return None

class PTE23_ULTIMATUM(BaseTE):
    """stop=None, take=None, period_dc=20, period_sdc=20, period_rsi=20, period_fractal=10, type_treshold=0, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, allowance=0.1, use_stop=0, period_zz=20"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_dc=20, period_sdc=20, period_rsi=20, period_fractal=10, type_treshold=0, period_max=55, n_std=1.5, period_sma=3, threshold_trend=0.5, allowance=0.1, use_stop=0, period_zz=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_fractal = period_fractal
        self.type_treshold = type_treshold
        self.period_max = period_max
        self.period_sma = period_sma
        self.n_std = n_std
        self.threshold_trend = threshold_trend
        self.period_rsi = period_rsi
        self.allowance = allowance
        self.use_stop = use_stop
        max_total = (period_max // 3) * 2
        total = period_dc + period_sdc

        if total > max_total:
            ratio = max_total / total
            self.period_dc = int(period_dc * ratio)
            self.period_sdc = int(period_sdc * ratio)
        else:
            self.period_dc = period_dc
            self.period_sdc = period_sdc
        self.period_zz = period_zz
        self.problems = 'Mcfly_FixVanga'

    def add_threshold(self, df):
        if self.type_treshold == 0:
            df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
            df['oversold'] = df['rsi'] < df['bottom_mean']
            df['overbought'] = df['rsi'] > df['top_mean']
        else:
            df = add_ext_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
            df['oversold'] = df['rsi'] < df['bottom_ext']
            df['overbought'] = df['rsi'] > df['top_ext']
        return df

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period_dc)
        df = add_smooth_channel(df, self.period_sdc)
        df['dc_diff_percent'] = ((df["max_hb"] - df["min_hb"]) / df["min_hb"]) * 100
        df['allowance'] = df['dc_diff_percent'] > self.allowance
        df = add_rsi(df, self.period_rsi)
        df = add_fractals(df, self.period_fractal)
        df = self.add_threshold(df)
        df = add_zigzag180826(df, n_std=self.n_std,period=self.period_zz)
        df = add_shift_zz_peaks(df)
        df = add_analys_dzz180826(df, self.period_sma)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['allowance']:
            if row['low'] <= row['min_hb'] and row['oversold']:
                if row['trend_sma'] >= -self.threshold_trend:
                    return 'open_long'
                else:
                    return 'close_short'
            if row['high'] >= row['max_hb'] and row['overbought']:
                if row['trend_sma'] <= self.threshold_trend:
                    return 'open_short'
                else:
                    return 'close_long'
        
        if self.use_stop:
            if row['trend_sma'] < -0.8:
                return 'close_long'
            if row['trend_sma'] > 0.8:
                return 'close_short'
        
        return None

class PTE24_BRIGHTWING(BaseTE):
    '''
    stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.2, threshold_dzz=0.2, buff=0.1, divider=2, use_stop=1
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.2, threshold_dzz=0.2, buff=0.1, divider=2, use_stop=1):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.percent_threshold = percent_threshold
        self.threshold_dzz = threshold_dzz
        self.buff = buff
        self.divider = divider
        self.use_stop = use_stop
        self.problems = 'Mcfly'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_rsi(df, self.period)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_percent_zz190826(df, percent_threshold=self.percent_threshold)
        df['zigzag_peaks'] = df['zigzag_peaks'].shift(1)
        df = add_pattern18_dzz_czd(df, self.threshold_dzz, self.buff)
        df = add_stop_loss_p18czd(df, self.divider)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['oversold']:
            if row['pattern18'] in ('btc', 'bui', 'bottom_range', 'double_bottom', 'weak_short', 'narrowing_up', 'upthrust', 'sow'):
                return 'open_long'
            elif self.use_stop and row['close'] < row['lsl']:
                return 'close_all'
            else:
                return 'close_short'
        
        if row['overbought']:
            if row['pattern18'] in ('bti', 'joc', 'top_range', 'double_top', 'weak_long', 'narrowing_down', 'spring', 'sos'):
                return 'open_short'
            elif self.use_stop and row['close'] < row['ssl']:
                return 'close_all'
            else:
                return 'close_long'
        
        if self.use_stop:
            if row['close'] > row['ssl']:
                return 'close_short'
            if row['close'] < row['lsl']:
                return 'close_long'
        
        return None

class PTE24_DEATHWING(BaseTE):
    '''
    stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.2, threshold_dzz=0.2, buff=0.1, divider=2, use_stop=1
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.2, threshold_dzz=0.2, buff=0.1, divider=2, use_stop=1):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.percent_threshold = percent_threshold
        self.threshold_dzz = threshold_dzz
        self.buff = buff
        self.divider = divider
        self.use_stop = use_stop
        self.problems = 'Mcfly'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_rsi(df, self.period)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df = add_percent_zz190826(df, percent_threshold=self.percent_threshold)
        df['zigzag_peaks'] = df['zigzag_peaks'].shift(1)
        df = add_pattern18_dzz_czd(df, self.threshold_dzz, self.buff)
        df = add_stop_loss_p18czd(df, self.divider)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['oversold']:
            if row['pattern18'] in ('bti', 'joc', 'top_range', 'double_top', 'weak_long', 'narrowing_down', 'spring', 'sos'):
                return 'open_long'
            elif self.use_stop and row['close'] < row['lsl']:
                return 'close_all'
            else:
                return 'close_short'
        
        if row['overbought']:
            if row['pattern18'] in ('btc', 'bui', 'bottom_range', 'double_bottom', 'weak_short', 'narrowing_up', 'upthrust', 'sow'):
                return 'open_short'
            elif self.use_stop and row['close'] < row['ssl']:
                return 'close_all'
            else:
                return 'close_long'
        
        if self.use_stop:
            if row['close'] > row['ssl']:
                return 'close_short'
            if row['close'] < row['lsl']:
                return 'close_long'
        
        return None

class PTE25_TASSADAR(BaseTE):
    '''
    stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.2, threshold_dzz=0.2, buff=0.1, divider=2, threshold_over=10, use_stop=0
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, period_fractal=10, period_max=55, percent_threshold=0.2, threshold_dzz=0.2, buff=0.1, divider=2, threshold_over=10, use_stop=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.period_fractal = period_fractal
        self.period_max = period_max
        self.threshold_over = threshold_over
        self.percent_threshold = percent_threshold
        self.threshold_dzz = threshold_dzz
        self.buff = buff
        self.divider = divider
        self.use_stop = use_stop
        self.problems = 'Mcfly'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_rsi(df, self.period)
        df = add_fractals(df, self.period_fractal)
        df = add_mean_on_fractals(df, self.period_max, 'rsi',self.period_fractal)
        df['oversold'] = df['rsi'] < df['bottom_mean']
        df['overbought'] = df['rsi'] > df['top_mean']
        df['overlimit'] = (df['top_mean'] - df['bottom_mean']) > self.threshold_over
        df = add_percent_zz190826(df, percent_threshold=self.percent_threshold)
        df['zigzag_peaks'] = df['zigzag_peaks'].shift(1)
        df = add_pattern18_dzz_czd(df, self.threshold_dzz, self.buff)
        df = add_stop_loss_p18czd(df, self.divider)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        can_long, can_short = None, None
        
        if row['pattern18'] in ('bti', 'joc', 'top_range', 'double_top', 'weak_long', 'narrowing_down', 'spring', 'sos'):
            can_long = row['close'] >= row['zp3']
            can_short = row['close'] <= row['zp2']
        
        if row['pattern18'] in ('btc', 'bui', 'bottom_range', 'double_bottom', 'weak_short', 'narrowing_up', 'upthrust', 'sow'):
            can_long = row['close'] >= row['zp2']
            can_short = row['close'] <= row['zp3']
        
        if row['oversold'] and row['overlimit']:
            if can_long:
                return 'open_long'
            elif self.use_stop and row['close'] < row['lsl']:
                return 'close_all'
            else:
                return 'close_short'
        
        if row['overbought'] and row['overlimit']:
            if can_short:
                return 'open_short'
            elif self.use_stop and row['close'] < row['ssl']:
                return 'close_all'
            else:
                return 'close_long'
        
        if self.use_stop:
            if row['close'] > row['ssl']:
                return 'close_short'
            if row['close'] < row['lsl']:
                return 'close_long'
        
        return None
            
class PTE26_UNKNOWN(BaseTE):
    """stop=None, take=None, period_sma=55, period_rsi=10, threshold=30, threshold_ii=25,period_smad=55,period_dc=10,period_ii=20,max_period=55,use_stop=0"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_sma=55, period_rsi=10, threshold=30, threshold_ii=25,period_smad=55,period_dc=10,period_ii=20,max_period=55,use_stop=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_rsi = period_rsi
        self.period_dc = period_dc
        self.period_ii = period_ii
        self.threshold = threshold
        self.threshold_ii = threshold_ii
        self.use_stop = use_stop
        self.period_sma, self.period_smad = fix_two_periods_hm(period_sma,period_smad,max_period)
        self.problems = 'Mcfly'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_sma(df, self.period_sma)
        df = add_stable_ma_direction(df, self.period_smad, 'sma')
        df = add_donchan_channel(df, self.period_dc)
        df = add_rsi(df, self.period_rsi)
        df = add_integrity_index(df, self.period_ii)
        df['nl'] = df['high'] - df['close'] > df['close'] - df['low']
        df['can_long'] = df['dir_ma'] > 0
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        
        if row['nl'] and row['can_long']:
            if row['close'] <= row['avarege'] and row['ii'] > self.threshold_ii:
                return 'open_long'
            if row['low'] <= row['min_hb']:
                return 'open_long'
        
        if not row['nl'] and not row['can_long']:
            if row['close'] >= row['avarege'] and row['ii'] < -self.threshold_ii:
                return 'open_short'
            if row['high'] >= row['max_hb']:
                return 'open_short'
        
        if row['nl'] and row['rsi'] < self.threshold and row['low'] <= row['min_hb']:
            return 'close_short'
        
        if not row['nl'] and row['rsi'] > 100 - self.threshold and row['high'] >= row['max_hb']:
            return 'close_long'
        
        if self.use_stop:
            if row['can_long']:
                return 'close_short'
            else:
                return 'close_long'
            
class PTE26_JUNKRAT(BaseTE):
    """stop=None, take=None, period_rsi=10, threshold_rsi=30, threshold_ii=25,period_dc=10,period_ii=10,allowance=0.1"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_rsi=10, threshold_rsi=30, threshold_ii=25,period_dc=10,period_ii=10,allowance=0.1):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_rsi = period_rsi
        self.period_dc = period_dc
        self.period_ii = period_ii
        self.threshold_rsi = threshold_rsi
        self.threshold_ii = threshold_ii
        self.allowance = allowance

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period_dc)
        df = add_rsi(df, self.period_rsi)
        df = add_integrity_index(df, self.period_ii)
        df['nl'] = df['high'] - df['close'] > df['close'] - df['low']
        df['dc_diff_per'] = ((df['max_hb'] - df['min_hb']) / df['min_hb']) * 100
        df['allowance'] = df['dc_diff_per'] > self.allowance
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['allowance']:
            if row['ii'] < self.threshold_ii or row['ii'] > 100 - self.threshold_ii:
                if row['nl'] and  row['low'] <= row['min_hb']:
                    return 'open_long'
                if not row['nl'] and row['high'] >= row['max_hb']:
                    return 'open_short'
            else:
                if row['nl'] and row['rsi'] < self.threshold_rsi and row['low'] <= row['min_hb']:
                    return 'open_long'
                if not row['nl'] and row['rsi'] > 100 - self.threshold_rsi and row['high'] >= row['max_hb']:
                    return 'open_short'
             
class PTE26_GAZLOWE(BaseTE):
    """stop=None, take=None, period_rsi=10, threshold_rsi=30, threshold_ii=10,period_dc=10,period_ii=20,sleep_thresh_ii=5,use_trend=0"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_rsi=10, threshold_rsi=30, threshold_ii=10,period_dc=10,period_ii=20,sleep_thresh_ii=5,use_trend=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_rsi = period_rsi
        self.period_dc = period_dc
        self.period_ii = period_ii
        self.threshold_rsi = threshold_rsi
        self.threshold_ii = threshold_ii
        self.sleep_thresh_ii = sleep_thresh_ii
        self.use_trend = use_trend

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period_dc)
        df = add_rsi(df, self.period_rsi)
        df = add_integrity_index(df, self.period_ii)
        df['nl'] = df['high'] - df['close'] > df['close'] - df['low']
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['ii'] < self.threshold_ii:
            if self.use_trend == 0:
                return
            if self.use_trend == 1:
                return 'open_long'
            if self.use_trend == 2:
                return 'open_short'
        elif row['ii'] > 100 - self.threshold_ii:
            if self.use_trend == 0:
                return
            if self.use_trend == 1:
                return 'open_short'
            if self.use_trend == 2:
                return 'open_long'
        elif row['ii'] < 100 - (self.threshold_ii+self.sleep_thresh_ii) and row['ii'] > self.threshold_ii + self.sleep_thresh_ii:
            if row['nl'] and row['rsi'] < self.threshold_rsi and row['low'] <= row['min_hb']:
                return 'open_long'
            if not row['nl'] and row['rsi'] > 100 - self.threshold_rsi and row['high'] >= row['max_hb']:
                return 'open_short'

