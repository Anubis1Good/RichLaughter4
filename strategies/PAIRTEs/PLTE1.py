from typing import Dict, Any, Tuple
from strategies.BaseTE import BaseTE


class LTEP1_SINGULARITY(BaseTE):
    """
    Парный реверс грид-бот с хеджем (перенос LWS8_SINGULARITY в RL4).
    Пример params в bot_on_ticker.py:
    (
        'TATNP',   # symbol2 (второй инструмент пары)
        2500,      # start
        3000,      # end
        5,         # amount_lvl
        3100,      # uh_lvl (верхний хедж-уровень, None если выкл)
        2400,      # dh_lvl (нижний хедж-уровень, None если выкл)
        False,     # first_long
        True,      # keep_hedge
        False,     # keep_pos
        True,      # last_point
        False,     # keep_start_long
        False,     # keep_start_short
        False,     # unfreeze
    )
    """

    def __init__(
        self,
        symbol: str = 'TATN',
        price_step: float = None,
        mode: Any = None,
        symbol2: str = 'TATNP',
        start: float = 2500.0,
        end: float = 3000.0,
        amount_lvl: int = 5,
        uh_lvl: float = 3100.0,
        dh_lvl: float = 2400.0,
        first_long: bool = False,
        keep_hedge: bool = True,
        keep_pos: bool = False,
        last_point: bool = True,
        keep_start_long: bool = False,
        keep_start_short: bool = False,
        unfreeze: bool = False,
        lot1: int = 1,
        lot2: int = 1,
    ):
        super().__init__(symbol=symbol, price_step=price_step, mode=mode, stop=None, take=None)
        self.symbol2 = symbol2
        self.symbols = (self.symbol, self.symbol2)
        self.lot_map = {self.symbol: lot1, self.symbol2: lot2}

        self.needs_info = {
            'chart': self.symbol,
            'poss': (self.symbol, self.symbol2),
        }

        self.max_pos = int(amount_lvl)
        self.hedge_pos = self.max_pos if last_point else self.max_pos - 1

        delta_se = end - start
        step_lvl = delta_se / (self.max_pos - 1) if self.max_pos > 1 else 0
        self.lvls = [start + step_lvl * i for i in range(self.max_pos)]

        self.uh_lvl = uh_lvl
        self.dh_lvl = dh_lvl
        self.first_long = first_long
        self.keep_hedge = keep_hedge
        self.keep_pos = keep_pos
        self.keep_start_long = keep_start_long
        self.keep_start_short = keep_start_short
        self.unfreeze = unfreeze

        self.lock_long = False
        self.lock_short = False
        self.in_work = True

        self.positions: Dict[str, float] = {self.symbol: 0.0, self.symbol2: 0.0}
        self.not_work_pos: Dict[str, float] = {}
        s_l, s_s = (self.symbols[0], self.symbols[1]) if self.first_long else (self.symbols[1], self.symbols[0])

        self.not_work_pos[s_l] = self.hedge_pos
        self.not_work_pos[s_s] = -self.hedge_pos

    def get_need_pos(self, pos_data: Tuple[Any, Any, int, int]) -> Dict[str, Any]:
        new_pos_long, new_pos_short, max_pos_long, max_pos_short = pos_data
        s_l, s_s = (self.symbols[0], self.symbols[1]) if self.first_long else (self.symbols[1], self.symbols[0])
        cur_pos_l = self.positions.get(s_l, 0.0)
        cur_pos_s = self.positions.get(s_s, 0.0)

        need_pos: Dict[str, Any] = {}
        if cur_pos_l >= max_pos_long:
            new_pos_long = max_pos_long
        if cur_pos_s <= max_pos_short:
            new_pos_short = max_pos_short

        if self.keep_pos:
            if new_pos_long != 0 and new_pos_long is not None:
                if cur_pos_l > new_pos_long:
                    new_pos_long = None
            if new_pos_short != 0 and new_pos_short is not None:
                if cur_pos_s < new_pos_short:
                    new_pos_short = None

        if self.keep_start_long:
            if new_pos_long == 0:
                self.lock_short = False
                if self.lock_long:
                    new_pos_long, new_pos_short = self.hedge_pos, -self.hedge_pos
                else:
                    self.keep_start_long = False
            elif new_pos_long is not None and new_pos_long < cur_pos_l:
                new_pos_long = None

        if self.keep_start_short:
            if new_pos_short == 0:
                self.lock_long = False
                if self.lock_short:
                    new_pos_long, new_pos_short = self.hedge_pos, -self.hedge_pos
                else:
                    self.keep_start_short = False
            elif new_pos_short is not None and new_pos_short > cur_pos_s:
                new_pos_short = None

        need_pos[s_l] = new_pos_long
        need_pos[s_s] = new_pos_short
        return need_pos

    def get_pos_on_grid(self, close_price: float) -> Tuple[Any, Any, int, int]:
        if self.dh_lvl is not None and close_price < self.dh_lvl:
            self.in_work = False if self.keep_hedge else True
            if self.unfreeze:
                self.lock_short = True
                self.keep_start_short = True
                self.keep_start_long = True
                self.in_work = True
            return (self.hedge_pos, -self.hedge_pos, self.max_pos, -self.max_pos)

        if self.uh_lvl is not None and close_price > self.uh_lvl:
            self.in_work = False if self.keep_hedge else True
            if self.unfreeze:
                self.lock_long = True
                self.keep_start_long = True
                self.keep_start_short = True
                self.in_work = True
            return (self.hedge_pos, -self.hedge_pos, self.max_pos, -self.max_pos)

        new_pos_long, new_pos_short = None, None
        max_pos_long, max_pos_short = 0, 0
        for lvl in self.lvls:
            if close_price <= lvl:
                max_pos_long += 1
                new_pos_long = max_pos_long - 1
            if close_price >= lvl:
                max_pos_short -= 1
                new_pos_short = max_pos_short + 1
        return new_pos_long, new_pos_short, max_pos_long, max_pos_short

    def preprocessing(self, tdata: Dict[str, Any]) -> Dict[str, Any]:
        # Обновляем текущие позиции в юнитах стратегии из tdata['poss']
        poss = tdata.get('poss')
        if isinstance(poss, dict):
            for s in self.symbols:
                if s in poss:
                    raw_amt = float(poss[s].get('amount', 0.0))
                    lot = self.lot_map.get(s, 1)
                    self.positions[s] = raw_amt / lot if lot else raw_amt
        return {'chart': tdata.get('chart')}

    def get_raw_action(self, pdata: Dict[str, Any]) -> Dict[str, Any]:
        if not self.in_work:
            return self.not_work_pos.copy()

        df = pdata['chart']
        if pdata.get('fast_mode') and 'idx' in pdata:
            close_price = float(df['close'].iat[pdata['idx']])
        else:
            close_price = float(df['close'].iat[-1])

        pos_data = self.get_pos_on_grid(close_price)
        return self.get_need_pos(pos_data)

