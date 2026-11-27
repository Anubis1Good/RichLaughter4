from strategies.BaseTE import BaseTE
from for_strategies.classic_indicators import add_fractals,add_rsi,add_adx,add_bollinger
from for_strategies.pva_indicators import add_average_fractals,add_plus_delta_fc,add_exp_pdfc,add_ext_on_fractals,add_mean_on_fractals,add_average_fractals_window,add_exp_pdfc_window,add_plus_delta_fc_window,add_vodka_channel
from for_strategies.pva2_indicators import add_per_above_sma
from for_strategies.zigzag_indicators import add_percent_zz190826,add_dzz_peaks,add_analys_dzz,add_percent_zz_peaks,add_pattern18_dzz_czd,add_stop_loss_p18czd,add_exp_plusdelta_dzz_peaks,add_mean_dzz_peaks,add_plusdelta_dzz_peaks,add_zigzag180826,add_shift_zz_peaks,add_analys_dzz180826, add_zigzag_window_210926,add_pattern18_zzw_210926,add_zigzag_window_260926,add_mean_peaks_wzz260926, add_plusdelta_peaks_wzz260926,add_exp_plusdelta_peaks_wzz260926,add_mean_ind_wzz_peaks,add_extreme_ind_wzz_peaks,add_pattern18_zzw_260926,add_drop_last_wzp
from for_strategies.help_indicators import add_buffer_add
from for_strategies.fix_params import fix_supertrend_params,fix_two_periods_hm,fix_three_periods_hm

# 14.10.2026 может зайти на локальном лое в шорт в лонговом тренде
# 27.10.2026 нужна версия, с локальным подстраивание периода sma под волатильность
class UTE6_SURVIVALIST(BaseTE):
    """stop=None, take=None, period_bb=55, period_smas=2, mult_bb=1, use_stop=0,div_buff=2,period_rsi=30,thresh_rsi=30,use_rsi=0
    \n
    UTE6_ADVENTURE с буфером и rsi
    """
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_bb=55, period_smas=2, mult_bb=1, use_stop=0,div_buff=2,period_rsi=30,thresh_rsi=30,use_rsi=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_bb = period_bb
        self.period_smas = period_smas
        self.mult_bb = mult_bb
        self.use_stop = use_stop
        self.div_buff = div_buff
        self.period_rsi = period_rsi
        self.thresh_rsi = thresh_rsi
        self.use_rsi = use_rsi

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_bollinger(df, self.period_bb, multiplier=self.mult_bb)
        df['high_sma'] = df['high'].rolling(self.period_smas).mean()
        df['low_sma'] = df['low'].rolling(self.period_smas).mean()
        df = add_buffer_add(df, 'high_sma', 'low_sma', self.div_buff)
        df = add_rsi(df,self.period_rsi)
        df['can_long'] = df['rsi'] < self.thresh_rsi if self.use_rsi else True        
        df['can_short'] = df['rsi'] > 100 - self.thresh_rsi if self.use_rsi else True        
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['high'] < row['bbu'] and row['low'] > row['bbd']:
            if row['close'] >= row['top_buff'] and row['can_short']:
                return 'open_short'
            if row['close'] <= row['bottom_buff'] and row['can_long']:
                return 'open_long'
        else:
            if row['low'] > row['bbu']:  # long
                if row['close'] <= row['bottom_buff'] and row['can_long']:
                    return 'open_long'
                if row['close'] >= row['top_buff']:
                    return 'close_long'
                if self.use_stop:
                    return 'close_short'
            if row['high'] < row['bbd']:  # short
                if row['close'] >= row['top_buff'] and row['can_short']:
                    return 'open_short'
                if row['close'] <= row['bottom_buff']:
                    return 'close_short'
                if self.use_stop:
                    return 'close_long'
        

