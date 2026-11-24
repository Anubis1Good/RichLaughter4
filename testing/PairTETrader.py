import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
from time import time
from typing import Dict, List, Any, Optional, Tuple
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


class PairTETrader:
    """
    Исторический тестер для парных и портфельных стратегий на базе BaseTE
    (LTE8_SINGULARITY, APSTE2_SPARTACUS, APSTE3_PROMETHEUS и др.).
    """

    def __init__(
        self,
        dfs: Dict[str, pd.DataFrame | str],
        ws: tuple | list | BaseTE,
        quantity: Optional[Dict[str, float] | List[float]] = None,
        fee: float = 0.0002,
        close_on_time: bool = True,
        close_map: tuple | list = (
            (22, 30), (22, 30), (22, 30), (22, 30), (22, 30), (17, 30), (17, 30),
        ),
        measure_time: bool = False,
        use_tqdm: bool = False,
        window: int = 150,
        days_mode=None,
    ):
        """
        dfs: словарь {'TATN': path_or_df, 'TATNP': path_or_df} (первый ключ — главный инструмент).
        ws: (StrategyClass, params_tuple, mode) или готовый экземпляр BaseTE.
        quantity: множители лотов по символам, например {'TATN': 1, 'TATNP': 1} или.
        """
        self.symbols = list(dfs.keys())
        self.main_symbol = self.symbols[0]
        self.window = window
        self.fee = fee
        self.fee_one_p = fee * 100
        self.close_on_time = close_on_time
        self.close_map = close_map
        self.check_days_mode(days_mode)
        self.measure_time = measure_time
        self.use_tqdm = use_tqdm

        if quantity is None:
            self.quantity_map = {s: 1.0 for s in self.symbols}
        elif isinstance(quantity, dict):
            self.quantity_map = {s: float(quantity.get(s, 1.0)) for s in self.symbols}
        else:
            self.quantity_map = {s: float(q) for s, q in zip(self.symbols, quantity)}

        # Загружаем и синхронизируем датафреймы всех инструментов по общей временной шкале ms
        raw_dfs: Dict[str, pd.DataFrame] = {}
        for s, src in dfs.items():
            df = simple_load_df(src) if isinstance(src, str) else src.copy()
            raw_dfs[s] = self._prepare_base_df(df)

        self.dfs = self._align_dfs(raw_dfs)
        self.price_steps = {s: get_price_step(self.dfs[s]) for s in self.symbols}
        self.main_price_step = self.price_steps[self.main_symbol]
        self.days = self.dfs[self.main_symbol]['ms'].dt.date.nunique()

        if isinstance(ws, (tuple, list)):
            cls = ws[0]
            params = ws[1] if len(ws) > 1 else ()
            mode = ws[2] if len(ws) > 2 else None
            self.ws = cls(self.main_symbol, self.main_price_step, mode, *params)
        else:
            self.ws = ws

        self.reload_data()

    def _prepare_base_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df['ms']):
            df['ms'] = pd.to_datetime(df['ms'])
        df = df.sort_values('ms').drop_duplicates(subset=['ms'], keep='last').reset_index(drop=True)
        df['hour'] = df['ms'].dt.hour
        df['minute'] = df['ms'].dt.minute
        df['weekday'] = df['ms'].dt.weekday
        return df

    def _align_dfs(self, raw_dfs: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Оставляем только общие временные метки ms для всех инструментов пары/портфеля."""
        common_ms = None
        for df in raw_dfs.values():
            ms_set = set(df['ms'])
            common_ms = ms_set if common_ms is None else (common_ms & ms_set)

        aligned: Dict[str, pd.DataFrame] = {}
        for s, df in raw_dfs.items():
            sub = df[df['ms'].isin(common_ms)].sort_values('ms').reset_index(drop=True)
            sub['x'] = sub.index
            aligned[s] = sub
        return aligned

    def check_days_mode(self, days_mode):
        if days_mode is not None:
            close_map_list = list(self.close_map)
            for d in days_mode:
                close_map_list[d] = (0, 0)
            self.close_map = tuple(close_map_list)

    def reload_data(self):
        self.trade_data = {
            s: {
                'total': 0.0,
                'count': 0,
                'fees': 0.0,
                'total_wfees_per': 0.0,
                'equity': [0.0],
                'equity_fee': [0.0],
                'step_eq_fee': [0.0],
                'unclosed_fee': [0.0],
                'pos': 0.0,
                'hist_pos': [0.0],
                'open_price': 0.0,
                'o_longs': [],
                'o_shorts': [],
                'c_longs': [],
                'c_shorts': [],
            }
            for s in self.symbols
        }
        self.open_fee = {s: 0.0 for s in self.symbols}
        self.max_poss = {s: 0.0 for s in self.symbols}

    def get_iterator(self, data):
        return tqdm(data) if self.use_tqdm else data

    def _get_poss_dict(self) -> Dict[str, Dict[str, float]]:
        """Формирует словарь позиций в формате CSTrader для передачи в tdata['poss']."""
        return {
            s: {
                'amount': self.trade_data[s]['pos'],
                'avgPrice': self.trade_data[s]['open_price'],
            }
            for s in self.symbols
        }

    # ================= УЧЁТ ПОЗИЦИЙ И КОМИССИЙ ПО КАЖДОЙ НОГЕ =================

    def _add_symbol_pos(self, symbol: str, delta_qty: float, price: float, row_name):
        if abs(delta_qty) < 1e-9:
            return
        td = self.trade_data[symbol]
        cur_pos = td['pos']
        cur_open = td['open_price']
        abs_add = abs(delta_qty)
        fee_part = self.fee * price * abs_add

        new_pos = round(cur_pos + delta_qty, 8)
        if abs(cur_pos) < 1e-9:
            td['open_price'] = price
        else:
            td['open_price'] = (abs(cur_pos) * cur_open + abs_add * price) / abs(new_pos)

        td['pos'] = new_pos
        td['fees'] += fee_part
        self.open_fee[symbol] += fee_part
        td['total_wfees_per'] -= self.fee_one_p * abs_add
        td['count'] += 1

        if delta_qty > 0:
            td['o_longs'].append((row_name, price))
        else:
            td['o_shorts'].append((row_name, price))

    def _reduce_symbol_pos(self, symbol: str, close_qty: float, price: float, row_name):
        td = self.trade_data[symbol]
        cur_pos = td['pos']
        abs_cur = abs(cur_pos)
        abs_close = min(abs(close_qty), abs_cur)
        if abs_close < 1e-9:
            return

        open_price = td['open_price']
        is_long = cur_pos > 0
        unit_delta = (price - open_price) if is_long else (open_price - price)
        realized_delta = unit_delta * abs_close

        ratio = abs_close / abs_cur
        entry_fee_part = self.open_fee[symbol] * ratio
        exit_fee_part = self.fee * price * abs_close

        self.open_fee[symbol] = max(0.0, self.open_fee[symbol] - entry_fee_part)
        td['fees'] += exit_fee_part
        td['total'] += realized_delta
        td['total_wfees_per'] += ((unit_delta / price) * 100 - self.fee_one_p) * abs_close
        td['equity'].append(td['equity'][-1] + realized_delta)
        td['equity_fee'].append(td['equity_fee'][-1] + realized_delta - exit_fee_part - entry_fee_part)

        rem_pos = round(cur_pos - (abs_close if is_long else -abs_close), 8)
        td['pos'] = rem_pos
        if abs(rem_pos) < 1e-9:
            td['pos'] = 0.0
            td['open_price'] = 0.0
            self.open_fee[symbol] = 0.0

        if is_long:
            td['c_longs'].append((row_name, price))
        else:
            td['c_shorts'].append((row_name, price))

    def _set_symbol_pos(self, symbol: str, target_pos: float, price: float, row_name):
        cur_pos = self.trade_data[symbol]['pos']
        diff = round(target_pos - cur_pos, 8)
        if abs(diff) < 1e-9:
            return

        if cur_pos > 0 and target_pos < cur_pos:
            close_amt = cur_pos if target_pos <= 0 else (cur_pos - target_pos)
            self._reduce_symbol_pos(symbol, close_amt, price, row_name)
            if target_pos < 0:
                self._add_symbol_pos(symbol, target_pos, price, row_name)
        elif cur_pos < 0 and target_pos > cur_pos:
            close_amt = abs(cur_pos) if target_pos >= 0 else (target_pos - cur_pos)
            self._reduce_symbol_pos(symbol, close_amt, price, row_name)
            if target_pos > 0:
                self._add_symbol_pos(symbol, target_pos, price, row_name)
        else:
            self._add_symbol_pos(symbol, diff, price, row_name)

    def _work_pair_action(self, action: Optional[Dict[str, Any]], prices: Dict[str, float], row_names: Dict[str, Any]):
        if isinstance(action, dict):
            for s, sub_act in action.items():
                if s not in self.symbols or sub_act is None:
                    continue
                if isinstance(sub_act, (int, float)) and not isinstance(sub_act, bool):
                    target = float(sub_act) * self.quantity_map[s]
                    if abs(target) > self.max_poss[s]:
                        self.max_poss[s] = abs(target)
                    self._set_symbol_pos(s, target, prices[s], row_names[s])
                elif sub_act == 'close_all':
                    self._set_symbol_pos(s, 0.0, prices[s], row_names[s])
                elif sub_act == 'open_long':
                    self._set_symbol_pos(s, self.quantity_map[s], prices[s], row_names[s])
                elif sub_act == 'open_short':
                    self._set_symbol_pos(s, -self.quantity_map[s], prices[s], row_names[s])

    def _update_all_step_data(self, prices: Dict[str, float]):
        for s in self.symbols:
            td = self.trade_data[s]
            td['step_eq_fee'].append(td['equity_fee'][-1])
            pos = td['pos']
            td['hist_pos'].append(pos)
            if pos > 0:
                unclosed = (prices[s] - td['open_price']) * abs(pos)
            elif pos < 0:
                unclosed = (td['open_price'] - prices[s]) * abs(pos)
            else:
                unclosed = 0.0
            td['unclosed_fee'].append(td['step_eq_fee'][-1] + unclosed)

    # ================= МЕТОДЫ ТЕСТИРОВАНИЯ =================

    @duration_time
    def check_strategy_faster(self):
        """
        Быстрый тест парной стратегии для оптимизации.
        Предполагает, что индикаторы в preprocessing считаются по окну назад (без заглядывания вперед).
        """
        self.reload_data()
        main_df = self.dfs[self.main_symbol]
        n = len(main_df)

        full_tdata = {
            'chart': main_df.copy(),
            'charts': {s: [self.dfs[s].copy()] for s in self.symbols if s != self.main_symbol},
            'poss': self._get_poss_dict(),
        }
        pdata = self.ws.preprocessing(full_tdata)
        proc_df = pdata['chart']

        offset = n - len(proc_df)
        if offset > 0:
            for k in range(offset):
                prices_k = {s: float(self.dfs[s]['close'].iat[k]) for s in self.symbols}
                self._update_all_step_data(prices_k)

        if self.close_on_time:
            close_hours = proc_df['weekday'].map(lambda wd: self.close_map[wd][0])
            close_minutes = proc_df['weekday'].map(lambda wd: self.close_map[wd][1])
            mask_values = ((proc_df['hour'] > close_hours) | (
                (proc_df['hour'] == close_hours) & (proc_df['minute'] >= close_minutes)
            )).values
        else:
            mask_values = None

        prices_map = {s: self.dfs[s]['close'].values[offset:] for s in self.symbols}
        xs_map = {s: self.dfs[s]['x'].values[offset:] for s in self.symbols}

        # print(f"DEBUG: len(main_df)={n}, len(proc_df)={len(proc_df)}, window={self.window}, close_on_time={self.close_on_time}")

        for i in self.get_iterator(range(len(proc_df))):
            cur_prices = {s: float(prices_map[s][i]) for s in self.symbols}
            cur_xs = {s: xs_map[s][i] for s in self.symbols}

            if i < self.window:
                self._update_all_step_data(cur_prices)
                continue

            if self.close_on_time and mask_values[i]:
                action = {s: 0.0 for s in self.symbols}
            else:
                # Синхронизируем текущие позиции стратегии перед вызовом get_raw_action
                if hasattr(self.ws, 'positions') and isinstance(self.ws.positions, dict):
                    for s in self.symbols:
                        q = self.quantity_map[s]
                        self.ws.positions[s] = self.trade_data[s]['pos'] / q if q else self.trade_data[s]['pos']

                fast_pdata = {
                    'chart': proc_df,
                    'idx': i,
                    'fast_mode': True,
                }
                action = self.ws(fast_pdata, 0, None)
            # if action and any(v not in (None, 0, 0.0) for v in action.values()):
            #     if not hasattr(self, '_debug_printed'):
            #         print("НЕНУЛЕВОЙ ACTION:", action, "i=", i)
            #         self._debug_printed = True


            self._work_pair_action(action, cur_prices, cur_xs)
            self._update_all_step_data(cur_prices)

    @duration_time
    def check_strategy_window(self):
        """
        Честный оконный тест парной стратегии (1-в-1 имитирует боевой CSTrader).
        """
        self.reload_data()
        main_df = self.dfs[self.main_symbol]
        n = len(main_df)

        prices_map = {s: self.dfs[s]['close'].values for s in self.symbols}
        xs_map = {s: self.dfs[s]['x'].values for s in self.symbols}

        for i in self.get_iterator(range(n)):
            cur_prices = {s: float(prices_map[s][i]) for s in self.symbols}
            cur_xs = {s: xs_map[s][i] for s in self.symbols}

            if i < self.window:
                self._update_all_step_data(cur_prices)
                continue

            if self.close_on_time:
                last_row = main_df.iloc[i]
                time_close = self.close_map[int(last_row['weekday'])]
                if (last_row['hour'] > time_close[0]) or (
                    last_row['hour'] == time_close[0] and last_row['minute'] >= time_close[1]
                ):
                    action = {s: 0.0 for s in self.symbols}
                    self._work_pair_action(action, cur_prices, cur_xs)
                    self._update_all_step_data(cur_prices)
                    continue

            start_idx = i - self.window
            end_idx = i + 1

            # Формируем poss в юнитах стратегии (как если бы lot был учтён снаружи)
            poss_units = {}
            for s in self.symbols:
                q = self.quantity_map[s]
                poss_units[s] = {
                    'amount': self.trade_data[s]['pos'] / q if q else self.trade_data[s]['pos'],
                    'avgPrice': self.trade_data[s]['open_price'],
                }

            slice_tdata = {
                'chart': main_df.iloc[start_idx:end_idx].copy(),
                'charts': {
                    s: [self.dfs[s].iloc[start_idx:end_idx].copy()]
                    for s in self.symbols if s != self.main_symbol
                },
                'poss': poss_units,
            }

            pdata = self.ws.preprocessing(slice_tdata)
            action = self.ws(pdata, 0, None)

            self._work_pair_action(action, cur_prices, cur_xs)
            self._update_all_step_data(cur_prices)

    # ================= СТАТИСТИКА И ГРАФИКИ =================

    def get_portfolio_equity(self, with_fee: bool = True, unclosed: bool = True) -> np.ndarray:
        col = 'unclosed_fee' if unclosed else 'step_eq_fee'
        length = len(self.trade_data[self.main_symbol][col])
        total_eq = np.zeros(length, dtype=float)
        for s in self.symbols:
            total_eq += np.array(self.trade_data[s][col], dtype=float)
        return total_eq

    def get_statistics(self) -> Dict[str, Any]:
        port_unclosed = self.get_portfolio_equity(unclosed=True)
        port_closed = self.get_portfolio_equity(unclosed=False)

        pick_profit = 0.0
        max_dd = 0.0
        for p in port_unclosed:
            if p > pick_profit:
                pick_profit = p
            elif p < pick_profit:
                dd = pick_profit - p
                if dd > max_dd:
                    max_dd = dd

        total_wfee = float(port_closed[-1]) if len(port_closed) else 0.0
        total_no_fee = sum(self.trade_data[s]['total'] for s in self.symbols)
        total_fees = sum(self.trade_data[s]['fees'] for s in self.symbols)
        total_trades = sum(self.trade_data[s]['count'] for s in self.symbols)
        total_max_pos = sum(self.max_poss.values())
        eq_day = total_wfee / self.days if self.days > 0 else 0.0

        em = equity_curve_metrics(list(port_closed))
        stats = {
            'total_no_fee': round(total_no_fee, 4),
            'total_wfee': round(total_wfee, 4),
            'fees': round(total_fees, 4),
            'count': total_trades,
            'max_profit': round(float(np.max(port_unclosed)), 4) if len(port_unclosed) else 0.0,
            'min_profit': round(float(np.min(port_unclosed)), 4) if len(port_unclosed) else 0.0,
            'max_dropdown': round(max_dd, 4),
            'days': self.days,
            'eq_day': round(eq_day, 4),
            'total_max_pos': total_max_pos,
            'eq_day_per_pos': round(eq_day / total_max_pos, 4) if total_max_pos > 0 else 0.0,
            'curve_composite': composite_score(em['total_return'], em),
            'curve_lex': lex_score(em, tr_eps=0.01, dd_limit=1.0),
        }
        return stats

    def print_statistics(self):
        stats = self.get_statistics()
        print(f"\n=== ПОРТФЕЛЬНАЯ СТАТИСТИКА ({' + '.join(self.symbols)}) ===")
        print(f"Прибыль ABC без комиссии: {stats['total_no_fee']:.2f}")
        print(f"Прибыль ABC с комиссией: {stats['total_wfee']:.2f}")
        print(f"Комиссии всего:          {stats['fees']:.2f}")
        print(f"Всего сделок (входов):   {stats['count']}")
        print(f"Прибыль в день:          {stats['eq_day']:.2f} (на лот: {stats['eq_day_per_pos']:.4f})")
        print(f"Максимальная просадка:   {stats['max_dropdown']:.2f}")
        print(f"Макс. экспозиция (лоты): {self.max_poss}")
        for s in self.symbols:
            td = self.trade_data[s]
            print(f"  -> {s}: PnL с ком.={td['equity_fee'][-1]:.2f} | сделок={td['count']} | ком.={td['fees']:.2f}")

    def _plot_symbol_transactions(self, symbol: str):
        td = self.trade_data[symbol]
        o_l = np.array(td['o_longs']) if td['o_longs'] else np.array([])
        o_s = np.array(td['o_shorts']) if td['o_shorts'] else np.array([])
        c_l = np.array(td['c_longs']) if td['c_longs'] else np.array([])
        c_s = np.array(td['c_shorts']) if td['c_shorts'] else np.array([])

        if o_l.ndim > 1 and o_l.size:
            plt.scatter(o_l[:, 0], o_l[:, 1], marker='^', color='blue')
        if o_s.ndim > 1 and o_s.size:
            plt.scatter(o_s[:, 0], o_s[:, 1], marker='v', color='black')
        if c_l.ndim > 1 and c_l.size:
            plt.scatter(c_l[:, 0], c_l[:, 1], marker='x', color='blue')
        if c_s.ndim > 1 and c_s.size:
            plt.scatter(c_s[:, 0], c_s[:, 1], marker='x', color='black')

    def plot_chart_and_equity(self, symbol: Optional[str] = None, convert_tf=None, help_info: str = 'couple_complex', show: bool = True):
        """
        Строит график цены выбранного инструмента (по умолчанию главного) со сделками
        и нижний график портфельной кривой доходности или позиций ('couple_complex', 'couple_pos', 'single').
        """
        target_sym = symbol or self.main_symbol
        chart = self.dfs[target_sym].copy()
        if convert_tf:
            chart = convert_timeframe(chart, convert_tf)

        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)

        plt.sca(ax1)
        draw_hb_chart_fast(chart)
        self._plot_symbol_transactions(target_sym)
        ax1.set_title(f'Pair Chart: {target_sym} ({", ".join(self.symbols)}) | days: {self.days}')

        plt.sca(ax2)
        if help_info == 'couple_pos':
            for s in self.symbols:
                ax2.plot(self.trade_data[s]['hist_pos'], label=f'pos_{s}')
            ax2.legend()
        elif help_info == 'single':
            ax2.plot(self.trade_data[target_sym]['unclosed_fee'], label='unclosed_fee')
            ax2.plot(self.trade_data[target_sym]['step_eq_fee'], label='step_eq_fee')
            ax2.legend()
        else:  # 'couple_complex'
            ax2.plot(self.get_portfolio_equity(unclosed=True), label='Portfolio Unclosed (with fee)')
            ax2.plot(self.get_portfolio_equity(unclosed=False), label='Portfolio Closed (with fee)')
            ax2.legend()

        stats = self.get_statistics()
        ax2.set_title(f"Portfolio PnL: {stats['total_wfee']} | Day: {stats['eq_day']} | MaxDD: {stats['max_dropdown']}")
        ax2.set_xlabel(f"Trades: {stats['count']} | MaxPos: {stats['total_max_pos']}")

        plt.tight_layout()
        if show:
            plt.show()

