import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
from time import time
from dataclasses import dataclass
from strategies.BaseTE import BaseTE
from utils.work_dfs.load_df import simple_load_df
from utils.work_dfs.convert_tf import convert_timeframe
from utils.work_dfs.other import get_price_step
from utils.drawing.chart import draw_hb_chart_fast
from utils.metrics.equity_metrics import equity_curve_metrics, composite_score, lex_score


def duration_time(func):
    def wrapper(self, *args, **kwargs):
        if self.measure_time:
            start = time()
            print('start', func.__name__)
            result = func(self, *args, **kwargs)
            print('Time:', time() - start)
        else:
            result = func(self, *args, **kwargs)
        return result
    return wrapper


@dataclass
class Order:
    long_dir: bool
    price: float
    amount: float = 1.0


class CheckTETrader:
    def __init__(
        self,
        df: pd.DataFrame | str,
        ws: list | tuple | BaseTE,
        fee: float = 0.001,  # в долях (абсолютное значение)
        symbol: str = 'Test',
        close_on_time: bool = True,
        close_map: tuple | list = (
            (22, 30), (22, 30), (22, 30), (22, 30), (22, 30), (17, 30), (17, 30),
        ),
        measure_time: bool = False,
        use_tqdm: bool = False,
        window: int = 60,
        days_mode=None,
        slip_stop_delta=1,
        auto_take=1,
    ):
        self.window = window
        self.symbol = symbol
        self.slip_stop_delta = slip_stop_delta
        if isinstance(df, str):
            path_df = df
            self.df = simple_load_df(path_df)
        else:
            self.df = df.copy()
        self.price_step = get_price_step(self.df)
        self.mean_price = self.df['close'].mean()
        self.price_step_per = (self.price_step / self.mean_price) * 100

        if isinstance(ws, (tuple, list)):
            cls = ws[0]
            params = ws[1] if len(ws) > 1 else ()
            mode = ws[2] if len(ws) > 2 else None
            self.ws = cls(self.symbol, self.price_step, mode, *params)
        else:
            self.ws = ws

        self.fee = fee
        self.fee_one_p = fee * 100
        self.close_on_time = close_on_time
        self.close_map = close_map
        self.check_days_mode(days_mode)
        self.measure_time = measure_time
        self.use_tqdm = use_tqdm
        self.df = self.add_time_features(self.df)
        self.days = self.df['ms'].dt.date.nunique()
        self.auto_take = auto_take
        self.reload_data()

    def check_days_mode(self, days_mode):
        """Пропускаем дни из списка days_mode."""
        if days_mode is not None:
            close_map_list = list(self.close_map)
            for d in days_mode:
                close_map_list[d] = (0, 0)
            self.close_map = tuple(close_map_list)

    def reload_data(self):
        self.trade_data = {
            'total': 0.0,
            'count': 0,  # количество входов/доборов
            'fees': 0.0,  # комиссия в абсолютных единицах
            'total_wfees_per': 0.0,  # прибыль в процентах с учетом комиссии
            'equity': [0.0],  # динамика дохода по закрытым сделкам
            'equity_fee': [0.0],  # динамика дохода с комиссией
            'step_eq_fee': [0.0],  # equity каждый шаг
            'unclosed_fee': [0.0],  # equity незакрытый каждый шаг
            'pos': 0.0,  # текущая позиция (поддерживает дробные и >1 значения)
            'hist_pos': [0.0],
            'open_price': 0.0,  # средневзвешенная цена текущей позиции
            'o_longs': [],  # входы/доборы в лонг
            'o_shorts': [],  # входы/доборы в шорт
            'c_longs': [],  # закрытия лонгов
            'c_shorts': [],  # закрытия шортов
            'takes':[0],  # тейков
            'stops':[0],  # стопов
        }
        self.open_fee = 0.0
        self.cur_eq = None
        self.tdata = {}
        self.tdata['chart'] = self.df.copy()
        if self.ws is not None:
            self.ws.amount_sl = 0
            self.ws.amount_tp = 0
            self.ws.can_long = True
            self.ws.can_short = True
        self.orders: list[Order] = []

    def get_iterator(self, data):
        if self.use_tqdm:
            return tqdm(data)
        return data

    # ================= УПРАВЛЕНИЕ ПОЗИЦИЕЙ (ВКЛЮЧАЯ УСРЕДНЕНИЕ И ЧАСТИЧНОЕ ЗАКРЫТИЕ) =================

    def _add_position(self, delta_qty: float, price: float, row_name):
        """Открытие новой позиции или усреднение/пирамидинг в ту же сторону."""
        if abs(delta_qty) < 1e-9:
            return
        cur_pos = self.trade_data['pos']
        cur_open = self.trade_data['open_price']
        abs_add = abs(delta_qty)
        fee_part = self.fee * price * abs_add

        new_pos = round(cur_pos + delta_qty, 8)
        if abs(cur_pos) < 1e-9:
            self.trade_data['open_price'] = price
        else:
            # Средневзвешенная цена входа при доборе
            self.trade_data['open_price'] = (abs(cur_pos) * cur_open + abs_add * price) / abs(new_pos)

        self.trade_data['pos'] = new_pos
        self.trade_data['fees'] += fee_part
        self.open_fee += fee_part
        self.trade_data['total_wfees_per'] -= self.fee_one_p * abs_add
        self.trade_data['count'] += 1

        if delta_qty > 0:
            self.trade_data['o_longs'].append((row_name, price))
        else:
            self.trade_data['o_shorts'].append((row_name, price))

    def _reduce_position(self, close_qty: float, price: float, row_name, is_stop: bool = False):
        """Частичное или полное закрытие текущей позиции."""
        cur_pos = self.trade_data['pos']
        abs_cur = abs(cur_pos)
        abs_close = min(abs(close_qty), abs_cur)
        if abs_close < 1e-9:
            return

        open_price = self.trade_data['open_price']
        is_long = cur_pos > 0

        # Прибыль на закрываемый объём
        unit_delta = (price - open_price) if is_long else (open_price - price)
        if is_stop:
            unit_delta *= self.slip_stop_delta
        realized_delta = unit_delta * abs_close

        # Пропорциональная часть входной комиссии + комиссия за закрытие
        ratio = abs_close / abs_cur
        entry_fee_part = self.open_fee * ratio
        exit_fee_part = self.fee * price * abs_close

        self.open_fee = max(0.0, self.open_fee - entry_fee_part)
        self.trade_data['fees'] += exit_fee_part
        self.trade_data['total'] += realized_delta
        self.trade_data['total_wfees_per'] += ((unit_delta / price) * 100 - self.fee_one_p) * abs_close
        self.trade_data['equity'].append(self.trade_data['equity'][-1] + realized_delta)
        self.trade_data['equity_fee'].append(
            self.trade_data['equity_fee'][-1] + realized_delta - exit_fee_part - entry_fee_part
        )

        rem_pos = round(cur_pos - (abs_close if is_long else -abs_close), 8)
        self.trade_data['pos'] = rem_pos
        if abs(rem_pos) < 1e-9:
            self.trade_data['pos'] = 0.0
            self.trade_data['open_price'] = 0.0
            self.open_fee = 0.0

        if is_long:
            self.trade_data['c_longs'].append((row_name, price))
        else:
            self.trade_data['c_shorts'].append((row_name, price))

    def set_position(self, target_pos: float, price: float, row_name, is_stop: bool = False):
        """Универсальный переход из текущей позиции в целевую target_pos (поддерживает 0, +-1, дробные, пирамидинг и переворот)."""
        cur_pos = self.trade_data['pos']
        diff = round(target_pos - cur_pos, 8)
        if abs(diff) < 1e-9:
            return

        # 1. Если позиция была и она закрывается или переворачивается в другую сторону
        if cur_pos > 0 and target_pos < cur_pos:
            close_amt = cur_pos if target_pos <= 0 else (cur_pos - target_pos)
            self._reduce_position(close_amt, price, row_name, is_stop=is_stop)
            if target_pos < 0:
                self._add_position(target_pos, price, row_name)
        elif cur_pos < 0 and target_pos > cur_pos:
            close_amt = abs(cur_pos) if target_pos >= 0 else (target_pos - cur_pos)
            self._reduce_position(close_amt, price, row_name, is_stop=is_stop)
            if target_pos > 0:
                self._add_position(target_pos, price, row_name)
        else:
            # 2. Открытие с нуля или добор (усреднение) в ту же сторону
            self._add_position(diff, price, row_name)

    def exec_orders(self, high, low, row_name):
        if len(self.orders) != 0:
            for order in self.orders:
                if order.long_dir:
                    if low <= order.price:
                        target = round(self.trade_data['pos'] + order.amount, 8)
                        self.set_position(target, order.price, row_name)
                else:
                    if high >= order.price:
                        target = round(self.trade_data['pos'] - order.amount, 8)
                        self.set_position(target, order.price, row_name)
            self.orders.clear()

    def work_action(self, action, price, row_name, high, low, top_level, bottom_level):
        self.exec_orders(high, low, row_name)
        if action is None:
            return

        cur_pos = self.trade_data['pos']

        # Поддержка числового set_pos (0, 1, -1, 0.5, 2.0 и т.д.)
        if isinstance(action, (int, float)) and not isinstance(action, bool):
            self.set_position(float(action), price, row_name)
            return

        if isinstance(action, str):
            if action == 'open_long':
                self.set_position(1.0, price, row_name)
            elif action == 'open_short':
                self.set_position(-1.0, price, row_name)
            elif action == 'close_long':
                if cur_pos > 0:
                    self.set_position(0.0, price, row_name)
            elif action == 'close_short':
                if cur_pos < 0:
                    self.set_position(0.0, price, row_name)
            elif action == 'close_all':
                if cur_pos != 0:
                    self.set_position(0.0, price, row_name)
            elif action == 'stop_close_long':
                if cur_pos > 0:
                    self.set_position(0.0, price, row_name, is_stop=True)
            elif action == 'stop_close_short':
                if cur_pos < 0:
                    self.set_position(0.0, price, row_name, is_stop=True)
            elif 'step' in action:
                self.work_step_action(action, price)
            elif 'level' in action:
                self.work_level_action(action, top_level, bottom_level)

    def work_step_action(self, action, price):
        parts_action = action.split('_')
        type_action = parts_action[0]
        dir_action = parts_action[1]
        step = int(parts_action[3])
        cur_pos = self.trade_data['pos']

        buy_price = price - step * self.price_step
        sell_price = price + step * self.price_step

        if type_action == 'spred':
            if dir_action == 'long':
                if cur_pos < 1.0:
                    self.orders.append(Order(True, buy_price, amount=1.0 - cur_pos))
                if cur_pos > 0:
                    self.orders.append(Order(False, sell_price, amount=cur_pos))
            elif dir_action == 'short':
                if cur_pos > -1.0:
                    self.orders.append(Order(False, sell_price, amount=1.0 + cur_pos))
                if cur_pos < 0:
                    self.orders.append(Order(True, buy_price, amount=abs(cur_pos)))
            else:  # 'all'
                if cur_pos < 1.0:
                    self.orders.append(Order(True, buy_price, amount=1.0 - cur_pos))
                if cur_pos > -1.0:
                    self.orders.append(Order(False, sell_price, amount=1.0 + cur_pos))

        elif type_action == 'open':
            if dir_action in ('long', 'all') and cur_pos < 1.0:
                self.orders.append(Order(True, buy_price, amount=1.0 - cur_pos))
            if dir_action in ('short', 'all') and cur_pos > -1.0:
                self.orders.append(Order(False, sell_price, amount=1.0 + cur_pos))
        else:  # 'close'
            if dir_action in ('long', 'all') and cur_pos > 0:
                self.orders.append(Order(False, sell_price, amount=cur_pos))
            if dir_action in ('short', 'all') and cur_pos < 0:
                self.orders.append(Order(True, buy_price, amount=abs(cur_pos)))

    def work_level_action(self, action, top_level, bottom_level):
        parts_action = action.split('_')
        type_action = parts_action[0]
        dir_action = parts_action[1]
        cur_pos = self.trade_data['pos']

        has_top = top_level is not None and not np.isnan(top_level)
        has_bot = bottom_level is not None and not np.isnan(bottom_level)

        if type_action == 'spred':
            if dir_action == 'long':
                if cur_pos < 1.0 and has_bot:
                    self.orders.append(Order(True, bottom_level, amount=1.0 - cur_pos))
                if cur_pos > 0 and has_top:
                    self.orders.append(Order(False, top_level, amount=cur_pos))
            elif dir_action == 'short':
                if cur_pos > -1.0 and has_top:
                    self.orders.append(Order(False, top_level, amount=1.0 + cur_pos))
                if cur_pos < 0 and has_bot:
                    self.orders.append(Order(True, bottom_level, amount=abs(cur_pos)))
            else:  # 'all'
                if cur_pos < 1.0 and has_bot:
                    self.orders.append(Order(True, bottom_level, amount=1.0 - cur_pos))
                if cur_pos > -1.0 and has_top:
                    self.orders.append(Order(False, top_level, amount=1.0 + cur_pos))

        elif type_action == 'open':
            if dir_action in ('long', 'all') and cur_pos < 1.0 and has_bot:
                self.orders.append(Order(True, bottom_level, amount=1.0 - cur_pos))
            if dir_action in ('short', 'all') and cur_pos > -1.0 and has_top:
                self.orders.append(Order(False, top_level, amount=1.0 + cur_pos))
        else:  # 'close'
            if dir_action in ('long', 'all') and cur_pos > 0 and has_top:
                self.orders.append(Order(False, top_level, amount=cur_pos))
            if dir_action in ('short', 'all') and cur_pos < 0 and has_bot:
                self.orders.append(Order(True, bottom_level, amount=abs(cur_pos)))

    def add_time_features(self, df: pd.DataFrame):
        df = df.copy()
        df['ms'] = pd.to_datetime(df['ms'], format='%Y-%m-%d %H:%M:%S')
        df['hour'] = df['ms'].dt.hour
        df['minute'] = df['ms'].dt.minute
        df['weekday'] = df['ms'].dt.weekday
        return df

    def update_step_data(self, price):
        self.trade_data['step_eq_fee'].append(self.trade_data['equity_fee'][-1])
        pos = self.trade_data['pos']
        self.trade_data['hist_pos'].append(pos)
        if pos > 0:
            unclosed_profit = (price - self.trade_data['open_price']) * abs(pos)
        elif pos < 0:
            unclosed_profit = (self.trade_data['open_price'] - price) * abs(pos)
        else:
            unclosed_profit = 0.0
        self.trade_data['unclosed_fee'].append(self.trade_data['step_eq_fee'][-1] + unclosed_profit)
        self.trade_data['stops'].append(self.ws.amount_sl)
        self.trade_data['takes'].append(self.ws.amount_tp)

    def sync_step_data(self, df_processed):
        price = 0
        empty_test = len(self.df) - len(df_processed)
        if empty_test > 0:
            for i in range(empty_test - 1):
                self.update_step_data(price)

    @duration_time
    def check_strategy_faster(self, history_bars=None, debug=False):
        """
        Быстрый тест для оптимизации.
        """
        self.reload_data()
        if debug:
            filepath = '_logs/csf/'
            os.makedirs(filepath, exist_ok=True)
            filepath = os.path.join(filepath, self.symbol + '.txt')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n')

        pdata = self.ws.preprocessing(self.tdata)
        df: pd.DataFrame = pdata['chart']

        window = self.window - (len(self.df) - len(df))
        self.sync_step_data(df)

        if self.close_on_time:
            close_hours = df['weekday'].map(lambda wd: self.close_map[wd][0])
            close_minutes = df['weekday'].map(lambda wd: self.close_map[wd][1])
            mask = (df['hour'] > close_hours) | (
                (df['hour'] == close_hours) & (df['minute'] >= close_minutes)
            )
            mask_values = mask.values
        else:
            mask_values = None

        highs = df['high'].values
        lows = df['low'].values
        prices = df['close'].values
        row_names = df['x'].values

        top = df.get('test_top_level')
        top_levels = top.values if top is not None else np.full(len(df), np.nan)
        bottom = df.get('test_bottom_level')
        bottom_levels = bottom.values if bottom is not None else np.full(len(df), np.nan)

        for i in self.get_iterator(range(len(df))):
            price = prices[i]
            high = highs[i]
            low = lows[i]
            if i < window:
                self.update_step_data(price)
                continue
            row_name = row_names[i]
            top_level = top_levels[i]
            bottom_level = bottom_levels[i]

            if self.close_on_time and mask_values[i]:
                action = 'close_all'
            else:
                pos = self.trade_data['pos']
                open_price = self.trade_data['open_price']

                delta = None
                if pos != 0 and open_price != 0:
                    if pos > 0:
                        delta_nega = (low - open_price) // self.price_step
                        if self.ws.stop is not None and delta_nega <= -self.ws.stop:
                            delta = delta_nega
                        elif self.auto_take is not None and self.ws.take is not None:
                            delta_posi = (high - open_price) // self.price_step
                            auto_take = self.ws.take * self.auto_take
                            if delta_posi >= auto_take:
                                delta = auto_take
                            else:
                                delta = (price - open_price) // self.price_step
                        else:
                            delta = (price - open_price) // self.price_step
                    else:
                        delta_nega = (open_price - high) // self.price_step
                        if self.ws.stop is not None and delta_nega <= -self.ws.stop:
                            delta = delta_nega
                        elif self.auto_take is not None and self.ws.take is not None:
                            delta_posi = (open_price - low) // self.price_step
                            auto_take = self.ws.take * self.auto_take
                            if delta_posi >= auto_take:
                                delta = auto_take
                            else:
                                delta = (open_price - price) // self.price_step
                        else:
                            delta = (open_price - price) // self.price_step

                fast_pdata = {
                    'chart': df,
                    'idx': i,
                    'fast_mode': True
                }
                action = self.ws(fast_pdata, pos, delta)

            if debug:
                row = df.iloc[i]
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write(row.to_string() + '\n')
                    f.write(str(row_name) + '_' + str(action) + '\n')
                    f.write('-' * 50 + '\n')

            self.work_action(action, price, row_name, high, low, top_level, bottom_level)
            self.update_step_data(price)

    @duration_time
    def check_strategy_window(self, normalization=True):
        """
        Честный оконный тест для проверки стратегии.
        """
        self.reload_data()

        for i in self.get_iterator(range(len(self.df))):
            if i < self.window:
                self.update_step_data(self.df.iloc[i]['close'])
                continue

            df_slice = self.df.iloc[i - self.window:i + 1].copy()
            price = df_slice.iloc[-1]['close']
            row_name = df_slice.iloc[-1]['x']
            low = df_slice.iloc[-1]['low']
            high = df_slice.iloc[-1]['high']

            if self.close_on_time:
                last_row = df_slice.iloc[-1]
                time_close = self.close_map[last_row['weekday']]
                if (last_row['hour'] > time_close[0]) or (
                    last_row['hour'] == time_close[0] and last_row['minute'] >= time_close[1]
                ):
                    action = 'close_all'
                    self.work_action(action, price, row_name, high, low, None, None)
                    self.update_step_data(price)
                    continue

            if normalization:
                candle_max = df_slice['high'].max()
                if candle_max > 0:
                    df_slice['volume'] = df_slice['volume'] / df_slice['volume'].max() if df_slice['volume'].max() > 0 else 0
                    df_slice['close'] = df_slice['close'] / candle_max
                    df_slice['open'] = df_slice['open'] / candle_max
                    df_slice['low'] = df_slice['low'] / candle_max
                    df_slice['high'] = df_slice['high'] / candle_max
                    df_slice['middle'] = df_slice['middle'] / candle_max

            tdata = {'chart': df_slice}
            pdata = self.ws.preprocessing(tdata)
            df_pdata = pdata.get('chart')

            top_level, bottom_level = None, None
            levels_list = pdata.get('levels') if isinstance(pdata, dict) else None
            if levels_list and len(levels_list) >= 2:
                top_level, bottom_level = levels_list[0], levels_list[1]
            elif df_pdata is not None:
                top = df_pdata.get('test_top_level')
                if top is not None:
                    top_level = top.iloc[-1]
                bottom = df_pdata.get('test_bottom_level')
                if bottom is not None:
                    bottom_level = bottom.iloc[-1]

            if normalization and df_pdata is not None:
                norm_price = df_pdata['close'].iloc[-1]
                if norm_price != 0:
                    if top_level is not None:
                        top_level = price * top_level / norm_price
                    if bottom_level is not None:
                        bottom_level = price * bottom_level / norm_price

            pos = self.trade_data['pos']
            open_price = self.trade_data['open_price']

            delta = None
            if pos != 0 and open_price != 0:
                if pos > 0:
                    delta_nega = (low - open_price) // self.price_step
                    if self.ws.stop is not None and delta_nega <= -self.ws.stop:
                        delta = delta_nega
                    elif self.auto_take is not None and self.ws.take is not None:
                        delta_posi = (high - open_price) // self.price_step
                        auto_take = self.ws.take * self.auto_take
                        if delta_posi >= auto_take:
                            delta = auto_take
                        else:
                            delta = (price - open_price) // self.price_step
                    else:
                        delta = (price - open_price) // self.price_step
                else:
                    delta_nega = (open_price - high) // self.price_step
                    if self.ws.stop is not None and delta_nega <= -self.ws.stop:
                        delta = delta_nega
                    elif self.auto_take is not None and self.ws.take is not None:
                        delta_posi = (open_price - low) // self.price_step
                        auto_take = self.ws.take * self.auto_take
                        if delta_posi >= auto_take:
                            delta = auto_take
                        else:
                            delta = (open_price - price) // self.price_step
                    else:
                        delta = (open_price - price) // self.price_step

            action = self.ws(pdata, pos, delta)
            self.work_action(action, price, row_name, high, low, top_level, bottom_level)
            self.update_step_data(price)

    # POST_PROCESS_RESULT_FUNCS
    def process_old_type_result(self):
        df_eq = pd.DataFrame({'eq': self.trade_data['equity'], 'eq_fee': self.trade_data['equity_fee']})
        trades = {
            'total': self.trade_data['total'],
            'count': self.trade_data['count'],
            'total_fee_per': self.trade_data['total_wfees_per'],
        }
        if df_eq.empty or len(df_eq) < 2:
            trades.update({
                'total_abs_fee': 0,
                'win_rate_wf': 0,
                'total_fee': self.trade_data['fees'],
                'mean_eq': 0,
                'median_eq': 0,
                'max_eq': 0,
                'min_eq': 0,
                'balance_eq': 0,
                'mean_eqf': 0,
                'median_eqf': 0,
                'max_eqf': 0,
                'min_eqf': 0,
                'balance_eqf': 0,
            })
        else:
            df_eq['diff_eq'] = df_eq['eq'].diff()
            df_eq['diff_eq_fee'] = df_eq['eq_fee'].diff()

            diff_eq = df_eq['diff_eq'].dropna()
            diff_eq_fee = df_eq['diff_eq_fee'].dropna()

            if len(diff_eq) == 0:
                mean_eq = median_eq = min_eq = max_eq = 0
                mean_eqf = median_eqf = min_eqf = max_eqf = 0
                win_rate = 0
            else:
                mean_eq = diff_eq.mean()
                median_eq = diff_eq.median()
                min_eq = diff_eq.min()
                max_eq = diff_eq.max()

                mean_eqf = diff_eq_fee.mean()
                median_eqf = diff_eq_fee.median()
                min_eqf = diff_eq_fee.min()
                max_eqf = diff_eq_fee.max()

                wins = len(diff_eq[diff_eq > 0])
                loss = len(diff_eq[diff_eq < 0])
                win_rate = round((wins / (wins + loss)) * 100, 2) if loss > 0 else 0

            trades['total_fee_per'] = round(self.trade_data['total_wfees_per'], 2)
            trades.update({
                'total_abs_fee': self.trade_data['equity_fee'][-1] if self.trade_data['equity_fee'] else 0,
                'win_rate_wf': win_rate,
                'total_fee': self.trade_data['fees'],
                'mean_eq': mean_eq,
                'median_eq': median_eq,
                'max_eq': max_eq,
                'min_eq': min_eq,
                'balance_eq': max_eq + min_eq,
                'mean_eqf': mean_eqf,
                'median_eqf': median_eqf,
                'max_eqf': max_eqf,
                'min_eqf': min_eqf,
                'balance_eqf': max_eqf + min_eqf,
            })
        longs = np.array(self.trade_data['o_longs']) if self.trade_data['o_longs'] else np.array([])
        shorts = np.array(self.trade_data['o_shorts']) if self.trade_data['o_shorts'] else np.array([])
        closes = (
            np.array(self.trade_data['c_longs'] + self.trade_data['c_shorts'])
            if (self.trade_data['c_longs'] or self.trade_data['c_shorts'])
            else np.array([])
        )
        equity = np.array(self.trade_data['equity'])
        equity_fee = np.array(self.trade_data['equity_fee'])

        em = equity_curve_metrics(self.trade_data['equity_fee'])
        trades.update({f'curve_{k}': v for k, v in em.items()})
        trades['curve_composite'] = composite_score(em['total_return'], em)
        trades['curve_lex'] = lex_score(em, tr_eps=0.01, dd_limit=1.0)
        return trades, equity, equity_fee, longs, shorts, closes

    def print_statistics(self):
        """Печать статистики по торгам."""
        td = self.trade_data
        print(f"\n=== СТАТИСТИКА ДЛЯ {self.symbol} ===")
        print(f"Прибыль ABC без комисии: {td['equity'][-1]:.2f}")
        print(f"Прибыль ABC c комиссией: {td['equity_fee'][-1]:.2f}")
        print(f"Комисии: {td['fees']:.2f}")
        print(f"Прибыль PER c комиссией: {td['total_wfees_per']:.2f}")
        print(f"Всего сделок: {td['count']}")
        print(f"Максимальная прибыль: {max(td['unclosed_fee']):.2f}")
        print(f"Максимальная просадка: {min(td['unclosed_fee']):.2f}")
        print(f"Открыто лонгов: {len(td['o_longs'])}")
        print(f"Открыто шортов: {len(td['o_shorts'])}")
        print(f"Тейков: {td['takes'][-1]}")
        print(f"Стопов: {td['stops'][-1]}")

    def get_statistics(self):
        td = self.trade_data
        pick_profit = 0
        dropdown = 0
        pick_loss = 0
        dropup = 0
        for p in td['unclosed_fee']:
            if p > pick_profit:
                pick_profit = p
            elif p < pick_profit:
                delta = pick_profit - p
                if delta > dropdown:
                    dropdown = delta

            if p < pick_loss:
                pick_loss = p
            elif p > pick_loss:
                delta = p - pick_loss
                if delta > dropup:
                    dropup = delta

        statistics = {
            'total': td['total'],
            'total_wfee': td['equity_fee'][-1],
            'twf_per': round(td['total_wfees_per'], 2),
            'count': td['count'],
            'fees': td['fees'],
            'max_profit': max(td['unclosed_fee']),
            'min_profit': min(td['unclosed_fee']),
            'max_dropdown': dropdown,
            'max_dropup': dropup,
            'days': self.days,
            'eq_day': td['total'] / self.days if self.days > 0 else 0,
        }

        df_eq = pd.DataFrame({'eq': td['equity']})
        mean_eq = 0
        median_eq = 0
        min_eq = 0
        max_eq = 0
        win_rate = 0

        if not df_eq.empty and len(df_eq) > 1:
            df_eq['diff_eq'] = df_eq['eq'].diff()
            diff_eq = df_eq['diff_eq'].dropna()

            if not diff_eq.empty:
                mean_eq = diff_eq.mean()
                median_eq = diff_eq.median()
                min_eq = diff_eq.min()
                max_eq = diff_eq.max()

                wins = len(diff_eq[diff_eq > 0])
                loss = len(diff_eq[diff_eq < 0])
                total = wins + loss
                if total > 0:
                    win_rate = round((wins / total) * 100, 2)

        statistics.update({
            'win_rate': win_rate,
            'mean_eq': mean_eq,
            'median_eq': median_eq,
            'min_eq': min_eq,
            'max_eq': max_eq,
        })

        return statistics

    def plot_transaction(self):
        td = self.trade_data
        o_longs = np.array(td['o_longs']) if len(td['o_longs']) else np.array([])
        o_shorts = np.array(td['o_shorts']) if len(td['o_shorts']) else np.array([])
        c_longs = np.array(td['c_longs']) if len(td['c_longs']) else np.array([])
        c_shorts = np.array(td['c_shorts']) if len(td['c_shorts']) else np.array([])

        if o_longs.ndim > 1 and o_longs.size:
            plt.scatter(o_longs[:, 0], o_longs[:, 1], marker='^', color='blue')
        if o_shorts.ndim > 1 and o_shorts.size:
            plt.scatter(o_shorts[:, 0], o_shorts[:, 1], marker='v', color='black')
        if c_longs.ndim > 1 and c_longs.size:
            plt.scatter(c_longs[:, 0], c_longs[:, 1], marker='x', color='blue')
        if c_shorts.ndim > 1 and c_shorts.size:
            plt.scatter(c_shorts[:, 0], c_shorts[:, 1], marker='x', color='black')

    def plot_equity(self, show=True):
        plt.plot(self.trade_data['equity'], color='r')
        plt.plot(self.trade_data['equity_fee'], color='b')
        if show:
            plt.show()

    def plot_chart(self, convert_tf=None, show=True):
        chart = self.df.copy()
        if convert_tf:
            chart = convert_timeframe(chart, convert_tf)
        draw_hb_chart_fast(chart)
        self.plot_transaction()
        chart['date'] = chart['ms'].dt.date

        for date in chart['date'].unique():
            day_indices = chart[chart['date'] == date].index
            first_idx = day_indices[0]
            plt.axvline(x=first_idx, color='green', linestyle='--', alpha=0.3, linewidth=0.8)

            weekday = int(chart.loc[first_idx, 'weekday'])

            if hasattr(self, 'close_map') and weekday in range(len(self.close_map)):
                close_hour, close_minute = self.close_map[weekday]

                for idx in day_indices:
                    hour = int(chart.loc[idx, 'hour'])
                    minute = int(chart.loc[idx, 'minute'])

                    if hour > close_hour or (hour == close_hour and minute >= close_minute):
                        plt.axvline(x=idx, color='red', linestyle='--', alpha=0.3, linewidth=0.8)
                        y_min, y_max = plt.ylim()
                        plt.text(
                            idx, y_max * 0.95, f'{close_hour:02d}:{close_minute:02d}',
                            rotation=90, fontsize=7, color='red', alpha=0.5
                        )
                        break

        if show:
            plt.show()

    def plot_chart_and_sequtity(self, convert_tf=None, help_info='complex', show=True):
        """Создаем фигуру с двумя subplot'ами."""
        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)

        plt.sca(ax1)
        self.plot_chart(convert_tf, show=False)

        plt.sca(ax2)
        if help_info == 'step_equity':
            sequity = self.trade_data['step_eq_fee']
        elif help_info == 'pos':
            sequity = self.trade_data['hist_pos']
        elif help_info == 'unclosed':
            sequity = self.trade_data['unclosed_fee']
        elif help_info == 'complex':
            sequity = self.trade_data['unclosed_fee']
            ax2.plot(sequity)
            sequity = self.trade_data['step_eq_fee']
        elif help_info == 'sltp':
            sequity = self.trade_data['stops']
            ax2.plot(sequity, color='red')
            sequity = self.trade_data['takes']
        else:
            sequity = np.array([0])
        ax2.plot(sequity)
        total_wfee = sequity[-1]

        ax1.set_title(f'Chart for {self.symbol} days {self.days}')
        ax2.set_title('Sequity: ' + str(total_wfee) + ' MDS: ' + str(total_wfee / self.days if self.days > 0 else 0))
        cnt = self.trade_data['count']
        risk_lbl = 'Count_trades: ' + str(cnt) + '| Mean_profit: ' + str(total_wfee / cnt if cnt > 0 else 0)
        ax2.set_xlabel(risk_lbl)

        plt.tight_layout()
        if show:
            plt.show()