# Нужна версия вариантом с использования rsi на каждом паттерне
# 06.10.2026 ограничения оптимизации привели к тому, что сделок как-будто как-то очень мало
# 07.10.2026 открыл лонг в хаях     'SIBN':(UTE8_SOLDIER,(None,20,18,21,40,0.57,4,0.76,24,0,92,2,2,97,75,19,79,43),2,None),
# 07.10.2026 почему-то открывал вообще не правильные сделки. Все наоборот 'IRAO':(UTE8_SOLDIER,(None,30,18,57,48,0.95,10,0.72,30,0,73,21,69,0,90,82,73,95),3,None),
# 09.10.2026 надо сделать версию только для боковика
# 14.10.2026 целый день тянул контренд. В итоге закрыл -4.81%
# 20.10.2026 открыл хорошо, но почему-то не закрыл почти процент и в итоге закрыл минус
# 21.10.2026 возможно стоит попробовать объединить с дюной
# 21.10.2026 специально блокировать действия при joc. Успешный пример:     'ENPG':(UTE8_SOLDIER,(None,None,13,35,36,0.7,8,0.64,31,0,  26,51,87,75,94,73,55,90),1,None), получает он на joc только закрывал позицию, а на sos открывал только по тренду
# 21.10.2026 попробовать сделать на расширение. Помнять точки 'pbzp3' -> 'mbzp3'
class UTE8_SOLDIER(BaseTE):
    """stop=None, take=None, \n
    divider_buff=5, period_rsi=14, period_wzz=30, frac_wzz=0.1, n_wzp=6, threshold_p18=0.1, threshold_rsi=30, use_rsi=0, g_joc=99,g_tr=99,g_dt=99,g_wl=99,g_nd=99,g_s=99,g_sos=99,g_bti=99
    \n
    0-2 - ничего,
    3-6 - противоположную,
    7-9 - все"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, divider_buff=5, period_rsi=14, period_wzz=30, frac_wzz=0.1, n_wzp=6, threshold_p18=0.1, threshold_rsi=30, use_rsi=0, g_joc=99,g_tr=99,g_dt=99,g_wl=99,g_nd=99,g_s=99,g_sos=99,g_bti=99):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.divider_buff = divider_buff
        self.period_rsi = period_rsi
        self.period_wzz = period_wzz
        self.frac_wzz = frac_wzz
        self.n_wzp = n_wzp
        self.threshold_p18 = threshold_p18
        self.g_joc = g_joc
        self.g_tr = g_tr
        self.g_dt = g_dt
        self.g_wl = g_wl
        self.g_nd = g_nd
        self.g_s = g_s
        self.g_sos = g_sos
        self.g_bti = g_bti
        self.use_rsi=use_rsi
        self.threshold_rsi=threshold_rsi
        self.wzp2 = f'wzp{n_wzp - 2}'
        self.wzp3 = f'wzp{n_wzp - 1}'
        self.long_group = ('bti', 'joc', 'top_range', 'double_top', 'weak_long', 'narrowing_down', 'spring', 'sos')
        self.short_group = ('btc', 'bui', 'bottom_range', 'double_bottom', 'weak_short', 'narrowing_up', 'upthrust', 'sow')

    def get_group(self,pattern):
        if pattern == 'joc' or pattern == 'bui':
            return self.g_joc
        if pattern == 'top_range' or pattern == 'bottom_range':
            return self.g_tr
        if pattern == 'double_top' or pattern == 'double_bottom':
            return self.g_dt
        if pattern == 'weak_long' or pattern == 'weak_short':
            return self.g_wl
        if pattern == 'narrowing_down' or pattern == 'narrowing_up':
            return self.g_nd
        if pattern == 'spring' or pattern == 'upthrust':
            return self.g_s
        if pattern == 'sos' or pattern == 'sow':
            return self.g_sos
        if pattern == 'bti' or pattern == 'btc':
            return self.g_bti
        return 0

    def get_action_by_group(self,pattern,can):
        group = self.get_group(pattern)
        od = group // 10
        cd = group % 10
        if can == 'long':
            if od > 6:
                return 'open_long'
            if od > 2 and pattern in self.long_group:
                return 'open_long'
            if cd > 2:
                return 'close_short'  
        else:
            if od > 6:
                return 'open_short'
            if od > 2 and pattern in self.short_group:
                return 'open_short'
            if cd > 2:
                return 'close_long'

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_rsi(df,self.period_rsi)
        df = add_zigzag_window_260926(df,self.period_wzz,self.frac_wzz,self.n_wzp)
        df = add_pattern18_zzw_260926(df,self.threshold_p18)
        df['buffer'] = ((df[self.wzp2] - df[self.wzp3]) / self.divider_buff).abs()
        df['pbzp2'] = df[self.wzp2] + df['buffer']
        df['mbzp2'] = df[self.wzp2] - df['buffer']
        df['pbzp3'] = df[self.wzp3] + df['buffer']
        df['mbzp3'] = df[self.wzp3] - df['buffer']
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        can_long, can_short = None, None
        if row['pattern18'] in self.long_group:
            can_long = row['pbzp3'] >= row['close']
            can_short = row['mbzp2'] <= row['close']
        
        if row['pattern18'] in self.short_group:
            can_short = row['close'] >= row['mbzp3']
            can_long = row['close'] <= row['pbzp2']
        if self.use_rsi:
            rsi = row['rsi']
            oversold = rsi <= self.threshold_rsi
            overbought = rsi >= 100 - self.threshold_rsi
            can_short = can_short and overbought
            can_long = can_long and oversold
        if can_long:
            return self.get_action_by_group(row['pattern18'],'long')
        if can_short:
            return self.get_action_by_group(row['pattern18'],'short')
        

# В боковике ахуенно работает. Надо подумать над версией, которая включается, только в боковике
# 05.10.2026 нужна версия с отдельной работой для боковика и тренда
# 07.10.2026 нужна версия без входа в канале (без top_stop and bottom_stop)
# 14.10.2026 тоже бывает открывает прям в хае сделки
class UTE9_GRAVY2(BaseTE):
    '''
    stop=None, take=None, period_wzz=55, frac_wzz=0.1, n_wzp=8, buffer_mean=0.1, mult_stop=0.5, use_stop=1
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_wzz=55, frac_wzz=0.1, n_wzp=8, buffer_mean=0.1, mult_stop=0.5, use_stop=0):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_wzz = period_wzz
        self.frac_wzz = frac_wzz
        self.n_wzp = n_wzp
        self.buffer_mean = buffer_mean
        self.mult_stop = mult_stop
        self.use_stop = use_stop

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_zigzag_window_260926(df,self.period_wzz,self.frac_wzz,self.n_wzp)
        df = add_mean_peaks_wzz260926(df,self.buffer_mean)
        df['top_stop'] = df['top_mean'] + df['delta_mean'] * self.mult_stop
        df['bottom_stop'] = df['bottom_mean'] - df['delta_mean'] * self.mult_stop
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['top_stop'] > row['close'] >= row['top_mean']:
            return 'open_short'
        if row['bottom_stop'] < row['close'] <= row['bottom_mean']:
            return 'open_long'
        if self.use_stop:
            if row['close'] > row['top_stop']:
                return 'close_short'
            if row['close'] < row['bottom_stop']:
                return 'close_long'

# 12.10.2026 Надо подумать над тем, что бы в тренде скользящие были ближе. Может два периода для тренда и боковика
# 21.10.2026 добавить версию, которая может закрывать сделки в случает запрета одной из сторон!
# 25.10.2026 возможно стоит классифицировать паттерны и отбирать те, на которых можно заходить и те, на которых нельзя
# 27.10.2026 какие-то частые входы прям в хаях. Надо это править!
class UTE9_POLITICIAN(BaseTE):
    '''
    stop=None, take=None, period_wzz=55, frac_wzz=0.1, n_wzp=8, buffer_mean=0.1,use_rsi=0,period_rsi=30,thresh_rsi=30
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_wzz=55, frac_wzz=0.1, n_wzp=8, buffer_mean=0.1,use_rsi=0,period_rsi=30,thresh_rsi=30):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_wzz = period_wzz
        self.frac_wzz = frac_wzz
        self.n_wzp = n_wzp
        self.buffer_mean = buffer_mean
        self.use_rsi = use_rsi
        self.period_rsi = period_rsi
        self.thresh_rsi = thresh_rsi

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_zigzag_window_260926(df,self.period_wzz,self.frac_wzz,self.n_wzp)
        df = add_mean_peaks_wzz260926(df,self.buffer_mean)
        if self.use_rsi:
            df = add_rsi(df,self.period_rsi)
            df['can_long'] = df['rsi'] <= self.thresh_rsi
            df['can_short'] = df['rsi'] >= 100 - self.thresh_rsi
        else:
            df['can_long'] = True
            df['can_short'] = True
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['close'] >= row['top_mean'] and row['can_short']:
            return 'open_short'
        if row['close'] <= row['bottom_mean'] and row['can_long']:
            return 'open_long'
        
class UTE9_ASTRAL(BaseTE):
    '''
    stop=None, take=None, period_vc=10, divider=1,allowance=0.1
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_vc=10, divider=1,allowance=0.1):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_vc = period_vc
        self.divider = divider
        self.allowance = allowance

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_vodka_channel(df,self.period_vc)
        df = add_buffer_add(df, 'top_mean', 'bottom_mean', self.divider)
        df['mean_diff_percent'] = ((df['top_mean'] - df['bottom_mean']) / df['bottom_mean']) * 100
        df['allowance'] = df['mean_diff_percent'] > self.allowance
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['allowance']:
            if row['close'] >= row['top_buff']:
                return 'open_short'
            if row['close'] <= row['bottom_buff']:
                return 'open_long'
            
class UTE9_MEDIUM(BaseTE):
    '''
    stop=None, take=None, period_vc=10, divider=1,allowance=0.1,period_pas1=10,period_pas2=60,max_period=70,pas_thresh=20
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_vc=10, divider=1,allowance=0.1,period_pas1=10,period_pas2=60,max_period=70,pas_thresh=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_vc = period_vc
        self.period_pas1, self.period_pas2 = fix_two_periods_hm(period_pas1,period_pas2,max_period)
        self.divider = divider
        self.allowance = allowance
        self.pas_thresh = pas_thresh

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_per_above_sma(df,self.period_pas1, self.period_pas2)
        df = add_vodka_channel(df,self.period_vc)
        df = add_buffer_add(df, 'top_mean', 'bottom_mean', self.divider)
        df['mean_diff_percent'] = ((df['top_mean'] - df['bottom_mean']) / df['bottom_mean']) * 100
        df['allowance'] = df['mean_diff_percent'] > self.allowance
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['allowance']:
            if row['pas'] >= 100-self.pas_thresh or row['pas'] <= self.pas_thresh:
                top = 'top_buff' 
                bottom = 'bottom_buff' 
            else:
                top = 'top_mean' 
                bottom = 'bottom_mean' 
            if row['close'] >= row[top]:
                return 'open_short'
            if row['close'] <= row[bottom]:
                return 'open_long'
    
class UTE9_TRACKER(BaseTE):
    '''
    stop=None, take=None, period_vc=10, divider=1,allowance=0.1,period_pas1=10,period_pas2=60,max_period=70,pas_thresh=20
    '''
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period_vc=10, divider=1,allowance=0.1,period_pas1=10,period_pas2=60,max_period=70,pas_thresh=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period_vc = period_vc
        self.period_pas1, self.period_pas2 = fix_two_periods_hm(period_pas1,period_pas2,max_period)
        self.divider = divider
        self.allowance = allowance
        self.pas_thresh = pas_thresh

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_per_above_sma(df,self.period_pas1, self.period_pas2)
        df = add_vodka_channel(df,self.period_vc)
        df = add_buffer_add(df, 'top_mean', 'bottom_mean', self.divider)
        df['mean_diff_percent'] = ((df['top_mean'] - df['bottom_mean']) / df['bottom_mean']) * 100
        df['allowance'] = df['mean_diff_percent'] > self.allowance
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['allowance']:
            can_long = True
            can_short = True
            if row['pas'] >= 100-self.pas_thresh:
                can_short = False
            if row['pas'] <= self.pas_thresh:
                can_long = False

            if row['close'] >= row['top_buff']:
                if can_short:
                    return 'open_short'
                else:
                    return 'close_long'
            if row['close'] <= row['bottom_buff']:
                if can_long:
                    return 'open_long'
                else:
                    return 'close_short'
    

        
