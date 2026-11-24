from typing import Dict, Any, Optional
import pandas as pd
from for_strategies.help_dtypes.actions_cls import OrderManager


class BaseTE:
    """
    TE - Trading Engine (Управляющий торговой логикой).
    Возвращает одно из:
      - str: команда ('open_long', 'close_long', 'close_all', 'spred_all_step_5')
      - int / float: целевая позиция в юнитах для self.symbol (например, 1, -1, 0, 2)
      - dict: команды или целевые позиции по нескольким инструментам ({'IMOEXF': 1, 'MMZ5': -1})
      - объекты заявок из OrderManager
      - None: без действий
    """

    def __init__(
        self,
        symbol: str = 'Test',
        price_step: Optional[float] = None,
        mode: Any = None,
        stop: Optional[float] = None,
        take: Optional[float] = None,
        **kwargs
    ):
        self.symbol = symbol
        self.price_step = price_step
        self.mode = mode
        self.stop = stop
        self.take = take

        self.needs_info: Optional[Dict[str, Any]] = None
        """Пример:
        self.needs_info = {
            'chart': True,
            'charts': (self.symbol,),
            'tapes': (self.symbol,),
            'poss': (self.symbol,),
            'orders': (self.symbol,),
        }"""

        self.can_long: bool = True
        self.can_short: bool = True
        self.type_te: int = 0  # 0 - D-ws, 1 - BD-ws, 2 - spred_glass
        self.block_type_tes: tuple = (0,)

        self.order_manager = OrderManager()
        self.amount_sl: int = 0
        self.amount_tp: int = 0
        self.last_action: Any = None

        self._slice_period: Optional[int] = None
        self._first_slice: bool = True
        self.problems: Any = None

    def _find_max_period(self) -> Optional[int]:
        """Находит максимальное значение period среди всех атрибутов объекта."""
        period_values = []
        for attr_name in dir(self):
            if 'period' in attr_name.lower():
                try:
                    value = getattr(self, attr_name)
                    if isinstance(value, (int, float)) and value > 0:
                        period_values.append(int(value))
                except Exception:
                    pass
        return max(period_values) if period_values else None

    def add_slice_df(self, df: pd.DataFrame, period: Optional[int] = None) -> pd.DataFrame:
        """Обрезает датафрейм, удаляя первые N строк прогрева индикаторов."""
        if period is not None:
            period_to_use = period
        else:
            if self._first_slice:
                self._slice_period = self._find_max_period()
                self._first_slice = False
            period_to_use = self._slice_period

            if period_to_use is None:
                return df

        return df.iloc[period_to_use + 1:].reset_index(drop=True)

    def get_test_df(self, df: pd.DataFrame) -> Any:
        return self.preprocessing(df)

    def get_test_row(self, df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
        if df is not None and not df.empty:
            try:
                return df.iloc[-1]
            except Exception:
                return None
        return None

    def check_stop(self, pos: int, delta: Optional[float], action: Any) -> Any:
        """delta > 0, если мы в плюсе, и < 0, если в минусе."""
        if self.stop is not None and delta is not None:
            if delta <= -self.stop:
                if pos > 0:
                    if self.type_te in self.block_type_tes:
                        self.can_long = False
                    if self.last_action != 'stop_close_long':
                        self.amount_sl += 1
                    return 'stop_close_long'
                elif pos < 0:
                    if self.type_te in self.block_type_tes:
                        self.can_short = False
                    if self.last_action != 'stop_close_short':
                        self.amount_sl += 1
                    return 'stop_close_short'
        return action

    def check_take(self, delta: Optional[float], action: Any) -> Any:
        if self.take is not None and delta is not None:
            if delta >= self.take:
                if self.last_action != 'close_all':
                    self.amount_tp += 1
                return 'close_all'
        return action

    def check_valid_action(self, action: Any, pos: int) -> Any:
        if isinstance(action, dict):
            return action
        if pos < 0:
            self.can_long = True
        elif pos > 0:
            self.can_short = True

        if action is None:
            return None

        if isinstance(action, str):
            if not self.can_long and 'open' in action:
                if 'long' in action:
                    return None
                if 'all' in action:
                    return action.replace('all', 'short')
            if not self.can_short and 'open' in action:
                if 'short' in action:
                    return None
                if 'all' in action:
                    return action.replace('all', 'long')
        elif isinstance(action, (int, float)):
            if not self.can_long and action > 0:
                return None
            if not self.can_short and action < 0:
                return None

        return action

    def preprocessing(self, tdata: Dict[str, Any]) -> Dict[str, Any]:
        """Передаем все данные (датафреймы, списки уровней, позиции, ордера и т.д.)."""
        return {}

    def get_raw_action(self, pdata: Dict[str, Any]) -> Any:
        """Обычный и быстрый режимы"""
        chart = pdata.get('chart', None)
        if chart is None or chart.empty:
            return None
        if pdata.get('fast_mode') and 'idx' in pdata:
            row = chart.iloc[pdata['idx']]
        else:
            row = self.get_test_row(chart)
        if row is None:
            return None
        return self._get_action_from_row(row)


    def get_raw_action_fast(self, pdata_fast: Dict[str, Any]) -> Any:
        """Быстрый режим"""
        return self.get_raw_action(pdata_fast)

    def _get_action_from_row(self, row: pd.Series) -> Any:
        """Основная логика стратегии. Переопределяется в каждой стратегии."""
        return None

    def __call__(self, pdata: Dict[str, Any], pos: int = 0, delta: Optional[float] = 0.0, *args, **kwds) -> Any:
        if isinstance(pdata, dict) and pdata.get('fast_mode', False):
            action = self.get_raw_action_fast(pdata)
        else:
            action = self.get_raw_action(pdata)

        if self.type_te in self.block_type_tes:
            action = self.check_valid_action(action, pos)

        action = self.check_stop(pos, delta, action)
        action = self.check_take(delta, action)

        self.last_action = action
        return action
