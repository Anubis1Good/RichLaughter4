from typing import Dict, Any
import pandas as pd
from strategies.BaseTE import BaseTE
from for_strategies.arb_indicators import get_percent_diff_window


class UTEP1_SPARTACUS(BaseTE):
    """
    Статистический арбитраж (перенос APSWS2_SPARTACUS в RL4).
    Пример params в bot_on_ticker.py:
    (
        'TATNP',  # symbol2
        0.2,      # min_desc
        0.05,     # buff_0
        145,      # window
        None,     # smooth
        'close',  # kind
        False,    # reverse_pos
        0,        # funding: 0 | 1 | -1 | 'close_all'
        18,       # hour_fund
        24,       # minute_fund
    )
    """

    def __init__(
        self,
        symbol: str = 'TATN',
        price_step: float = None,
        mode: Any = None,
        symbol2: str = 'TATNP',
        min_desc: float = 0.2,
        buff_0: float = 0.05,
        window: int = 145,
        smooth: Any = None,
        kind: str = 'close',
        reverse_pos: bool = False,
        funding: Any = 0,
        hour_fund: int = 18,
        minute_fund: int = 24,
        lot1: int = 1,
        lot2: int = 1,
    ):
        super().__init__(symbol=symbol, price_step=price_step, mode=mode, stop=None, take=None)
        self.symbol2 = symbol2
        self.symbols = (self.symbol, self.symbol2)
        self.lot_map = {self.symbol: lot1, self.symbol2: lot2}

        self.needs_info = {
            'chart': self.symbol,
            'charts': (self.symbol2,),
            'poss': (self.symbol, self.symbol2),
        }

        self.min_desc = min_desc
        self.buff_0 = buff_0
        self.window = window
        self.smooth = smooth
        self.kind = kind
        self.reverse_pos = reverse_pos
        self.funding = funding
        self.hour_fund = hour_fund
        self.minute_fund = minute_fund

        self.enter_desc = 0
        self.positions: Dict[str, float] = {self.symbol: 0.0, self.symbol2: 0.0}

    def get_need_pos(self, row: pd.Series) -> Dict[str, Any]:
        s_1, s_2 = self.symbols[0], self.symbols[1]
        need_pos: Dict[str, Any] = {}
        pos_s1, pos_s2 = None, None

        if pd.notna(row['desc']):
            if row['desc'] > self.min_desc:
                pos_s1, pos_s2 = -1, 1
                self.enter_desc = 1
            elif row['desc'] < -self.min_desc:
                pos_s1, pos_s2 = 1, -1
                self.enter_desc = -1
            elif self.reverse_pos:
                pos_s1, pos_s2 = None, None
            elif self.enter_desc > 0:
                if row['desc'] < self.buff_0:
                    pos_s1, pos_s2 = 0, 0
                    self.enter_desc = 0
            elif self.enter_desc < 0:
                if row['desc'] > -self.buff_0:
                    pos_s1, pos_s2 = 0, 0
                    self.enter_desc = 0

        if row['weekday'] < 5 and self.funding:
            if row['hour'] == self.hour_fund and row['minute'] > self.minute_fund:
                if self.funding == 'close_all':
                    pos_s1, pos_s2 = 0, 0
                else:
                    pos_s1, pos_s2 = (-1, 1) if self.funding > 0 else (1, -1)

        if abs(self.positions[s_1]) != abs(self.positions[s_2]):
            if pos_s1 is None:
                if abs(self.positions[s_1]) > abs(self.positions[s_2]):
                    sign_s1 = 1 if self.positions[s_1] > 0 else -1
                    pos_s1, pos_s2 = sign_s1, -sign_s1
                else:
                    sign_s2 = 1 if self.positions[s_2] > 0 else -1
                    pos_s1, pos_s2 = sign_s2, -sign_s2

        need_pos[s_1] = pos_s1
        need_pos[s_2] = pos_s2
        return need_pos

    def preprocessing(self, tdata: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Обновляем позиции из tdata['poss']
        poss = tdata.get('poss')
        if isinstance(poss, dict):
            for s in self.symbols:
                if s in poss:
                    raw_amt = float(poss[s].get('amount', 0.0))
                    lot = self.lot_map.get(s, 1)
                    self.positions[s] = raw_amt / lot if lot else raw_amt

        # 2. Подготавливаем основной график и график второго инструмента
        df1 = tdata['chart'].copy()
        if not pd.api.types.is_datetime64_any_dtype(df1['ms']):
            df1['ms'] = pd.to_datetime(df1['ms'])
        if 'hour' not in df1.columns:
            df1['hour'] = df1['ms'].dt.hour
            df1['minute'] = df1['ms'].dt.minute
            df1['weekday'] = df1['ms'].dt.weekday

        raw_df2 = tdata['charts'][self.symbol2]
        df2 = (raw_df2[0] if isinstance(raw_df2, list) else raw_df2).copy()
        if not pd.api.types.is_datetime64_any_dtype(df2['ms']):
            df2['ms'] = pd.to_datetime(df2['ms'])

        df1['desc'] = get_percent_diff_window(df1, df2, self.window, self.smooth, self.kind)
        return {'chart': df1}

    def get_raw_action(self, pdata: Dict[str, Any]) -> Dict[str, Any]:
        df = pdata['chart']
        if pdata.get('fast_mode') and 'idx' in pdata:
            row = df.iloc[pdata['idx']]
        else:
            row = df.iloc[-1]
        return self.get_need_pos(row)
    

class UTEP2_PROMETHEUS(BaseTE):
    """
    Сеточный статистический арбитраж (перенос APSWS3_PROMETHEUS в RL4).
    Пример params в bot_on_ticker.py:
    (
        'TATNP',          # symbol2
        (0.05, 0.1, 0.2), # desc_lvls
        0.01,             # buff_0
        145,              # window
        None,             # smooth
        'close',          # kind
        False,            # reverse_pos
        0,                # funding: 0 | 1 | -1 | 'close_all'
        18,               # hour_fund
        24,               # minute_fund
        False,            # keep_pos
    )
    """

    def __init__(
        self,
        symbol: str = 'TATN',
        price_step: float = None,
        mode: Any = None,
        symbol2: str = 'TATNP',
        desc_lvls: tuple = (0.1, 0.2),
        buff_0: float = 0.01,
        window: int = 145,
        smooth: Any = None,
        kind: str = 'close',
        reverse_pos: bool = False,
        funding: Any = 0,
        hour_fund: int = 18,
        minute_fund: int = 24,
        keep_pos: bool = False,
        lot1: int = 1,
        lot2: int = 1,
    ):
        super().__init__(symbol=symbol, price_step=price_step, mode=mode, stop=None, take=None)
        self.symbol2 = symbol2
        self.symbols = (self.symbol, self.symbol2)
        self.lot_map = {self.symbol: lot1, self.symbol2: lot2}

        self.needs_info = {
            'chart': self.symbol,
            'charts': (self.symbol2,),
            'poss': (self.symbol, self.symbol2),
        }

        self.desc_lvls = desc_lvls
        self.buff_0 = buff_0
        self.window = window
        self.smooth = smooth
        self.kind = kind
        self.reverse_pos = reverse_pos
        self.funding = funding
        self.hour_fund = hour_fund
        self.minute_fund = minute_fund
        self.keep_pos = keep_pos

        self.enter_desc = 0
        self.positions: Dict[str, float] = {self.symbol: 0.0, self.symbol2: 0.0}

    def get_need_pos(self, row: pd.Series) -> Dict[str, Any]:
        s_1, s_2 = self.symbols[0], self.symbols[1]
        need_pos: Dict[str, Any] = {}
        pos_s1, pos_s2 = None, None

        if pd.notna(row['desc']):
            max_pos = 1
            enter_desc = 1 if row['desc'] > 0 else -1

            for lvl in self.desc_lvls:
                if row['desc'] > lvl or row['desc'] < -lvl:
                    max_pos += 1

            if max_pos != 1:
                new_pos = max_pos - 1
                if enter_desc == 1:
                    if self.positions[s_1] <= -max_pos:
                        if self.keep_pos:
                            pos_s1, pos_s2 = None, None
                        elif self.reverse_pos:
                            if self.positions[s_1] < 0:
                                pos_s1, pos_s2 = None, None
                            else:
                                pos_s1, pos_s2 = -new_pos, new_pos
                        else:
                            pos_s1, pos_s2 = -max_pos, max_pos
                    else:
                        pos_s1, pos_s2 = -new_pos, new_pos
                else:
                    if self.positions[s_1] >= max_pos:
                        if self.keep_pos:
                            pos_s1, pos_s2 = None, None
                        elif self.reverse_pos:
                            if self.positions[s_1] > 0:
                                pos_s1, pos_s2 = None, None
                            else:
                                pos_s1, pos_s2 = new_pos, -new_pos
                        else:
                            pos_s1, pos_s2 = max_pos, -max_pos
                    else:
                        pos_s1, pos_s2 = new_pos, -new_pos
                self.enter_desc = enter_desc

            if not self.reverse_pos:
                if self.enter_desc > 0:
                    if row['desc'] < self.buff_0:
                        pos_s1, pos_s2 = 0, 0
                        self.enter_desc = 0
                elif self.enter_desc < 0:
                    if row['desc'] > -self.buff_0:
                        pos_s1, pos_s2 = 0, 0
                        self.enter_desc = 0

        if row['weekday'] < 5 and self.funding:
            if row['hour'] == self.hour_fund and row['minute'] > self.minute_fund:
                if self.funding == 'close_all':
                    pos_s1, pos_s2 = 0, 0
                else:
                    pos_s1, pos_s2 = (-1, 1) if self.funding > 0 else (1, -1)

        if abs(self.positions[s_1]) != abs(self.positions[s_2]):
            if pos_s1 is None:
                if abs(self.positions[s_1]) > abs(self.positions[s_2]):
                    sign_s1 = 1 if self.positions[s_1] > 0 else -1
                    pos_s1, pos_s2 = sign_s1, -sign_s1
                else:
                    sign_s2 = 1 if self.positions[s_2] > 0 else -1
                    pos_s1, pos_s2 = sign_s2, -sign_s2

        need_pos[s_1] = pos_s1
        need_pos[s_2] = pos_s2
        return need_pos

    def preprocessing(self, tdata: Dict[str, Any]) -> Dict[str, Any]:
        poss = tdata.get('poss')
        if isinstance(poss, dict):
            for s in self.symbols:
                if s in poss:
                    raw_amt = float(poss[s].get('amount', 0.0))
                    lot = self.lot_map.get(s, 1)
                    self.positions[s] = raw_amt / lot if lot else raw_amt

        df1 = tdata['chart'].copy()
        if not pd.api.types.is_datetime64_any_dtype(df1['ms']):
            df1['ms'] = pd.to_datetime(df1['ms'])
        if 'hour' not in df1.columns:
            df1['hour'] = df1['ms'].dt.hour
            df1['minute'] = df1['ms'].dt.minute
            df1['weekday'] = df1['ms'].dt.weekday

        raw_df2 = tdata['charts'][self.symbol2]
        df2 = (raw_df2[0] if isinstance(raw_df2, list) else raw_df2).copy()

        if not pd.api.types.is_datetime64_any_dtype(df2['ms']):
            df2['ms'] = pd.to_datetime(df2['ms'])

        df1['desc'] = get_percent_diff_window(df1, df2, self.window, self.smooth, self.kind)
        return {'chart': df1}

    def get_raw_action(self, pdata: Dict[str, Any]) -> Dict[str, Any]:
        df = pdata['chart']
        if pdata.get('fast_mode') and 'idx' in pdata:
            row = df.iloc[pdata['idx']]
        else:
            row = df.iloc[-1]
        return self.get_need_pos(row)