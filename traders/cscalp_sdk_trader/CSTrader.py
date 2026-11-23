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
    Использует декларативную синхронизацию заявок (sync_orders).
    """

    def __init__(
        self,
        group_cfg: Dict[str, Dict[str, Tuple[int, int]]],
        base_url: str = "http://localhost:7777",
        candles_limit: int = 201,
        close_on_time: bool = True,
        close_map: tuple = ((21, 30), (21, 30), (21, 30), (21, 30), (21, 30), (17, 30), (17, 30)),
        debug_mode: bool = False,
    ):
        self.client = CscalpClient(base_url=base_url)
        self.candles_limit = candles_limit
        self.close_on_time = close_on_time
        self.close_time = close_map[datetime.now().weekday()]
        self.debug_mode = debug_mode
        if debug_mode:
            self._init_debug_folders()
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
                    'last_pos': 0,
                    'last_signal': None,  # хранит последний непустой сигнал (pdata, raw_action, action, bp, orders)

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

        for (slot, ticker), bot in self.active_bots.items():
            deadline = time.time() + 15.0
            while True:
                try:
                    bp = self.client.get_best_prices(slot, ticker)
                    if 'step' in bp and 'decimals' in bp and bp['step'] > 0:
                        break
                except Exception:
                    pass

                if time.time() > deadline:
                    raise TimeoutError(f"Не удалось получить стакан и шаг цены для {slot}:{ticker} за 15 сек.")
                time.sleep(0.2)

            step = bp['step']
            decimals = bp['decimals']
            bot['step'] = step
            bot['decimals'] = decimals

            te_cls = bot['te_cls']
            params = bot['params']
            mode = bot['mode']
            bot['te'] = te_cls(ticker, step, mode, *params)
            print(
                f"[CSTrader] Инициализирован {slot}:{ticker} -> {te_cls.__name__} "
                f"(tf={bot['tf']}m, lot={bot['lot']}, step={step}, decimals={decimals})"
            )

    def _init_debug_folders(self):
        date_folder = datetime.now().strftime('%d%m%Y')
        self.debug_folder_main = os.path.join('_logs', 'debug_cs', date_folder)
        self.debug_folder_log = os.path.join(self.debug_folder_main, 'logs')
        self.debug_folder_df = os.path.join(self.debug_folder_main, 'dfs')
        self.debug_folder_fg = os.path.join(self.debug_folder_main, 'fg')
        os.makedirs(self.debug_folder_log, exist_ok=True)
        os.makedirs(self.debug_folder_df, exist_ok=True)
        os.makedirs(self.debug_folder_fg, exist_ok=True)

    def _debug_save(
        self,
        slot: str,
        ticker: str,
        bot: Dict[str, Any],
        pdata: Dict[str, Any],
        pos: int,
        pos_units: int,
        delta: Optional[float],
        raw_action: Any,
        final_action: Any,
        bp: Dict[str, Any],
        orders_info: Dict[str, Any],
        tag: str = '',
    ):
        now = datetime.now()
        now_ms = str(int(time.time() * 1000))
        safe_slot = slot.replace(':', '_')
        suffix = f"_{tag}" if tag else ""
        base_name = f"{safe_slot}_{ticker}_{now_ms}{suffix}"

        # 1. Сохраняем df с индикаторами, если есть
        df = pdata.get('chart') if isinstance(pdata, dict) else None
        if df is not None and not df.empty:
            df.to_csv(os.path.join(self.debug_folder_df, f"{base_name}.csv"))

        # 2. Сохраняем снимок стакана, если запрашивался
        fg = pdata.get('fg') if isinstance(pdata, dict) else None
        if fg is not None:
            import json
            with open(os.path.join(self.debug_folder_fg, f"{base_name}.json"), 'w', encoding='utf-8') as f:
                json.dump(fg, f, ensure_ascii=False, indent=2)

        # 3. Пишем текстовый лог события
        log_file = os.path.join(self.debug_folder_log, f"{safe_slot}_{ticker}.txt")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{now} [{tag}]\n")
            f.write(f"ts_ms: {now_ms}\n")
            f.write(f"strategy: {type(bot['te']).__name__}\n")
            f.write(f"pos: {pos} ({pos_units}u) | delta: {delta}\n")
            f.write(f"bp: {bp}\n")
            f.write(f"orders: {orders_info}\n")
            f.write(f"raw_action: {raw_action}\n")
            f.write(f"final_action: {final_action}\n")
            f.write("=" * 40 + "\n")


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

    def _get_pos_units_for_ticker(self, slot: str, ticker: str) -> int:
        sub_bot = self.active_bots.get((slot, ticker))
        if not sub_bot:
            return 0
        pos_info = self.client.get_position(slot, ticker)
        raw_amount = int(pos_info.get('amount', 0))
        lot = sub_bot['lot']
        if raw_amount == 0:
            return 0
        units = int(round(raw_amount / lot)) if lot else raw_amount
        return units if units != 0 else (1 if raw_amount > 0 else -1)

    def _apply_close_on_time(self, action: Any, time_mode: int, pos_units: int = 0, slot: str = '') -> Any:
        if self.force_mode is None and not self.close_on_time:
            return action

        if isinstance(action, dict):
            return {
                k: self._apply_close_on_time(
                    v,
                    time_mode,
                    self._get_pos_units_for_ticker(slot, k),
                    slot,
                )
                for k, v in action.items()
            }

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
            elif isinstance(action, (int, float)):
                if pos_units == 0:
                    return 0
                if pos_units > 0 and action < 0:
                    return 0
                if pos_units < 0 and action > 0:
                    return 0
                if pos_units > 0 and action > pos_units:
                    return pos_units
                if pos_units < 0 and action < pos_units:
                    return pos_units
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


        if needs is not None:
            if 'chart' in needs:
                tdata['chart'] = self.client.get_candles(slot, ticker, tf_minutes=tf, limit=self.candles_limit)
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
            if raw_amount > 0 and bask > 0:
                delta = (bask - avg_price) / step
            elif raw_amount < 0 and bbid > 0:
                delta = (avg_price - bbid) / step

        return raw_amount, pos_units, delta

    # ================= ФОРМИРОВАНИЕ И СИНХРОНИЗАЦИЯ ЗАЯВОК =================

    def _target_amount_to_orders(self, current_amount: int, target_amount: int) -> List[Dict[str, Any]]:
        """Превращает целевой объем позиции в список заявок с автоценой (price=None)."""
        diff = target_amount - current_amount
        if diff > 0:
            return [{'side': 'BUY', 'amount': abs(diff), 'price': None}]
        elif diff < 0:
            return [{'side': 'SELL', 'amount': abs(diff), 'price': None}]
        return []

    def _step_action_to_orders(
        self,
        bot: Dict[str, Any],
        action: str,
        current_amount: int,
        bp: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Формирует список заявок для спредовых/шаговых команд ('spred_all_step_5', 'open_long_step_2')."""
        parts = action.split('_')
        type_action = parts[0]   # 'spred', 'open', 'close'
        dir_action = parts[1]    # 'long', 'short', 'all'
        step_mult = int(parts[3])

        step = bot['step']
        decimals = bot['decimals']
        lot = bot['lot']

        bbid = bp.get('bestBid', 0.0)
        bask = bp.get('bestAsk', 0.0)
        if bbid <= 0 or bask <= 0 or bask < bbid:
            return []

        buy_price = round(bbid - step_mult * step, decimals) if step_mult > 0 else None
        sell_price = round(bask + step_mult * step, decimals) if step_mult > 0 else None

        orders: List[Dict[str, Any]] = []

        if type_action == 'spred':
            if dir_action == 'long':
                # Набираем лонг до +lot (если еще не набрали) и закрываем в 0 то, что уже налито
                if current_amount < lot:
                    orders.append({'side': 'BUY', 'amount': lot - current_amount, 'price': buy_price})
                if current_amount > 0:
                    orders.append({'side': 'SELL', 'amount': current_amount, 'price': sell_price})

            elif dir_action == 'short':
                # Набираем шорт до -lot (если еще не набрали) и закрываем в 0 то, что уже налито
                if current_amount > -lot:
                    orders.append({'side': 'SELL', 'amount': lot + current_amount, 'price': sell_price})
                if current_amount < 0:
                    orders.append({'side': 'BUY', 'amount': abs(current_amount), 'price': buy_price})

            else:  # 'all' (качели от -lot до +lot)
                if current_amount < lot:
                    orders.append({'side': 'BUY', 'amount': lot - current_amount, 'price': buy_price})
                if current_amount > -lot:
                    orders.append({'side': 'SELL', 'amount': lot + current_amount, 'price': sell_price})

        elif type_action == 'open':
            if dir_action in ('long', 'all') and current_amount < lot:
                orders.append({'side': 'BUY', 'amount': lot - current_amount, 'price': buy_price})
            if dir_action in ('short', 'all') and current_amount > -lot:
                orders.append({'side': 'SELL', 'amount': lot + current_amount, 'price': sell_price})

        else:  # 'close'
            if dir_action in ('long', 'all') and current_amount > 0:
                orders.append({'side': 'SELL', 'amount': abs(current_amount), 'price': sell_price})
            if dir_action in ('short', 'all') and current_amount < 0:
                orders.append({'side': 'BUY', 'amount': abs(current_amount), 'price': buy_price})

        return orders

    def _work_action(
        self,
        slot: str,
        ticker: str,
        bot: Dict[str, Any],
        action: Any,
        current_amount: int,
        bp: Dict[str, Any],
    ):
        lot = bot['lot']
        desired_orders: List[Dict[str, Any]] = []

        if isinstance(action, (int, float)):
            target_amount = int(round(action * lot))
            desired_orders = self._target_amount_to_orders(current_amount, target_amount)

        elif isinstance(action, str):
            if 'step' in action:
                desired_orders = self._step_action_to_orders(bot, action, current_amount, bp)
            elif action in ('close_long', 'stop_close_long'):
                if current_amount > 0:
                    desired_orders = self._target_amount_to_orders(current_amount, 0)
            elif action in ('close_short', 'stop_close_short'):
                if current_amount < 0:
                    desired_orders = self._target_amount_to_orders(current_amount, 0)
            elif action == 'close_all':
                if current_amount != 0:
                    desired_orders = self._target_amount_to_orders(current_amount, 0)
            elif action == 'open_long':
                desired_orders = self._target_amount_to_orders(current_amount, lot)
            elif action == 'open_short':
                desired_orders = self._target_amount_to_orders(current_amount, -lot)

        # Отправляем целевое состояние на C#-сервер (он сам оставит нужное, снимет лишнее и выставит новое)
        self.client.sync_orders(slot, ticker, desired_orders)

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

                orders_info = self.client.get_orders(slot, ticker)
                bp = self.client.get_best_prices(slot, ticker)

                current_amount, pos_units, delta = self._calc_pos_and_delta(bot, pos_info, bp)

                tdata = self._collect_tdata(slot, ticker, bot, orders_info, bp)
                te: BaseTE = bot['te']
                pdata = te.preprocessing(tdata)

                raw_action = te(pdata, pos_units, delta)
                action = self._apply_close_on_time(raw_action, time_mode, pos_units,slot)

                if self.debug_mode:
                    # 1. Если позиция изменилась — сбрасываем на диск и текущий момент, и сигнал-причину из памяти
                    if current_amount != bot['last_pos']:
                        # Сначала пишем сигнал, который привёл к этой сделке (если он был)
                        if bot['last_signal'] is not None:
                            sig = bot['last_signal']
                            self._debug_save(
                                slot, ticker, bot, sig['pdata'],
                                sig['pos'], sig['pos_units'], sig['delta'],
                                sig['raw_action'], sig['action'], sig['bp'], sig['orders'],
                                tag='SIGNAL_CAUSE'
                            )
                        # И пишем сам факт изменения позиции
                        self._debug_save(
                            slot, ticker, bot, pdata,
                            current_amount, pos_units, delta,
                            raw_action, action, bp, orders_info,
                            tag='POS_CHANGED'
                        )
                        bot['last_pos'] = current_amount

                    # 2. В оперативной памяти всегда держим последний активный сигнал (0 мс накладных расходов)
                    if action is not None:
                        bot['last_signal'] = {
                            'pdata': pdata,
                            'pos': current_amount,
                            'pos_units': pos_units,
                            'delta': delta,
                            'raw_action': raw_action,
                            'action': action,
                            'bp': bp,
                            'orders': orders_info,
                        }

                if isinstance(action, dict):
                    for target_ticker, sub_action in action.items():
                        sub_bot = self.active_bots.get((slot, target_ticker))
                        if not sub_bot:
                            continue
                        if target_ticker == ticker:
                            sub_amount = current_amount
                            sub_bp = bp
                        else:
                            sub_pos = self.client.get_position(slot, target_ticker)
                            sub_amount = int(sub_pos.get('amount', 0))
                            sub_bp = self.client.get_best_prices(slot, target_ticker)
                        self._work_action(slot, target_ticker, sub_bot, sub_action, sub_amount, sub_bp)
                else:
                    self._work_action(slot, ticker, bot, action, current_amount, bp)

            except Exception as err:
                self._log_error(slot, ticker, err)
