from strategies.BaseTE import BaseTE
from for_strategies.classic_indicators import add_bollinger,add_adx,add_sma,add_rsi,add_ema
from for_strategies.zigzag_indicators import add_percent_zz190826
from for_strategies.help_indicators import add_big_volume,add_over_bb
from for_strategies.pva_indicators import add_simple_dynamics_ma,add_pc_stair_fast

# подумать над вариацией STE со способностью тянуть сделку дольше (может, до противоположной сделки)
# (STE1_LITE,(None,108,70,0.7,0.7,57),9,None) #add_simple_dynamics_ma из-за этого не было сделок в оконном тесте
# 02.10.2026 нужно заменить add_simple_dynamics_ma на оконный аналог и упросить выход из сделки
class STE1_LITE(BaseTE):
    """stop=None, take=None, period=20, multiplier=2, slope=0.5, period2=10"""
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None, period=20, multiplier=2, slope=0.5, period2=10):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}
        self.period = period
        self.multiplier = multiplier
        self.slope = slope
        self.period2 = period2

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_sma(df, self.period2)
        df = df.rename(columns={'sma': 'sma2'})
        df = add_bollinger(df, self.period, multiplier=self.multiplier)
        df = add_big_volume(df, self.period)
        df = add_over_bb(df)
        sdm_period = max(3, self.period2 // 3)
        df = add_simple_dynamics_ma(df, sdm_period)
        df = self.add_slice_df(df)
        pdata['chart'] = df
        return pdata
    
    def _get_action_from_row(self, row):
        if row['sdm'] >= self.slope:
            if row['high'] > row['bbu'] and row['is_big']:
                return 'close_long'
            if row['over_bbu']:
                return 'close_long'
            if row['low'] < row['sma'] and row['sma2'] > row['sma']:
                return 'open_long'
        elif row['sdm'] <= -self.slope:
            if row['over_bbd']:
                return 'close_short'
            if row['low'] < row['bbd'] and row['is_big']:
                return 'close_short'
            if row['high'] > row['sma'] and row['sma2'] < row['sma']:
                return 'open_short'
        
        return None

