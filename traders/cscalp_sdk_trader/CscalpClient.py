import time
import requests
import pandas as pd
from typing import List, Optional, Dict, Any


class CscalpServerError(Exception):
    """Ошибка, возвращенная локальным C#-сервером."""
    pass


class CscalpClient:
    def __init__(self, base_url: str = "http://localhost:7777", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Используем Session для переиспользования TCP-соединений (Keep-Alive) — запросы будут идти < 1 мс
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.base_url}{endpoint}"
        resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        data = resp.json()
        if resp.status_code >= 400:
            raise CscalpServerError(data.get("error", f"HTTP {resp.status_code}: {data}"))
        return data

    # --- Управление и подписка ---

    def status(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/status")

    def wait_until_ready(self, slots: List[str], timeout_sec: float = 30.0) -> None:
        """Ожидает готовности всех указанных слотов при старте робота."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            statuses = {s["alias"]: s["isReady"] for s in self.status()}
            if all(statuses.get(slot, False) for slot in slots):
                return
            time.sleep(0.5)
        raise TimeoutError(f"Слоты {slots} не перешли в состояние Ready за {timeout_sec} сек.")

    def subscribe(self, slot: str, tickers: List[str]) -> Dict[str, str]:
        return self._request("POST", "/subscribe", json={"slot": slot, "tickers": tickers})

    # --- Рыночные данные ---

    def get_best_prices(self, slot: str, ticker: str) -> Dict[str, Any]:
        return self._request("GET", "/best-prices", params={"slot": slot, "ticker": ticker})

    def get_orderbook(self, slot: str, ticker: str, depth: int = 20) -> Dict[str, Any]:
        return self._request("GET", "/orderbook", params={"slot": slot, "ticker": ticker, "depth": depth})

    def get_candles(self, slot: str, ticker: str, tf_minutes: int = 5, limit: int = 200, prepare: bool = True) -> pd.DataFrame:
        data = self._request("GET", "/candles", params={
            "slot": slot,
            "ticker": ticker,
            "tf_minutes": tf_minutes,
            "limit": limit
        })
        df = pd.DataFrame(data)
        if not df.empty and "time" in df.columns:
            # Убираем суффикс Z, так как сервер отдаёт биржевое время (МСК)
            df["time"] = pd.to_datetime(df["time"].astype(str).str.rstrip("Z"))

            if prepare:
                df.rename(columns={"time": "ms"}, inplace=True)
                df["direction"] = (df["close"] >= df["open"]).astype(int) * 2 - 1
                df["middle"] = (df["high"] + df["low"]) / 2.0
                df = df.reset_index(drop=True)
                df["x"] = df.index
        return df

    def get_ticks(self, slot: str, ticker: str, limit: int = 500) -> pd.DataFrame:
        data = self._request("GET", "/ticks", params={"slot": slot, "ticker": ticker, "limit": limit})
        df = pd.DataFrame(data)
        if not df.empty and "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"].astype(str).str.rstrip("Z"))
        return df

    def get_clusters(self, slot: str, ticker: str, tf_minutes: int = 5, limit: int = 50) -> pd.DataFrame:
        data = self._request("GET", "/clusters", params={
            "slot": slot,
            "ticker": ticker,
            "tf_minutes": tf_minutes,
            "limit": limit
        })
        df = pd.DataFrame(data)
        if not df.empty and "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"].astype(str).str.rstrip("Z"))
            df.rename(columns={"time": "ms"}, inplace=True)
        return df


    # --- Позиция и торговля ---

    def get_position(self, slot: str, ticker: str) -> Dict[str, Any]:
        return self._request("GET", "/position", params={"slot": slot, "ticker": ticker})

    def get_orders(self, slot: str, ticker: str) -> Dict[str, List[Dict[str, Any]]]:
        return self._request("GET", "/orders", params={"slot": slot, "ticker": ticker})

    def buy_limit(self, slot: str, ticker: str, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """Если price=None, сервер сам встанет лучшим покупателем (или вместе с лучшим в спред)."""
        return self._request("POST", "/order", json={
            "slot": slot,
            "ticker": ticker,
            "side": "BUY",
            "amount": amount,
            "price": price
        })

    def sell_limit(self, slot: str, ticker: str, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """Если price=None, сервер сам встанет лучшим продавцом (или вместе с лучшим в спред)."""
        return self._request("POST", "/order", json={
            "slot": slot,
            "ticker": ticker,
            "side": "SELL",
            "amount": amount,
            "price": price
        })

    def cancel(self, slot: str, ticker: str, order_id: Optional[str] = None) -> Dict[str, Any]:
        """Если order_id=None, снимает все активные заявки по инструменту."""
        return self._request("POST", "/cancel", json={
            "slot": slot,
            "ticker": ticker,
            "orderId": order_id
        })
    
    def sync_orders(self, slot: str, ticker: str, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Декларативная синхронизация заявок:
        orders = [{'side': 'BUY', 'amount': 10, 'price': None}, ...]
        Пустой список [] снимает все заявки по тикеру.
        """
        return self._request("POST", "/sync-orders", json={
            "slot": slot,
            "ticker": ticker,
            "orders": orders
        })

    def get_glass_df(self, slot: str, ticker: str, depth: int = 20, step: Optional[float] = None, decimals: int = 2) -> pd.DataFrame:
        """
        Собирает стакан в привычный DataFrame с колонками:
        ['price', 'amount', 'type_cell', 'vol_per', 'have_order']
        Отсортирован сверху вниз (от дальних асков к дальним бидам), как в терминале.
        """
        ob = self.get_orderbook(slot, ticker, depth=depth)
        orders_data = self.get_orders(slot, ticker)
        limit_orders = orders_data.get("limitOrders", [])

        # Собираем цены, на которых стоят наши активные лимитные заявки
        my_order_prices = {round(float(o["price"]), decimals) for o in limit_orders if o.get("remainAmount", 0) > 0}

        asks = ob.get("asks", [])  # от лучшего аска вверх
        bids = ob.get("bids", [])  # от лучшего бида вниз

        if not asks and not bids:
            return pd.DataFrame(columns=["price", "amount", "type_cell", "vol_per", "have_order"])

        rows = []

        # 1. Аски (переворачиваем, чтобы дальние были сверху, а лучший bask — прямо над спредом)
        for i, item in enumerate(reversed(asks)):
            p = round(float(item["price"]), decimals)
            is_best = (i == len(asks) - 1)
            rows.append({
                "price": p,
                "amount": float(item["amount"]),
                "type_cell": "bask" if is_best else "ask",
                "have_order": p in my_order_prices,
            })

        # 2. Пустые уровни спреда между bask и bbid (если передан step и спред > 1 шага)
        best_ask = round(float(ob.get("bestAsk", 0)), decimals)
        best_bid = round(float(ob.get("bestBid", 0)), decimals)
        if step and step > 0 and best_ask > best_bid:
            spred_ticks = int(round((best_ask - best_bid) / step)) - 1
            for s_idx in range(1, min(spred_ticks + 1, 50)):  # ограничиваем 50 тиками на случай огромных дыр
                p = round(best_ask - s_idx * step, decimals)
                rows.append({
                    "price": p,
                    "amount": 0.0,
                    "type_cell": "spred",
                    "have_order": p in my_order_prices,
                })

        # 3. Биды (сверху вниз, первый уровень — bbid)
        for i, item in enumerate(bids):
            p = round(float(item["price"]), decimals)
            is_best = (i == 0)
            rows.append({
                "price": p,
                "amount": float(item["amount"]),
                "type_cell": "bbid" if is_best else "bid",
                "have_order": p in my_order_prices,
            })

        df = pd.DataFrame(rows)
        max_vol = df["amount"].max() if not df.empty else 0
        df["vol_per"] = ((df["amount"] / max_vol) * 100).round().astype(int) if max_vol > 0 else 0
        return df
