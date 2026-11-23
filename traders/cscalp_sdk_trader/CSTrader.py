import os
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from strategies.BaseTE import BaseTE
from traders.cscalp_sdk_trader.CscalpClient import CscalpClient
from traders.cscalp_sdk_trader.bot_on_ticker import init_trader


class CSTrader:
    """
    Боевой трейдер для работы через локальный C# сервер CScalp SDK.
    Заменяет старый VT7 (CV + кликер) на прямое API-взаимодействие.
    """

    def __init__(
        self,
        group_cfg: Dict[str, Dict[str, Tuple[int, int]]],
        base_url: str = "http://localhost:7777",
        candles_limit: int = 200,
        close_on_time: bool = True,
        close_map: tuple = ((21, 30), (21, 30), (21, 30), (21, 30), (21, 30), (17, 30), (17, 30)),
        debug_mode: bool = False,
    ):
        self.client = CscalpClient(base_url=base_url)
        self.candles_limit = candles_limit
        self.close_on_time = close_on_time
        self.close_time = close_map[datetime.now().weekday()]
        self.debug_mode = debug_mode

        # Управление принудительными режимами с кнопок GUI:
        # None - штатно по времени, -2 - только закрытие, -1 - закрыть всё принудительно
        self.force_mode: Optional[int] = None

        self.active_bots: Dict[Tuple[str, str], Dict[str, Any]] = {}
        slots_to_subscribe: Dict[str, List[str]] = {}

        for slot, tickers_dict in group_cfg.items():
            for ticker, (lot, tf) in tickers_dict.items():
                slots_to_subscribe.setdefault(slot, []).append(ticker)
                te_cls, params, mode = init_trader(slot, ticker)
                self.active_bots[(slot, ticker)] = {
                    'te_cls': te_cls,
                    'params': params,
                    'mode': mode,
                    'te': None,
                    'tf': int(tf),
                    'lot': int(lot),
                    'step': 0.01,
                    'decimals': 2,
                }

        self.trader_name = 'CSTrader'
        self.folder_error = '_logs/error_logs_CSTrader'
        os.makedirs(self.folder_error, exist_ok=True)

        self._init_connections_and_strategies(slots_to_subscribe)

    def set_force_mode(self, mode: Optional[int]):
        """Переключение режима с кнопок GUI: None (штатно), -2 (только закрытие), -1 (закрыть всё)."""
        self.force_mode = mode
        print(f"[CSTrader] Установлен force_mode = {self.force_mode}")

    def _init_connections_and_strategies(self, slots_to_subscribe: Dict[str, List[str]]):
        if not slots_to_subscribe:
            print("[CSTrader] Нет активных инструментов для запуска.")
            return

        slots = list(slots_to_subscribe.keys())
        print(f"[CSTrader] Ожидание готовности слотов: {slots}...")
        self.client.wait_until_ready(slots, timeout_sec=30.0)

        for slot, tickers in slots_to_subscribe.items():
            self.client.subscribe(slot, tickers)
            print(f"[CSTrader] Подписка оформлена: {slot} -> {tickers}")

        time.sleep(1.5)

        for (slot, ticker), bot in self.active_bots.items():
            bp = self.client.get_best_prices(slot, ticker)
            step = bp.get('step', 0.01)
            decimals = bp.get('decimals', 2)
            bot['step'] = step
            bot['decimals'] = decimals

            te_cls = bot['te_cls']
            params = bot['params']
            mode = bot['mode']
            bot['te'] = te_cls(ticker, step, mode, *params)
            print(
                f"[CSTrader] Инициализирован {slot}:{ticker} -> {te_cls.__name__} "
                f"(tf={bot['tf']}m, lot={bot['lot']}, step={step})"
            )

    # ================= ВРЕМЯ И БЕЗОПАСНОСТЬ =================

    def _check_time(self) -> int:
        if self.force_mode is not None:
            return self.force_mode

        now = datetime.now()
        chour = now.hour
        cminute = now.minute
        if chour >= 7:
            if chour >= self.close_time[0] - 1:
                if cminute > self.close_time[1]:
                    if chour >= self.close_time[0]:
                        return -1
                    return -2
                elif chour == self.close_time[0]:
                    return -2
                elif chour > self.close_time[0]:
                    return -1
            return 1
        return 0

    def _apply_close_on_time(self, action: Any, time_mode: int) -> Any:
        # Принудительные кнопки (-1 и -2) работают даже если close_on_time=False
        if self.force_mode is None and not self.close_on_time:
            return action

        if time_mode == -1:
            return 'close_all'
        elif time_mode == -2:
            if isinstance(action, str):
                if 'open_long' in action:
                    return action.replace('open_long', 'close_short')
                elif 'open_short' in action:
                    return action.replace('open_short', 'close_long')
                elif 'spred' in action:
                    return action.replace('spred', 'close')
                elif 'open_all' in action:
                    return action.replace('open', 'close')
            elif isinstance(action, (int, float)) and action != 0:
                return 0
        return action

    # ================= СБОР ДАННЫХ ДЛЯ СТРАТЕГИИ =================

    def _collect_tdata(
        self,
        slot: str,
        ticker: str,
        bot: Dict[str, Any],
        orders_info: Dict[str, Any],
        bp: Dict[str, Any],
    ) -> Dict[str, Any]:
        te: BaseTE = bot['te']
        tf = bot['tf']
        tdata: Dict[str, Any] = {}
        needs = te.needs_info

        if needs is None or 'chart' in needs:
            tdata['chart'] = self.client.get_candles(slot, ticker, tf_minutes=tf, limit=self.candles_limit)

        if needs is not None:
            if 'charts' in needs:
                tdata['charts'] = {}
                for item in needs['charts']:
                    if isinstance(item, tuple):
                        req_ticker = item[0]
                        req_tf = item[1] if len(item) > 1 else tf
                    else:
                        req_ticker = item
                        req_tf = tf
                    df = self.client.get_candles(slot, req_ticker, tf_minutes=req_tf, limit=self.candles_limit)
                    tdata['charts'].setdefault(req_ticker, []).append(df)

            if 'tapes' in needs:
                tdata['tapes'] = {
                    s: self.client.get_ticks(slot, s, limit=500) for s in needs['tapes']
                }

            if 'spred' in needs:
                step = bp.get('step', bot['step'])
                tdata['spred'] = round((bp['bestAsk'] - bp['bestBid']) / step) if step else 0

            if 'full_glass' in needs or 'orderbook' in needs:
                tdata['fg'] = self.client.get_orderbook(slot, ticker, depth=20)

            if 'poss' in needs:
                tdata['poss'] = {
                    s: self.client.get_position(slot, s) for s in needs['poss']
                }

            if 'orders' in needs:
                tdata['orders'] = orders_info

        return tdata

    def _calc_pos_and_delta(
        self,
        bot: Dict[str, Any],
        pos_info: Dict[str, Any],
        bp: Dict[str, Any],
    ) -> Tuple[int, int, Optional[float]]:
        raw_amount = int(pos_info.get('amount', 0))
        avg_price = float(pos_info.get('avgPrice', 0.0))
        lot = bot['lot']
        step = bot['step']

        if raw_amount == 0:
            return 0, 0, None

        pos_units = int(round(raw_amount / lot)) if lot else raw_amount
        if pos_units == 0:
            pos_units = 1 if raw_amount > 0 else -1

        bbid = bp.get('bestBid', 0.0)
        bask = bp.get('bestAsk', 0.0)

        delta = None
        if avg_price > 0 and step > 0:
            if raw_amount > 0 and bbid > 0:
                delta = (bbid - avg_price) / step
            elif raw_amount < 0 and bask > 0:
                delta = (avg_price - bask) / step

        return raw_amount, pos_units, delta

    # ================= ИСПОЛНЕНИЕ КОМАНД И ЗАЯВОК =================

    def _set_target_amount(
        self,
        slot: str,
        ticker: str,
        current_amount: int,
        target_amount: int,
        limit_orders: List[Dict[str, Any]],
    ):
        diff = target_amount - current_amount
        if diff == 0:
            if limit_orders:
                self.client.cancel(slot, ticker)
            return

        if limit_orders:
            return

        if diff > 0:
            self.client.buy_limit(slot, ticker, amount=abs(diff), price=None)
        else:
            self.client.sell_limit(slot, ticker, amount=abs(diff), price=None)

    def _execute_step_action(
        self,
        slot: str,
        ticker: str,
        bot: Dict[str, Any],
        action: str,
        current_amount: int,
        bp: Dict[str, Any],
        limit_orders: List[Dict[str, Any]],
    ):
        parts = action.split('_')
        type_action = parts[0]   # 'spred', 'open', 'close'
        dir_action = parts[1]    # 'long', 'short', 'all'
        step_mult = int(parts[3])

        step = bot['step']
        decimals = bot['decimals']
        lot = bot['lot']

        bbid = bp.get('bestBid', 0.0)
        bask = bp.get('bestAsk', 0.0)
        if bbid <= 0 or bask <= 0:
            return

        buy_price = round(bbid - step_mult * step, decimals) if step_mult > 0 else None
        sell_price = round(bask + step_mult * step, decimals) if step_mult > 0 else None

        desired_orders: List[Tuple[str, float, Optional[float]]] = []

        if type_action == 'spred':
            if dir_action == 'long':
                if current_amount > 0:
                    desired_orders.append(('SELL', abs(current_amount), sell_price))
                else:
                    need_buy = lot + abs(current_amount) if current_amount < 0 else lot
                    desired_orders.append(('BUY', need_buy, buy_price))
            elif dir_action == 'short':
                if current_amount < 0:
                    desired_orders.append(('BUY', abs(current_amount), buy_price))
                else:
                    need_sell = lot + current_amount if current_amount > 0 else lot
                    desired_orders.append(('SELL', need_sell, sell_price))
            else:
                if current_amount > 0:
                    desired_orders.append(('SELL', abs(current_amount), sell_price))
                elif current_amount < 0:
                    desired_orders.append(('BUY', abs(current_amount), buy_price))
                else:
                    desired_orders.append(('BUY', lot, buy_price))
                    desired_orders.append(('SELL', lot, sell_price))

        elif type_action == 'open':
            if dir_action in ('long', 'all') and current_amount < lot:
                desired_orders.append(('BUY', lot - current_amount, buy_price))
            if dir_action in ('short', 'all') and current_amount > -lot:
                desired_orders.append(('SELL', lot + current_amount, sell_price))

        else:
            if dir_action in ('long', 'all') and current_amount > 0:
                desired_orders.append(('SELL', abs(current_amount), sell_price))
            if dir_action in ('short', 'all') and current_amount < 0:
                desired_orders.append(('BUY', abs(current_amount), buy_price))

        if len(limit_orders) == len(desired_orders):
            all_match = True
            for side, qty, price in desired_orders:
                matched = any(
                    o.get('side') == side and (price is None or abs(float(o.get('price', 0)) - price) < step * 0.1)
                    for o in limit_orders
                )
                if not matched:
                    all_match = False
                    break
            if all_match:
                return

        if limit_orders:
            self.client.cancel(slot, ticker)

        for side, qty, price in desired_orders:
            if side == 'BUY':
                self.client.buy_limit(slot, ticker, amount=qty, price=price)
            else:
                self.client.sell_limit(slot, ticker, amount=qty, price=price)

    def _work_action(
        self,
        slot: str,
        ticker: str,
        bot: Dict[str, Any],
        action: Any,
        current_amount: int,
        bp: Dict[str, Any],
        limit_orders: List[Dict[str, Any]],
    ):
        lot = bot['lot']

        if isinstance(action, (int, float)):
            target_amount = int(round(action * lot))
            self._set_target_amount(slot, ticker, current_amount, target_amount, limit_orders)
            return

        if action is None:
            if limit_orders and bot['mode'] is None:
                self.client.cancel(slot, ticker)
            return

        if isinstance(action, str):
            if 'step' in action:
                self._execute_step_action(slot, ticker, bot, action, current_amount, bp, limit_orders)
            elif action in ('close_long', 'stop_close_long'):
                if current_amount > 0:
                    self._set_target_amount(slot, ticker, current_amount, 0, limit_orders)
                elif limit_orders:
                    self.client.cancel(slot, ticker)
            elif action in ('close_short', 'stop_close_short'):
                if current_amount < 0:
                    self._set_target_amount(slot, ticker, current_amount, 0, limit_orders)
                elif limit_orders:
                    self.client.cancel(slot, ticker)
            elif action == 'close_all':
                if current_amount != 0:
                    self._set_target_amount(slot, ticker, current_amount, 0, limit_orders)
                elif limit_orders:
                    self.client.cancel(slot, ticker)
            elif action == 'open_long':
                self._set_target_amount(slot, ticker, current_amount, lot, limit_orders)
            elif action == 'open_short':
                self._set_target_amount(slot, ticker, current_amount, -lot, limit_orders)

    # ================= ОСНОВНОЙ ТОРГОВЫЙ ЦИКЛ =================

    def _log_error(self, slot: str, ticker: str, err: Exception):
        safe_slot = slot.replace(':', '_')
        log_path = os.path.join(self.folder_error, f"{self.trader_name}_{safe_slot}_{ticker}.txt")
        print(f"[CSTrader ERROR] {slot}:{ticker} -> {type(err).__name__}: {err}")
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now()}\n{traceback.format_exc()}\n{'='*40}\n")

    def run_once(self):
        time_mode = self._check_time()
        if time_mode == 0:
            return

        for (slot, ticker), bot in self.active_bots.items():
            try:
                pos_info = self.client.get_position(slot, ticker)
                if not pos_info.get('isReplicationsDone', True):
                    continue

                orders_info = self.client.get_orders(slot, ticker)
                limit_orders = orders_info.get('limitOrders', [])
                bp = self.client.get_best_prices(slot, ticker)

                current_amount, pos_units, delta = self._calc_pos_and_delta(bot, pos_info, bp)

                tdata = self._collect_tdata(slot, ticker, bot, orders_info, bp)
                te: BaseTE = bot['te']
                pdata = te.preprocessing(tdata)

                action = te(pdata, pos_units, delta)
                action = self._apply_close_on_time(action, time_mode)

                if self.debug_mode:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] {slot}:{ticker} | "
                        f"pos={current_amount} ({pos_units}u) | delta={delta} | action={action}"
                    )

                if isinstance(action, dict):
                    for target_ticker, sub_action in action.items():
                        sub_bot = self.active_bots.get((slot, target_ticker))
                        if sub_bot:
                            sub_pos = self.client.get_position(slot, target_ticker)
                            sub_ord = self.client.get_orders(slot, target_ticker).get('limitOrders', [])
                            sub_bp = self.client.get_best_prices(slot, target_ticker)
                            self._work_action(
                                slot, target_ticker, sub_bot, sub_action,
                                int(sub_pos.get('amount', 0)), sub_bp, sub_ord
                            )
                else:
                    self._work_action(slot, ticker, bot, action, current_amount, bp, limit_orders)

            except Exception as err:
                self._log_error(slot, ticker, err)

