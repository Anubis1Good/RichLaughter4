# PROJECT_CONTEXT — RichLaughter4 (RL4)

> Исчерпывающий технический справочник для ИИ-ассистентов и разработчиков.
> Дата актуализации: 25.11.2026. Репозиторий: `E:\Dev\exchange\RichLaughter4` (Python 3.11, Windows).

---

## 1. Что это за проект

RL4 — фреймворк внутридневной алготрейдинговой торговли на MOEX:

- **strategies/** — 140+ торговых стратегий-классов (`*TE`, Trading Engine) на едином базовом классе `BaseTE`.
- **traders/cscalp_sdk_trader/** — боевой контур: Python-робот, торгующий через локальный C# HTTP-сервер CScalp SDK (`localhost:7777`).
- **testing/** — исторические тестеры (симулятор исполнения с комиссиями, стопами, усреднением).
- **for_strategies/** — библиотека индикаторов (`add_*`-функции над pandas DataFrame).
- **optimization/** — Optuna-оптимизация параметров стратегий.
- **loaders/** — загрузка свечей MOEX ISS.
- **startCS.py** — PyQt5 GUI-лаунчер боевого робота.

Историческая справка: до 23.11.2026 боевой контур был `traders/VT/` (клик-робот, управлял терминалом CScalp эмуляцией мыши — отсюда легаси-классы `OrderCords`/`OrderManager` и зависимости-«автокликеры»). Сейчас удалён; боевой контур — `traders/cscalp_sdk_trader/` через HTTP SDK. Параллельно шёл рефакторинг имён `*EG` → `*TE` (см. §13 «Известные проблемы»).

---

## 2. Общая архитектура и потоки данных

### 2.1 Боевой контур (live)

```
C# CScalp SDK Server (localhost:7777)          ← внешний процесс, не в репозитории
        ▲  HTTP JSON (requests.Session, Keep-Alive)
        │
startCS.py  (PyQt5 GUI: выбор группы, StartTrade/StopTrade, Only Close(-2), Force Close All(-1), Debug Mode)
   └─ CSTradeWorker(QThread)                   ← поток; цикл: run_once() → пауза poll_ms=500мс (шагами по 50мс)
        └─ CSTrader(group_cfg, debug_mode)
             ├─ __init__: клиент CscalpClient; из sgs.pc_groups[group_key] берёт {slot: {ticker: (lot, tf)}}
             │   wait_until_ready(slots) → subscribe(slot, tickers) → get_best_prices (получить step/decimals)
             │   → для каждого тикера init_trader(slot, ticker) из bot_on_ticker → инстанс TE
             └─ run_once() для каждого (slot, ticker):
                  1. get_position / get_orders / get_best_prices
                  2. _calc_pos_and_delta: pos_units = amount/lot; delta = (цена - avg)/step в шагах цены
                  3. _collect_tdata(ticker, needs_info) → tdata  (данные запрашиваются ТОЛЬКО по needs_info)
                  4. pdata = te.preprocessing(tdata)
                  5. raw_action = te(pdata, pos_units, delta)      # BaseTE.__call__
                  6. action = _apply_close_on_time(raw_action, time_mode)   # force_mode / close_on_time
                  7. [debug_mode: «чёрный ящик» — при изменении позиции пишет сигнал-причину]
                  8. _work_action(action|dict) → список желаемых заявок → client.sync_orders(slot, ticker, orders)
```

**Декларативная модель заявок:** каждый цикл стратегия формирует *целевое состояние заявок*; `sync_orders` на сервере сам снимает лишние и выставляет новые. `sync_orders([])` = снять все заявки по тикеру. Если `action is None` или не распознан → уходит `[]` → все активные заявки снимаются (это осознанное поведение).

### 2.2 Исторический контур (backtest)

```
loaders/ApiMoexLoader (apimoex, MOEX ISS)  →  _data_for_tests/**/*.parquet  (1m; конвертация в 5m — utils/work_dfs/convert_tf.py)
        │
history_test.py / today_test.py / current_test.py  →  testing/CheckTETrader    (одна нога)
history_pair_test.py                                →  testing/PairTETrader    (пара/портфель)
        │  check_strategy_faster (быстрый) / check_strategy_window(2) (честный оконный)
        ▼
utils/metrics/equity_metrics.py → словарь метрик; utils/drawing/chart.py → графики
```

### 2.3 Оптимизационный контур

```
optimization/optuna_grops/{main,best,exp,spread,window,bad,archive}_groups.py   (группы стратегий + диапазоны параметров)
        │ group__optuna_optimization.py
        ▼
optimization/OptimizatorOptuna.py  (optuna, multiprocessing по тикерам)
        │  → _test_results/optuna/<strategy>/<ticker>/<ticker>_<strategy>.xlsx (лист total)
        ▼
post_optuna_test_auto.py (WindowTester: оконная перепроверка топ-параметров) → _test_results/post_optuna_results/*.xlsx
utils/processing_result/{best_in_optuna_test, best_in_post_optuna}.py → агрегированные xlsx (ranked/ws_name_agg/ws_type_agg)
```

⚠️ Этот контур в данный момент сломан переименованием EG→TE (см. §13).

---

## 3. Контракт `strategies/BaseTE.py`

`TE` = Trading Engine. Базовый класс всех стратегий. Все 140+ классов наследуются **напрямую** от `BaseTE`.

### 3.1 Сигнатура конструктора

```python
BaseTE(symbol='Test', price_step=None, mode=None, stop=None, take=None, **kwargs)
```

Позиционный порядок **обязателен** — все вызывающие создают TE как `cls(symbol, price_step, mode, stop, take, *strategy_params)`:

| Кто создаёт | Вызов |
|---|---|
| `CSTrader._init_connections_and_strategies` | `te_cls(ticker, step, mode, *params)`, где `params = (stop, take, *strategy_params)` из записи `bot_on_ticker` |
| `CheckTETrader.__init__` | `cls(self.symbol, self.price_step, mode, *params)`, где `params = ws[1]` — второй элемент кортежа `ws = (Class, (stop, take, *strategy_params), mode)` |
| `PairTETrader.__init__` | `cls(main_symbol, main_price_step, mode, *params)` |
| `OptimizatorOptuna.objective` | `cls(symbol, price_step, 1, None, sl_value, tp_value, *params)` ⚠️ см. §13 (сдвиг аргументов) |

Конкретные стратегии объявляют свои параметры как именованные kwargs после `take` и хранят их как `self.<param>` (напр. `self.period`). Наличие атрибутов с подстрокой `period` важно: `add_slice_df` ищет максимальный числовой атрибут с `period` в имени для длины прогрева.

Ключевые атрибуты экземпляра:

| Атрибут | Назначение |
|---|---|
| `needs_info` | `dict` или `None` — декларация требуемых каналов данных (см. §3.3). `None` → tdata пуст |
| `can_long / can_short` | Разрешения направлений; глушатся после стопа (для `type_te in block_type_tes`), восстанавливаются в `check_valid_action` |
| `type_te` | `0` — D-ws (обычные чартовые стратегии), `1` — BD-ws, `2` — spred_glass (стакан/спред). Информационно + влияет на фильтрацию |
| `block_type_tes` | `(0,)` по умолчанию: для стратегий с `type_te=0` действует фильтр `check_valid_action` и блокировка направлений после стопа |
| `order_manager` | `OrderManager()` (легаси VT); реально используется только `PTE31_HYPERION` |
| `amount_sl / amount_tp` | Счётчики срабатываний стопа/тейка (тестер пишет их в метрики `stops/takes`) |
| `last_action` | Последнее возвращённое действие; используется, чтобы не дублировать счётчики SL/TP |
| `stop / take` | Пороги в **шагах цены** (delta); `None` = отключены |
| `problems` | Строковая метка проблемных семейств (`'Mcfly'`, `'Mcfly_FixVanga'`, `'Vanga'`) — только для человека, на логику не влияет |
| `_slice_period / _first_slice` | Кэш длины прогрева для `add_slice_df` |

### 3.2 Жизненный цикл

```
tdata (сырьё от трейдера/тестера)
   │ te.preprocessing(tdata)          # переопределяется: считает индикаторы, режет прогрев
   ▼
pdata (dict; почти всегда {'chart': df}, опционально 'levels', 'fg', 'can_spred')
   │ te.__call__(pdata, pos, delta)
   │   ├─ get_raw_action(pdata)  [fast-режим → get_raw_action_fast(pdata)]
   │   │     row = pdata['chart'].iloc[pdata['idx']]  если fast_mode и есть 'idx'
   │   │     row = pdata['chart'].iloc[-1]            иначе
   │   │     return self._get_action_from_row(row)    # ← основная логика стратегии
   │   ├─ check_valid_action(action, pos)   # только если type_te in block_type_tes
   │   ├─ check_stop(pos, delta, action)    # delta <= -stop → 'stop_close_long'/'stop_close_short'
   │   └─ check_take(delta, action)         # delta >= take → 'close_all'
   ▼
action (str | int/float | dict | List[OrderCords] | None)
```

- Стратегии по умолчанию реализуют **только `_get_action_from_row(row: pd.Series)`** — логика на одной строке df. Fast_mode поддержка получается **автоматически** через базовый `get_raw_action`.
- Переопределять `get_raw_action` целиком не рекомендуется; исключения в кодовой базе: `PTE30_MURKY`, `PTE31_HYPERION` (без fast_mode — легаси), `TestTE`, `CloseAllTE`, `InspectorTE`, все `PAIRTEs` (с поддержкой fast_mode/idx).

### 3.3 `needs_info` — каналы данных (собирает `CSTrader._collect_tdata`)

Проверка по факту **наличия ключа** в dict (значения почти не важны).

| Ключ | Формат значения в needs_info | Что попадает в tdata |
|---|---|---|
| `'chart'` | `True` или имя тикера | `tdata['chart']` = df свечей главного тикера (get_candles, tf из конфига, limit=201) |
| `'charts'` | итерация: строки-тикеры или кортежи `(ticker, tf)` | `tdata['charts']` = **dict {ticker: [df, df, ...]}** — списки датафреймов! |
| `'tapes'` | итерация тикеров | `tdata['tapes']` = dict {ticker: df сделок} (get_ticks, limit=500) |
| `'spred'` | truthy | `tdata['spred']` = int — ширина спреда в тиках: `round((bestAsk-bestBid)/step)` |
| `'full_glass'` или `'orderbook'` | truthy | `tdata['fg']` = df стакана (get_glass_df, depth=20) |
| `'poss'` | итерация тикеров | `tdata['poss']` = dict {ticker: {'amount': int, 'avgPrice': float, 'isReplicationsDone': bool}} |
| `'orders'` | truthy | `tdata['orders']` = ответ `/orders`: `{'limitOrders': [...], 'stopOrders': [...]}` |
| `'clusters'` | truthy | `tdata['clusters']` = df кластеров (get_clusters, tf, limit=50) |

Эталонные примеры: `InspectorTE` (helpTE.py) запрашивает все каналы разом; `PTE31_HYPERION` — `{'chart': True, 'full_glass': True}`.

### 3.4 Формат DataFrame-свечей (`chart` / `charts` / `pdata['chart']`)

Колонки (подтверждено логами InspectorTE, `_logs/inspector/`):

| Колонка | Тип | Значение |
|---|---|---|
| `ms` | datetime64 | Время открытия бара (биржевое время, МСК; из `/candles`, суффикс `Z` отбрасывается) |
| `open, high, low, close` | float | OHLC |
| `volume` | int/float | Объём |
| `direction` | int ±1 | `(close >= open) * 2 - 1` — направление бара |
| `middle` | float | `(high + low) / 2` |
| `x` | int | Порядковый индекс бара (0..N-1, `reset_index`). Тестеры используют как `row_name` сделки |

Каждый DataFrame в `charts[ticker]` — тот же формат. Исторические данные из parquet (ApiMoexLoader) содержат те же колонки (+`vol_coin`, `hour`, `minute`, `weekday`, добавляемые тестерами).

### 3.5 Типы возвращаемых `action` и их семантика

| Тип | Значение | Исполнитель |
|---|---|---|
| `None` | Нет действий → `sync_orders([])` — снять все активные заявки | оба |
| `int/float` | **Целевая позиция в юнитах** для `self.symbol` (0, ±1, ±2, 0.5...). Бой: `target_amount = round(action * lot)` → одна заявка `BUY/SELL` с автоценой (price=None). Тест: `set_position(float(action))` | оба |
| `'open_long'` / `'open_short'` | Целевая позиция ±1 юнит (±lot) | оба |
| `'close_long'` | Закрыть лонг (если pos>0 → 0) | оба |
| `'close_short'` | Закрыть шорт (если pos<0 → 0) | оба |
| `'close_all'` | В плоскую позицию | оба |
| `'stop_close_long'` / `'stop_close_short'` | То же, что close_*, но в тестере с проскальзыванием `slip_stop_delta` и счётчиком `amount_sl` | оба |
| `'<type>_<dir>_step_<N>'` | Лимитные заявки со сдвигом N шагов цены от лучшей цены: buy = `bbid - N*step`, sell = `bask + N*step`. `type` ∈ `spred|open|close`, `dir` ∈ `long|short|all`. `spred` = качели (добрать до +lot по низкой и закрыть имеющееся по высокой и т.п.) | оба (боец: sync_orders; тест: отложенные `Order`, исполнение на следующем баре касанием high/low) |
| `'<type>_<dir>_level'` | Заявки по ценовым уровням из `pdata['levels'] = [top_level, bottom_level]` (боец: buy по ближайшему уровню < bask, sell по ближайшему > bbid; тест: по уровням напрямую). Уровни должны лежать в `pdata` | оба |
| `dict {ticker: sub_action}` | Мультиинструментальные команды (PAIRTEs). Боец: каждый ключ — тикер **того же слота**, позиция/цены запрашиваются по нему отдельно, `pdata['levels']` пробрасывается. Тест (PairTETrader): числа умножаются на `quantity_map[s]`, поддержаны `close_all`/`open_long`/`open_short` | оба |
| `List[OrderCords]` | ЛЕГАСИ VT (клик-робот): `order_manager.get_spred_orders(fg, ...)`. ⚠️ В текущем CSTrader **не исполняется** (попадает в ветку «неизвестное действие» → `sync_orders([])`, т.е. снятие всех заявок). Единственный источник — `PTE31_HYPERION` | — |
| `'open_all'` | Указан в `__docs/possible_actions.py`, но **не обработан** ни бойцом, ни тестером (на деле = снятие заявок) | — |

Примечания:
- Строковые команды с `'step'`/`'level'` парсятся по подстроке (`'step' in action` / `'level' in action`) — см. `_step_action_to_orders` / `_level_action_to_orders` в CSTrader и `work_step_action` / `work_level_action` в CheckTETrader.
- dict-действия **не проходят** `check_valid_action` (проходят насквозь); `check_stop`/`check_take` применяются к dict как к целому (заменяют его на строку при срабатывании).
- `_apply_close_on_time` обрабатывает dict рекурсивно по каждому тикеру с его позицией.

### 3.6 `pos`, `delta` и встроенные стоп/тейк

- `pos` — позиция в **юнитах** (боец: `amount/lot`; тестер: дробное число юнитов).
- `delta` — текущий результат в **шагах цены** (`price_step`), >0 — в плюсе:
  - боец: лонг `(bask - avgPrice)/step`, шорт `(avgPrice - bbid)/step`; 0 позиции → `None`;
  - тестер: по `close` бара; при стопе берётся худший экстремум бара (`low`/`high`), при `auto_take` — искусственное срабатывание тейка на экстремуме, умноженном на `take * auto_take`.
- `check_stop`: при `delta <= -stop` возвращает `'stop_close_long'`/`'stop_close_short'` (по знаку pos), инкрементирует `amount_sl` (1 раз на подряд идущие стопы) и глушит `can_long`/`can_short`, если `type_te in block_type_tes`.
- `check_take`: при `delta >= take` возвращает `'close_all'`, инкрементирует `amount_tp`.

### 3.7 `add_slice_df(df, period=None)`

Обрезает первые `N+1` строк прогрева. `N` = максимум по числовым атрибутам с `'period'` в имени (или явный `period`). Вызывается **стратегиями внутри `preprocessing`** (после добавления индикаторов). Кэшируется `_slice_period` на экземпляре. В оконном тесте окно должно быть длиннее прогрева, иначе действия не начнутся (`df` обнулится). Стратегии без индикаторов (PAIRTEs) `add_slice_df` не вызывают.

### 3.8 Stateful-стратегии (PAIRTEs)

`LTEP1_SINGULARITY`, `UTEP1_SPARTACUS`, `UTEP2_PROMETHEUS` хранят собственный `self.positions` (dict тикер → позиция), обновляемый из `tdata['poss']` в `preprocessing`. В PairTETrader fast-режиме тестер синхронизирует `ws.positions` из своих `trade_data` перед каждым шагом (`hasattr(ws, 'positions')`). Свои `__init__` kwargs: `symbol2`, `lot1/lot2`, `funding/hour_fund/minute_fund` и параметры грида; `stop/take` принудительно `None`.

---

## 4. Спецификация C# SDK API (по `traders/cscalp_sdk_trader/CscalpClient.py`)

Базовый URL: `http://localhost:7777` (конструктор `CscalpClient(base_url, timeout=10.0)`). Транспорт: `requests.Session` (Keep-Alive). Любой HTTP ≥400 → исключение `CscalpServerError(data['error'])`.

### 4.1 Эндпоинты

| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| GET | `/status` | — | `List[{alias: str, isReady: bool}]` |
| POST | `/subscribe` | `{"slot": str, "tickers": [str]}` | `Dict[str, str]` |
| GET | `/best-prices` | `slot, ticker` | `{bestAsk: float, bestBid: float, step: float, decimals: int}` |
| GET | `/orderbook` | `slot, ticker, depth` (по умолч. 20) | `{asks: [{price, amount}...] (от лучшего вверх), bids: [{price, amount}...] (от лучшего вниз), bestAsk, bestBid}` |
| GET | `/candles` | `slot, ticker, tf_minutes, limit` | JSON-массив объектов с полями `time` (ISO, суффикс `Z`), `open, high, low, close, volume` |
| GET | `/ticks` | `slot, ticker, limit` | массив `{time, price, amount, direction}`; `direction` — **строка** `'Buy'/'Sell'` |
| GET | `/clusters` | `slot, ticker, tf_minutes, limit` | массив `{time, price, amount, direction, highPrice, lowPrice, maxTickPrice, maxTickAmount}` |
| GET | `/position` | `slot, ticker` | `{amount: int (сырые лоты), avgPrice: float, isReplicationsDone: bool}` |
| GET | `/orders` | `slot, ticker` | `{'limitOrders': [{orderId, price, remainAmount, ...}], 'stopOrders': [...]}` |
| POST | `/order` | `{"slot", "ticker", "side": "BUY"/"SELL", "amount": float, "price": float|null}` | dict. `price=None` → сервер сам встанет лучшим покупателем/продавцом (обёртки `buy_limit`/`sell_limit`) |
| POST | `/cancel` | `{"slot", "ticker", "orderId": str|null}` | `orderId=None` → снять все активные заявки по инструменту |
| POST | `/sync-orders` | `{"slot", "ticker", "orders": [{"side", "amount", "price"|null}]}` | **Декларативная синхронизация**: сервер оставит совпадающее, снимет лишнее, выставит новое. `[]` = снять всё |

Служебное: `wait_until_ready(slots, timeout_sec=30)` — поллинг `/status` до `isReady=True` по всем слотам (шаг 0.5с).

### 4.2 Подготовка данных на клиенте

- `get_candles(..., prepare=True)` → df с колонками `ms, open, high, low, close, volume, direction, middle, x` (см. §3.4). `prepare=False` — только парсинг времени.
- `get_ticks`, `get_clusters` → df с колонками из таблицы (время парсится, суффикс `Z` отбрасывается; у кластеров `time→ms`).
- `get_glass_df(slot, ticker, depth=20, step, decimals=2)` — стакан как «в терминале», сверху вниз: дальние аски → **`bask`** → пустые уровни спреда (`type_cell='spred'`, если передан `step` и спред > 1 шага; максимум 50) → **`bbid`** → биды. Колонки (фактический порядок, подтверждён логами InspectorTE): `price, amount, type_cell, have_order, vol_per`; `type_cell ∈ {ask, bask, bid, bbid, spred}`; `vol_per` — процент от максимального объёма (0..100); `have_order` — стоит ли на цене наша заявка (`remainAmount > 0`).

`slot` — алиас терминала/подключения CScalp (напр. `'LiteInvest:stockLI'`); тикеры группируются по слотам.

---

## 5. Боевой контур в деталях

### 5.1 Конфигурации

- **`traders/cscalp_sdk_trader/sgs.py`** — `pc_groups`: какие группы терминалов запускаются. Формат: `{GROUP: {slot: {TICKER: (lot, tf)}}}`. `base_tf = 5`. Для парных роботов второй инструмент указывается здесь (в `bot_on_ticker` можно не указывать или поставить `BaseTE`).
- **`traders/cscalp_sdk_trader/bot_on_ticker.py`** — какие стратегии торгуют: `{slot: {TICKER: (StrategyClass, params_tuple, mode)}}`, где `params_tuple = (stop, take, *strategy_params)` (передаются позиционно в TE). Функция `init_trader(slot, ticker)` возвращает запись или `(BaseTE, (), None)` как фолбэк. Комментарии над строками — журнал результатов стратегии в бою.
- **`startCS.py`** — PyQt5 GUI. `CSTradeWorker(QThread, poll_ms=500)` создаёт `CSTrader(pc_groups[group_key], debug_mode)` и крутит `run_once()`; остановка через `requestInterruption` (пауза дробится по 50 мс). Кнопки: StartTrade/StopTrade, `Only Close (-2)`, `Force Close All (-1)` (взаимоисключающие, передаются через `set_force_mode` с QMutex), чекбокс Debug Mode (по умолчанию вкл.). При старте очищает `_logs/error_logs_CSTrader`.

### 5.2 `CSTrader`

Конструктор: `candles_limit=201`, `close_map` по умолчанию `((21,30)*5, (17,30)*2)` — час:минута закрытия по дням недели (пн–пт, сб, вс); `debug_mode` создаёт `_logs/debug_cs/<ddmmyyyy>/{logs,dfs,fg}`.

**`_check_time() → int`** — режим времени/принуждения:
- `force_mode` (кнопки GUI) перекрывает всё: `None` штатно, `-2`, `-1`.
- Иначе: до 7:00 → `0` (не торгуем, `run_once` выходит); с 7:00 до закрытия → `1`; в последний час (`chour == close_time[0]`) → `-2` (только закрытие); после `close_time` → `-1` (закрыть всё).

**`_apply_close_on_time(action, time_mode, pos_units, slot)`**:
- `dict` — рекурсивно по каждому тикеру (позиция запрашивается по тикеру).
- `-1` → всегда `'close_all'`.
- `-2` → строковые: `open_long→close_short`, `open_short→close_long`, `spred…→close…`, `open_all→close_all` (замены подстрок); числовые: цель в сторону увеличения экспозиции → `0`; цель дальше текущей позиции → клампится к текущей `pos_units` (уменьшить можно, нарастить нельзя).
- При `close_on_time=False` и `force_mode=None` — passthrough.

**`_calc_pos_and_delta`**: `raw_amount` (лоты) → `pos_units = round(raw_amount / lot)` (0 → знак raw_amount); `delta` в шагах цены к лучшей встречной цене (§3.6).

**`run_once()`** — на каждый `(slot, ticker)`: исключения ловятся и пишутся в `_logs/error_logs_CSTrader/CSTrader_<slot>_<ticker>.txt` (трейсбек), цикл по остальным тикерам продолжается.

**dict-действие**: для каждого ключа-тикера того же слота: если ключ == текущий тикер — используются текущие `current_amount`/`bp`, иначе запрашиваются `/position` и `/best-prices` по тикеру, после чего `_work_action` с общими `levels` из `pdata`.

**`debug_mode` («чёрный ящик»)**: без записи на диск в обычном цикле; в памяти `bot['last_signal']` хранится последний непустой сигнал (pdata/pos/delta/raw_action/action/bp/orders). При изменении позиции (`current_amount != bot['last_pos']`) на диск сбрасываются: сигнал-причина (`tag='SIGNAL_CAUSE'`) и факт изменения (`tag='POS_CHANGED'`) — CSV датафрейма (`dfs/`), JSON стакана (`fg/`), текстовый лог (`logs/`). Цель — восстановить причину сделки постфактум.

### 5.3 Разбор команд в `_work_action` (боец)

| Вход | Логика |
|---|---|
| `int/float` | `target_amount = round(action * lot)`; разница → одна заявка `BUY/SELL`, `price=None` (автоцена) |
| `'close_long'`, `'stop_close_long'` | если pos>0 → цель 0 |
| `'close_short'`, `'stop_close_short'` | если pos<0 → цель 0 |
| `'close_all'` | цель 0 (если pos≠0) |
| `'open_long'` | цель +lot; `'open_short'` → цель −lot |
| `'..._step_N'` | `_step_action_to_orders`: спред/открытие/закрытие лимитками на `bbid−N·step` (buy) / `bask+N·step` (sell) до объёма ±lot |
| `'..._level'` | `_level_action_to_orders`: уровни из `pdata['levels']`, округляются к шагу цены; buy по ближайшему уровню строго ниже `bask`, sell по ближайшему строго выше `bbid` (мейкерские) |
| остальное (None, List[OrderCords]) | пустой список → `sync_orders([])` → снять все заявки |

---

## 6. Исторические тестеры

### 6.1 `testing/CheckTETrader.py` — одна нога

Конструктор: `CheckTETrader(df | path, ws=(Class, (stop, take, *params), mode) | экземпляр BaseTE, fee=0.001, symbol, close_on_time=True, close_map=((22,30)*5,(17,30)*2), measure_time, use_tqdm, window=60, days_mode=None, slip_stop_delta=1, auto_take=1)`. `fee` — доля от цены за одну сторону (0.0002 = 0.02%); `price_step` определяется автоматически (`utils/work_dfs/other.get_price_step` через НОД разниц цен). `add_time_features` добавляет `hour/minute/weekday`. `days_mode=(d,...)` — обнуляет `close_map[d]` → `(0,0)`, т.е. день пропускается (форс-закрытие с 00:00).

Модель позиции (`trade_data`): дробные позиции и пирамидинг; `_add_position` — средневзвешенная `open_price`; `_reduce_position` — частичное закрытие, входная комиссия списывается пропорционально объёму (`open_fee`), выходная комиссия на весь закрываемый объём; `total_wfees_per` — PnL в % с комиссией (на объём). Стоп-закрытие умножает результат на `slip_stop_delta` (имитация проскальзывания).

`exec_orders` — исполнение отложенных лимиток (для `step`/`level`-команд): лонг-заявка исполняется, если `low <= price`, шорт — если `high >= price` (в начале следующего шага).

**Три режима прогона:**

| Метод | Как работает | Применение |
|---|---|---|
| `check_strategy_faster(history_bars=None, debug=False)` | `preprocessing` вызывается **1 раз** на полном df; далее цикл по строкам с `fast_pdata = {'chart': df, 'idx': i, 'fast_mode': True}`. Окно уменьшается на длину срезанного прогрева. Быстро (O(n)) | Оптимизация (Optuna), массовые прогоны |
| `check_strategy_window(normalization=False)` | Ускоренный оконный тест (бывший `check_strategy_window2`): массивы цен предвычислены, нормализация векторизована; `preprocessing` на срезе `df.iloc[i-window:i+1]` для каждого бара | Финальная проверка стратегии |
| `check_strategy_window_old(normalization=False)` | «Честный» оконный тест без предрасчёта — медленная версия `check_strategy_window` | Референс/сверка |

`normalization=True` — делит `open/high/low/close/middle/volume` окна на их максимум (для ML-стратегий); уровни из pdata пересчитываются обратно в реальные цены.

`delta` в тестере (§3.6): при срабатывании стопа берётся худший экстремум бара; при `auto_take` — если бар доходил до `take*auto_take`, delta фиксируется на этом уровне (ранний тейк по экстремуму).

`close_on_time` — форс `'close_all'` после `close_map[weekday]` (проверяется `hour/minute` строки).

**Метрики:**
- `get_statistics()` → dict: `total` (без комиссии), `total_wfee`/`twf_per` (с комиссией, абс/%), `count`, `fees`, `max_profit/min_profit` (по unclosed кривой), `max_dropdown/max_dropup`, `days`, `eq_day` (в день), `win_rate`, `mean/median/min/max_eq` (по закрытым сделкам).
- `process_old_type_result()` → `(trades, equity, equity_fee, longs, shorts, closes)`: `trades` содержит всё из статистики + `curve_*` из `equity_curve_metrics` + `curve_composite` + `curve_lex`; используется Optuna.
- `print_statistics()`, `plot_transaction()`, `plot_equity()`, `plot_chart(convert_tf)`, `plot_chart_and_sequtity(help_info='step_equity'|'pos'|'unclosed'|'complex'|'sltp')`.

### 6.2 `testing/PairTETrader.py` — пары/портфель

Конструктор: `PairTETrader(dfs: {symbol: path|df}, ws, quantity=None, fee=0.0002, close_on_time, close_map, window=150, days_mode)`. Первый ключ `dfs` — главный инструмент (`main_symbol`), его `price_step` передаётся в TE.

- `_prepare_base_df`: datetime `ms`, сортировка, дедупликация (`keep='last'`), `hour/minute/weekday`.
- `_align_dfs`: пересечение меток `ms` всех инструментов → синхронные датафреймы с переустановленным `x`.
- `quantity_map`: множители лотов по инструментам (по умолчанию 1.0).
- Учёт позиции и комиссий — по-ноге (`_add_symbol_pos`/`_reduce_symbol_pos`/`_set_symbol_pos`), логика идентична CheckTETrader; `max_poss[s]` — максимальная экспозиция.
- **`check_strategy_faster()`**: один `preprocessing` на полных данных (`full_tdata = {'chart': main, 'charts': {s: [df]}, 'poss': ...}`), затем fast-цикл с `'fast_mode': True, 'idx'`; `ws` вызывается как `ws(fast_pdata, 0, None)` — парные стратегии управляют позициями через собственный `self.positions` (синхронизируется из `trade_data` перед каждым шагом). Действие — dict по инструментам.
- **`check_strategy_window()`**: честный оконный прогон; `poss_units[s] = {'amount': pos/quantity, 'avgPrice': open_price}` передаётся в `tdata['poss']`; окна `chart`/`charts` режутся синхронно.
- `_work_pair_action`: числа → `set_pos` с умножением на `quantity_map`; `close_all` → 0; `open_long` → +quantity; `open_short` → −quantity.
- Метрики: `get_portfolio_equity(with_fee, unclosed)` — сумма кривых по инструментам; `get_statistics()` — портфельные (`total_no_fee/total_wfee/fees/count/max_profit/min_profit/max_dropdown/days/eq_day/total_max_pos/eq_day_per_pos/curve_composite/curve_lex`); `print_statistics()`; `plot_chart_and_equity(symbol, convert_tf, help_info='couple_complex'|'couple_pos'|'single')`.

### 6.3 Точки входа тестов и константы

- **`testing/test_constants.py`**: `PATH_DF` (тестовый parquet ALRS 5m), `WINDOW=80`, `MAIN_FEE=0.0002`, `DAYS_MODE=(3,5,6)` (пропуск чт/сб/вс), `DAYS_MODE_HT=(5,6)`, `SLIP_STOP_DELTA=1`.
- **`history_test.py`** — ручной тест одной стратегии: загрузка parquet → `CheckTETrader` → `check_strategy_window2()` → статистика → график → `check_strategy_window()` → сравнение.
- **`history_pair_test.py`** — ручной тест парных стратегий (TATN/TATNP): `UTEP1_SPARTACUS` faster+window через `PairTETrader`; `close_on_time=False` в шапке.

---

## 7. Библиотека индикаторов (`for_strategies/`)

**Конвенции**: `add_*(df, ...)` **мутируют df на месте** (создают колонки) и возвращают df — цепочки вида `df = add_rsi(add_bollinger(df, ...), ...)`. Периоды передаются именованными параметрами. Каузальность: функции должны использовать только текущие и прошлые строки (rolling со shift, где нужно). Функции `get_*` / `_`-префиксованные — возвращают значения, df не мутируют.

| Модуль | Содержимое (ключевое) |
|---|---|
| `classic_indicators.py` (32 ф.) | RSI/RSI-TW, SMA, EMA, KAMA, Bollinger, Donchian (`max_hb/min_hb/avarege`), Keltner, MA-envelope, std/LR-каналы, ATR, ATR-канал, Parabolic SAR, MACD, Stochastic, CCI, Williams %R, MFI, Awesome Oscillator, ROC, Ultimate Osc., CMO, RVI, Choppiness (`chop`), ADX, Volume Profile, Pivot Points, Chaikin Volatility, Supertrend (требует колонку `atr`), fractals |
| `classic_indicators2.py` | Регime-метрики: fractal dimension index (`fdi`), Hurst (`hurst`), VHF, variance ratio (`vr/vr_z`), range compression z-score (`rc_z`), percentile rank (`pct_rank`), композитный `blender_score` |
| `pva_indicators.py` (36 ф.) | Каналы: vodka, kusuruken (channel/bb), kvas, kefir, cascade, static, hope, std-fractals, smooth; фракталы/пики: average_fractals(_window), extremes/delta_fractals, mean/ext_on_fractals (`top_mean/bottom_mean`), plus_delta_fc(_window), exp_pdfc(_window) (серии `pdf_up/down`, `ave_up/down`...); quantile_params/ext_params (`bottom_q/top_q`, `oversold/overbought`); velcro; hl/pc_stair_fast; integrity_index (`ii`); assessment_motion_index; stable_ma_direction; benefit (оценка выгоды входов); BBI |
| `pva2_indicators.py` | perdirlong/real_perdirlong (долгосрочное направление), каналы Перчана (perchan_sma/mid/two), zebra/zechan, velcro_bb, ratio_2ext (+rolling), per_above_sma (`pas`), diff_ext_channel; колонки «педалей» (`pedal`, `real_pedal`, `wpedal`, `diff_pedals`...) |
| `zigzag_indicators.py` (63 ф., самый большой) | Зигзаги: precent/dynamic/van/window_zigzag, `add_zigzag180826`, `add_percent_zz190826`, оконный `add_zigzag_window_260926` (`zp1..N/wzp1..N`, `idx_wzp*`, `trend_sma`, ...); пики: dzz_peaks, percent_zz_peaks, shift_zz_peaks, mean/plusdelta/exp_plusdelta_peaks (+варианты `_wzz260926`); каналы/цели по зигзагу (`bzp*`, `ssl/lsl` — стоп-лоссы); **pattern18** (`add_pattern18_dzz_czd`, `add_pattern18_zzw_260926`, `pattern18_code` — VSA-подобные паттерны: joc/btc/bui/bti/double_top/bottom/upthrust/spring/sow/sos/...); анализ (`add_analys_dzz*`) |
| `vsa_indicators.py` (22 ф.) | CDV (cumulative delta volume), vsai/dvsai/cdvsai (+MA/границы), стоп-действия (real/vsa/simple/aggressive/balanced), volume zones, rails/allowance_rails, reversal_patterns (`rev_pat`) |
| `ml_indicators.py` | `add_segmented_regression_from_end` (сегментная LR-регрессия → upper/lower_channel), `add_find_similar_pattern_lite` (поиск похожего паттерна истории → forecast_high/low, per_fs), `add_linear_regression_window` (скользящий LR → lr_upper/lower/slope_pct) |
| `arb_indicators.py` | `get_percent_diff_window(df1, df2, window, smooth, kind)` — % разница двух инструментов для парных стратегий (Series `desc`) |
| `help_indicators.py` | over_bb, attached_bb, big_volume (`is_big`), sc_and_buffer, buffer_add/sub (`top_buff/bottom_buff`), ideal_pos |
| `other_indicators.py` | vangerchik (`max_vg/min_vg`), zigzag_stair |
| `notdone_indicators.py` | Черновики: find_point_by_price, add_some |
| `fix_params.py` | Нормировка периодов под бюджет `max_period`: `fix_supertrend_params`, `fix_two_periods(_hm)`, `fix_three_periods_hm` |
| `help_dtypes/actions_cls.py` | `OrderCords` (dataclass заявки клик-робота: send_cords/send_simple/send_smart/reset_cords/reset_simple/close_all_simple/close_all_smart/no_action) и `OrderManager` (`get_spred_orders(fg, direction, min_spred, large_open, large_close, n_orders, min_step)` — легаси VT; используем только `PTE31_HYPERION`) |

#### Модули `zai_*` (серия каузальных индикаторов, добавлена 25.11.2026)

Все функции соблюдают конвенции раздела 11.2 (мутируют df + return df, только конечные скользящие окна, без ewm/рекурсивных фильтров/глобальных статистик, событийные колонки с ограниченным `ffill(limit)`). Имена колонок сгруппированы префиксами (`ichi_`, `aroon_`, `evr_`, `fvg_`, `vwap_`, `pz_` и т.п.) и не пересекаются с остальным проектом (коллизия со старыми `swing_high/swing_low` обойдена через `smc_swing_*`).

| Модуль | Функции (колонки) |
|---|---|
| `zai_classic_indicators.py` | `add_ichimoku` (каузальный Ichimoku без Chikou; `ichi_tenkan/kijun/senkou_a/senkou_b/cloud_top/cloud_bottom`), `add_aroon` (`aroon_up/down/diff`, векторный argmax), `add_donchian_width` (`dcw_width`, флаг `dcw_squeeze` по квантилю), `add_elder_ray` (SMA-вариант; `elder_bull/bear/dir`), `add_vortex` (`vtx_plus/minus/diff`), `add_chaikin_money_flow` (`cmf_value`) |
| `zai_vsa_indicators.py` | `add_effort_result` (`evr_effort/result/ratio`), `add_stopping_volume` (`sv_close_pos`, `sv_up_climax`, `sv_down_climax`, `sv_stopping`), `add_no_demand_supply` (`nds_low_vol/no_demand/no_supply`), `add_climax_churn` (`churn_vol_hi/bar/dir`), `add_volume_absorption` (`abs_at_top/bottom`, `abs_sign`); фон объёма/спреда берётся со `shift(1)` |
| `zai_smc_indicators.py` | `add_fvg` (3-я свеча, `fvg_bull/bear`, середины гэпа `fvg_*_mid`), `add_swing_points` (каузальные свинги с подтверждением через `left_bars`; `smc_swing_high/low` на баре подтверждения + `smc_swing_*_last` с `ffill(limit=memory)`), `add_order_blocks` (OB через FVG + объёмный фильтр; `ob_bull/bear_top/bot`), `add_liquidity_sweep` (`sweep_up/down`, `sweep_level_*`; уровень строго из прошлого), `add_premium_discount` (по rolling-диапазону; `pd_pos/pd_premium/pd_discount`) |
| `zai_volume_indicators.py` | `add_vwap_daily` (дневной VWAP по `ms.dt.normalize` + σ-полосы `vwap_value/std/up/dn`; значение зависит только от баров текущего дня), `add_obv_net` (оконная дельта OBV + сигнальная SMA; `obv_net/net_sig`), `add_force_index` (`fi_raw/ma/norm`), `add_ease_of_movement` (`eom_raw/ma`; нулевой диапазон/объём → 0.0), `add_relative_volume` (`rvol_ratio/z/spike`, фон со `shift(1)`) |
| `zai_ml_indicators.py` | `add_return_autocorr` (`rac_corr`), `add_market_entropy` (нормированная энтропия доходностей окна; `ent_norm`, ~0.4 мс/бар rolling.apply), `add_trend_r2` (векторный R² + наклон %; `tr2_r2`, `tr2_slope_pct`), `add_return_zscore` (`rz_value`, `rz_extreme`), `add_price_dynamics` (`dyn_slope`, `dyn_accel`) |
| `zai_arb_indicators.py` | Сигнатура `(df1, df2, ...) -> df1`, dfs выровнены по строкам (ValueError иначе): `add_pair_zscore` (`pz_spread/pz_zscore`, kind='log'/'pct'), `add_pair_beta_spread` (скользящая бета + хеджированный остаток; прогрев 2×window), `add_pair_corr_regime` (`pcr_corr`, AR(1)-phi `pcr_phi`, полупериод `pcr_half_life`), `add_pair_spread_oscillators` (BB + SMA-RSI на %-спреде; `pso_*`) |

Каталога `indicators/` в репозитории **нет** — библиотека индикаторов живёт в `for_strategies/`.

---

## 8. Утилиты (`utils/`) и загрузчики (`loaders/`)

| Модуль | Содержимое |
|---|---|
| `utils/work_dfs/load_df.py` | `simple_load_df(raw_file)` — parquet через `pd.read_parquet` (нужен pyarrow), иначе csv |
| `utils/work_dfs/other.py` | `get_price_step(df)` — шаг цены инструмента через НОД разниц уникальных цен |
| `utils/work_dfs/convert_tf.py` | `convert_timeframe(df, timeframe, ...)` — ресемплинг OHLCV в другой TF (пересчёт direction/middle, `weekday/hour/minute`) |
| `utils/metrics/equity_metrics.py` | `equity_curve_metrics(eq)` → dict метрик кривой (total_return, slope/r2/rmse, max_dd, jump_ratio, sharpe, calmar, linearity_score); `composite_score(total_return, metrics)` — взвешенный скор; `lex_score(em, tr_eps, dd_limit)` — лексикографический скор для Optuna (прибыль → качество; штраф при dd>limit или tr<=0) |
| `utils/drawing/chart.py` | `draw_hb_chart_fast(df)` (быстрый high-low график), `draw_bars_chart(df)`, `draw_bars_chart_wo_vol(df, ax)` |
| `utils/drawing/indicators.py` | `draw_wzp(df)` — ломаная зигзага по колонкам `wzpN`/`idx_wzpN` |
| `utils/processing_result/best_in_optuna_test.py` | Скрипт: агрегация результатов Optuna (`_test_results/optuna/**.xlsx`) в `total_optuna.xlsx` (total/ranked/ws_name_agg/ws_type_agg) |
| `utils/processing_result/best_in_post_optuna.py` | Скрипт: агрегация пост-оптимизационных результатов в `total_post_optuna_aggregated.xlsx` (6 листов) |
| `loaders/ApiMoexLoader.py` | `ApiMoexLoader(symbol, board='TQBR', ...)`: `load_data(start, end, timeframe)` (apimoex → свечи MOEX ISS; tf: 1/10/60/24/7/31), `processing_df` (rename `begin→ms`, `value→vol_coin`, direction/middle/x, hour/minute/weekday), `save_df(...)` → parquet/csv в `_data_for_tests/data_from_moex` |

---

## 9. Оптимизация (`optimization/`)

- **`OptimizatorOptuna.py`** — класс `OptimizatorOptuna(test_folder='_data_for_tests/data_small', fee, max_period=55, close_on_time, close_map, bottom_limit=100, top_limit=1000, n_trials, n_jobs, sl_min_pct...tp_max_pct, use_window_test, window_size=60, normalization=True, metric='total_fee_per', days_mode, slip_slope_delta, use_stop=0, use_take=0)`.
  - `param_options` — опции по каждому параметру: `(min, max, step)` → suggest_int/float; `(min, max)` → шаг 1; кортеж/список значений → suggest_categorical.
  - SL/TP: `use_stop`: `1` → всегда оптимизируется, `-1` → None, `0` → сначала categorical. Пересчёт % → шаги цены через `trader.price_step_per`.
  - На триал: создание стратегии → `trader.ws = strategy; reload_data()` → `check_strategy_faster` (или `check_strategy_window`) → `process_old_type_result()`; количество сделок вне `[bottom_limit, top_limit]` → `TrialPruned()`. Часть метрик — минимизируемые (`metric_sign=-1`), study всегда maximize.
  - Результаты: `_test_results/optuna/<strategy>/<ticker>/<ticker>_<strategy>.xlsx`; multiprocessing `Pool` по тикерам; `optimize_multiple_groups(groups)`.
- **`optuna_grops/`** (каталог с опечаткой): `opt_params.py` — глобальные границы (`min_period=5, max_period=70, max_percent_threshold=0.5, ...`); `main_groups.py` — активная группа (~20 конфигов, параметры вида `(min,max,step)`/категории каналов `"DC","VG","BB","VC","WC","SC"` и видов «педалей»); `best/exp/spread/window/bad/archive_groups.py` — прочие группы. ⚠️ Все импортируют `strategies.all_egs` и используют `PEG*/UEG*/SEG*/VEG*` имена (см. §13).

---

## 10. Реестр модулей и стратегий

### 10.1 Слои боевого контура (`traders/cscalp_sdk_trader/`)

| Модуль | Класс/объекты | Назначение |
|---|---|---|
| `CscalpClient.py` | `CscalpClient`, `CscalpServerError` | HTTP-клиент C# SDK (§4) |
| `CSTrader.py` | `CSTrader` | Боевой цикл: сбор tdata → TE → фильтры времени → sync_orders (§5) |
| `bot_on_ticker.py` | `bot_on_ticker` (dict), `init_trader()` | Регистрация какие стратегии на каких тикерах |
| `sgs.py` | `pc_groups`, `base_tf` | Группы терминалов: слоты, лоты, TF |
| `startCS.py` (корень) | `CSTradeWorker`, `MainWindow` | PyQt5 GUI-лаунчер |

### 10.2 Стратегии (`strategies/`)

Все классы наследуются напрямую от `BaseTE`. Соглашение имён: `<Семья><Номер>_<Имя>`; суффикс `P` в семье — парные (`PAIRTEs`). `strategies/all_tes.py` — единый реестр (`from ... import *`), его импортируют тестеры.

| Файл | Классы (кол-во) | Тематика |
|---|---|---|
| `BaseTE.py` | `BaseTE` | Базовый контракт (§3) |
| `all_tes.py` | — | Реестр-импортёр всех семей |
| `helpTEs/helpTE.py` | `TestTE` (демо spred-по-уровням, type_te=2), `CloseAllTE`, `InspectorTE` (слепок всех данных в `_logs/inspector/`) | Служебные |
| `helpTEs/debugTE.py` | `debugTE` (инвертированный фрактальный сигнал), `DebugMean` (пишет debug_data, не торгует), `DebugAction` (трейс действий, переопределяет `__call__`) | Отладка |
| `PTEs/PTE1_9.py` (7) | `PTE2_DDCrWork`, `PTE2_DDCrWork_level_test` (демо levels), `PTE4_U4/U5/U6` (канал+RSI-осциллятор, kind_channel/kind_rsi), `PTE8_DOBBY`, `PTE8_LOBSTER` (BB + big volume; LOBSTER type_te=1) | Donchian/каналы + осцилляторы |
| `PTEs/PTE10_19.py` (38) | `PTE11_KUSURUKEN/_RAYMIYAMOTO/_SHIZUKAMARIKAWA/_SAYATAKAGI/_ALICEMARASATO` (kusuruken BB + 2 RSI + chop-зоны), `PTE13_DWDDCr/_DUNE` (DC+AO), `PTE14_RWDDCr/_REGAL/_RANGER/_RENEGADE` (ranger-фильтры chop/adx), `PTE15_ANNA/_SILVANA` (DC shift + end_up/down), `PTE16_LEORIC/_CHEN/_ARTANIS` (benefit-оценка), `PTE17_PHOENIX/_AIUR/_PROBIUS/_ZEALOT/_TEMPLAR/_ARCHON/_SELENDIS/_ALDERA` (velcro + DC + rsi), `PTE18_REXXAR2/_UTER/_UTER2/_DIABLO2/_VARIAN2/_ANDUIN/_BLAZE` (supertrend/ami), `PTE19_ANUBARAK/_YREL/_VALEERA/_ZERATUL/_JOHANNA/_CASSIA/_IMPERIUS` (hope/cascade каналы + rsi) | Каналы + осцилляторы + zigzag-гейты |
| `PTEs/PTE20_29.py` (14) | `PTE20_HOGGER`, `PTE21_WHITEMANE/_AURIEL/_MALTHAEL`, `PTE22_BERSERK/_SONYA`, `PTE23_ULTIMATUM`, `PTE24_BRIGHTWING/_DEATHWING` (⚠️ у DEATHWING группы перепутаны), `PTE25_TASSADAR`, `PTE26_UNKNOWN/_JUNKRAT/_GAZLOWE` (integrity_index) | Фракталы + zigzag + pattern18 |
| `PTEs/PTE30_39.py` (4) | `PTE30_MURKY` (type_te=2, `'spred'`, переопределяет get_raw_action), `PTE30_ETC` (`open_*_step_N`), `PTE30_ETC2` (`spred_*_step_N`), `PTE31_HYPERION` (type_te=2, `full_glass`, возвращает `List[OrderCords]` ⚠️ легаси) | Спред/стакан |
| `PTEs/PTE40_ai.py` (7) | Тренд/канальные с гистерезисом и фильтрами боковика (вход по кроссоверу через shift(1)-колонки, выход через центральную линию с запасом `exit_buff`, фильтры chop/ADX): `PTE40_DCRISE` (пробой Дончиана), `PTE40_TWINMA` (кроссовер 2 SMA с ADX), `PTE40_KELTBREAK` (пробой Кельтнера), `PTE40_BBVOLUME` (пробой BB на большом объёме), `PTE40_TRENDRIDER` (пирамидинг 0/±1/±2 по SMA+ADX+DC), `PTE40_STEPGUARD` (качели `spred_all_step_N` во флэте, `close_all` на пробое), `PTE40_LEVELTWIN` (качели `'spred_all_level'` по уровням Дончиана через `pdata['levels']`) | Трендовые/канальные |
| `LTEs/LTE1.py` (11) | `LTE1_CC2` (10 осцилляторов + очки), `LTE1_OKROSHKA` (адаптивный порог rsi/chop), `LTE1_PIN`, `LTE1_BIBI2` (квантили осциллятора), `LTE1_IGOGOSHA2` (ext-зоны), `LTE1_IRONANNY2`, `LTE1_PHOGA/_PHOGA2/_BORSCH/_PHOBO` (supertrend+volume, type_te=1), `LTE1_LAKSAe` | Осцилляторные входы |
| `LTEs/LTE2.py` (8) | `LTE2_HOTS/_DRINKER/_ALKASH/_FENNEC/_LYNX/_DRG` (BB/vodka + DC + rsi + буферы), `LTE2_LOGAN` (static channel + chop), `LTE2_MONSTER` (adx-тренд или close_all, type_te=1) | Каналы с буферами |
| `LTEs/LTE3.py` (1) | `LTE3a_LOTR` (percentile rank ширина) | Режим-стратегия |
| `LTEs/LTE4_ai.py` (7) | `LTE4_VORTEXFALL` (vortex+CMF развороты), `LTE4_SQUEEZEPOP` (squeeze→Aroon-пробой), `LTE4_CLOUDFADE` (контртренд к облаку Ишимоку + vortex), `LTE4_TRIPLEOSC` (score из Aroon+Elder+CMF), `LTE4_FADER` (числовая лестница усреднения 0/±1/±2), `LTE4_SPREADEATER` (MM-качели `spred_*_step_N` по тренд-состоянию Aroon), `LTE4_LEVELFADE` (качели по уровням облака, `pdata['levels']` + `'spred_all_level'`, гейт на `dcw_squeeze`) — на индикаторах `zai_classic_indicators` | Осцилляторные/адаптивные/контртрендовые |
| `WTEs/WTE1_9.py` (6) | `WTE3_BATYA` (спред/объём сигнал), `WTE4_DOG/_PUPPY` (RSI по CDV), `WTE7_PARADOX2` (dvsai+BB), `WTE8_MOUSE` (DC+velcro+cdvsai+adx), `WTE9_` | VSA/дельта-объём |
| `WTEs/WTE10_19.py` (2) | `WTE10_sleep`, `WTE10_` (BB + big bar + reversal patterns; ⚠️ двойной np.where) | VSA-паттерны |
| `WTEs/WTE11_ai.py` (5) | Объёмные стратегии на паттернах (zai_volume + vsai + SMA): `WTE11_VWAP_REVERSION` (возврат внутрь std-полос дневного VWAP при затухании объёма, выход на VWAP; требует window ≥ max баров дня в оконном тесте), `WTE11_CLIMAX_FADE` (фейд кульминации: rvol_z + длинная свеча + vsai, вход против на баре-подтверждении), `WTE11_OBV_BREAKOUT` (пробой экстремума + obv_net над сигнальной SMA, выход при «ложном выносе» с буфером exit_buff), `WTE11_FORCE_PULLBACK` (откат в тренде: провал fi_norm за -fi_thr за flush_window баров + разворот на turn_eps), `WTE11_VOL_SQUEEZE_STEP` (качели `spred_all_step_N` при rvol≤quiet_rvol, `close_all` на всплеске rvol_z≥spike_z) | Объёмные/VSA |
| `UTEs/UTE1_9.py` (32) | `UTE4_CANADIAN/_FALCON2/_PELICAN2` (фрактальные окна), `UTE5_HAWK`, `UTE6_DODO/_DUELDODO/_VULTURE/_PIGEON/_ADVENTURE/_SURVIVALIST/_SHERIFF` (GGD: быстрые SMA границ + BB + adx/pdf), `UTE7_*` (12 шт — те же на оконных фракталах), `UTE8_AVENGER/_SOLDIER` (zigzag + pattern18 с групповыми порогами), `UTE9_BIRDWATCHER2/_GRAVY2/_POLITICIAN/_ASTRAL/_MEDIUM/_TRACKER` (пики оконного зигзага + pas) | Окно-фракталы/зигзаги |
| `UTEs/UTE10_ai.py` (7) | SMC/зональные (zai_smc + adx/chop/fdi): `UTE10_FVGRETEST` (ретест середины FVG по импульсу, выход при перекрытии зоны), `UTE10_LIQSWEEP` (реверс после sweep за подтверждённый свинг), `UTE10_ORDERBLOCK` (отскок от OB с подтверждением свечи), `UTE10_PREMDISCOUNT` (возврат к равновесию из глубокой Discount/Premium), `UTE10_SWINGBREAK` (BOS-кроссовер за swing_last при adx/fdi-режиме), `UTE10_FALCONPRO` (UTE4_FALCON2 + adx-тренд + pd_pos-зона + выход на середине канала — автор просил тренд-версию), `UTE10_SHERIFFPRO` (UTE6_SHERIFF + режим chop: GGD только в боковике и правильной pd-зоне, пробои только в тренде) | SMC/зональные |
| `STEs/STE_CA1_9.py` (5) | `STE1_LITE`, `STE2/_FAST/_ULTRA`, `STE3_FORCE` (stair/ema/detach/adx + BB) | Канальные ступени |
| `STEs/STE_ML10_19.py` (5) | `STEML2_NEWAVE/_TUNNELER/_SID/_TRENDWAVE` (segmented LR / similar pattern / LR window), `STEML2b_RAPTOR` (обучение sklearn DecisionTreeClassifier прямо в preprocessing, predict → `signal`) | ML |
| `VTEs/VTE1.py` (4) | `VTE1_MERCURY/_VENUS/_EARTH/_MOON` — большие диспетчеры по `pattern18` с уровнями bzp*/zp* и стопами ssl/lsl | Pattern18-диспетчеры |
| `PAIRTEs/PLTE1.py` (1) | `LTEP1_SINGULARITY` (грид-хедж по ценам, dict-позиции, fast_mode/idx) | Парные |
| `PAIRTEs/PUTE1.py` (2) | `UTEP1_SPARTACUS` (desc = % расхождение пары, funding-правило), `UTEP2_PROMETHEUS` (многоуровневый грид desc) — dict-позиции, fast_mode/idx | Парные |

`problems`-метки у отдельных стратегий (`'Mcfly'`, `'Mcfly_FixVanga'`, `'Vanga'`) — маркеры проблемных семейств для человека.

### 10.3 Прочее

| Путь | Назначение |
|---|---|
| `__docs/possible_actions.py` | Справочник допустимых строковых action |
| `__docs/` (xlsx/txt) | RoadMap, fee_prop, trade_data — человеческие документы |
| `__bats/*.bat` | Лаунчеры: `startCS.bat`, `group_optuna.bat`, `pos_optuna_test.bat` |
| `archive/sample_use.py` | Пример работы с `CscalpClient` (подписка, candles, buy_limit) |
| `compare_charts.py` | Интерактивная визуализация окна баров с индикаторами |
| `compare_df.py` / `compare_files.py` | Сравнение значений индикаторов/CSV между прогонами (верификация каузальности) |
| `some_downloads.py` | Массовая загрузка 1m-свечей MOEX (~36 тикеров, 30 дней) |
| `work_on_indicators.py` / `_visual.py` | Песочница индикаторов |
| `test.py` | Проверка живого SDK-сервера: GET `/debug-cluster-type` |
| `current_test.py` / `today_test.py` / `post_optuna_test_auto.py` / `group__optuna_optimization.py` | Массовые прогоны и оптимизация (⚠️ битые импорты, §13) |

---

## 11. Правила написания новых стратегий и индикаторов

### 11.1 Новая стратегия (шаблон)

```python
from for_strategies.classic_indicators import add_rsi
from for_strategies.pva_indicators import add_donchan_channel  # пример
from strategies.BaseTE import BaseTE


class PTE40_MYSTRAT(BaseTE):
    "stop=None, take=None, period=20"  # docstring = оптимизируемые параметры (для Optuna-групп)

    def __init__(self, symbol='Test', price_step=None, mode=None,
                 stop=None, take=None, period=20):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart': self.symbol}   # или True; см. §3.3
        self.period = period                        # параметры — только как self-атрибуты

    def preprocessing(self, tdata):
        pdata = {}
        df = tdata['chart']
        df = add_donchan_channel(df, self.period)   # цепочка add_* из for_strategies
        df = self.add_slice_df(df)                  # срез прогрева (по макс. period)
        pdata['chart'] = df
        return pdata

    def _get_action_from_row(self, row):
        if row['low'] <= row['min_hb']:
            return 'open_long'
        if row['high'] >= row['max_hb']:
            return 'open_short'
        return None
```

**Обязательные правила:**

1. **Каузальность / отсутствие заглядывания в будущее.** В `_get_action_from_row` используются только значения текущей строки (индикаторы в `preprocessing` должны быть каузальны: rolling с `shift(1)` там, где значения включают текущий бар). Проверять сравнением `check_strategy_faster` vs `check_strategy_window` (у оконного режима нет возможности заглянуть вперёд — результаты должны совпадать; утилиты `compare_df.py`/`compare_files.py` помогают сравнивать колонки между прогонами).
2. **`fast_mode` и `idx`.** Не переопределяйте `get_raw_action` — реализуйте `_get_action_from_row(row)`: базовый класс сам разрулит fast-режим (строка по `idx`) и оконный (последняя строка). Если всё же переопределяете — обязаны поддержать `pdata.get('fast_mode') and 'idx' in pdata → chart.iloc[idx]` (образец: `UTEP1_SPARTACUS`). Анти-образец: `PTE30_MURKY`/`PTE31_HYPERION` (в fast-режиме считают по последней строке → в быстрых тестах смещение сигналов).
3. **`preprocessing` чист относительно действий.** Он вызывается и в fast-режиме 1 раз, и в оконном на каждый бар — не должен зависеть от позиции/дельты и не должен торговать. Индикаторные колонки — только через `add_*` или `df['col'] = df[...].rolling(...)`. Результат — `{'chart': df}` (+ опционально `'levels'`, `'fg'`, `'can_spred'`).
4. **Прогрев.** Храните периоды как `self.period*`-атрибуты и вызывайте `add_slice_df(df)` — иначе первые бары будут с NaN и действия нулевые. Параметры нормируйте `fix_*_params` (бюджет `max_period`) — важно для Optuna.
5. **Контракт action** — только типы из §3.5. Не возвращайте `open_all` (не исполняется) и `List[OrderCords]` (в бою = снятие заявок).
6. **Именование.** Семья + номер + имя: `PTE*` (price-канальные), `LTE*` (осцилляторные), `WTE*` (VSA/объём), `UTE*` (фракталы/зигзаг), `STE*` (ступени/ML), `VTE*` (pattern18), `PAIRTEs/…P*` (парные). Класс регистрируется в `strategies/all_tes.py` (`from strategies.<Семья>.<файл> import *`).
7. **Конструктор.** Первые пять аргументов — всегда `symbol, price_step, mode, stop, take` (позиционные вызовы снаружи!), свои параметры после — именованные с дефолтами.
8. **Доступ к данным вне chart** — только декларативно через `needs_info` (§3.3): стакан (`'full_glass'` → `tdata['fg']`), спред (`'spred'` → `tdata['spred']`), ленты (`'tapes'`), позиции (`'poss'`), заявки (`'orders'`), кластеры (`'clusters'`). Не держите состояние, синхронное с рынком, кроме случаев как PAIRTEs (`self.positions` из `tdata['poss']`).
9. **Детерминированность сравнений (float-шум).** Pandas rolling-статистики накапливают ошибку ~1e-13 от точки старта расчёта, поэтому `check_strategy_faster` (индикаторы на полном df) и `check_strategy_window` (на срезе) дают значения, совпадающие лишь с точностью ~1e-13. Сравнения непрерывных индикаторов с нулём или с порогом, лежащим точно на сетке данных (кратные шага цены), могут переворачиваться этим шумом → расхождение результатов тестов. Правила: (а) все пороги — буфером от нуля (`vtx_diff > 0.05`, а не `> 0`); (б) пороги в единицах шага цены брать полуцелыми (`1.5 * price_step`): значения SMA-семейства лежат на сетке `step/period`, и полуцелый кратный недостижим точно; (в) счёт очков — через `int(...)` для каждого слагаемого: `np.bool_ + np.bool_` в NumPy — логическое ИЛИ, а не сумма; (г) после написания обязательно сравнивать `check_strategy_faster` и `check_strategy_window2` (PnL и число сделок должны совпасть).
10. **Проверка перед боем:** прогон в `history_test.py` (window2 + window совпадают), отладка сигналов `DebugAction`/`DebugMean`/`InspectorTE` (слепок данных), затем запись в `bot_on_ticker.py` (параметры: `(stop, take, *strategy_params)`) и `sgs.py` (`(lot, tf)`).

### 11.2 Новый индикатор (`for_strategies/`)

- Функция `add_<name>(df, period=..., ...) -> pd.DataFrame`: мутирует df, добавляя колонки, и возвращает df (входит в цепочки `df = add_a(add_b(df))`).
- Каузальность: только прошлые/текущие бары; никаких `.shift(-N)`, future-окон, центрированных средних; глобальные нормировки по всему df (min/max по всей истории) запрещены.
- Имена колонок — стабильные и уникальные (стратегии обращаются по имени через `row['col']`); при коллизиях — переименование в стратегии.
- Период — параметр; внутри допустимы хелперы `fix_*_params`.
- Если индикатор возвращает значение для строки (не колонки) — префикс `get_`, df не мутировать.

### 11.3 Правило для парных стратегий

`needs_info = {'chart': symbol, 'charts': (symbol2,), 'poss': (symbol, symbol2)}`; возврат — `dict {ticker: int_pos}`; `preprocessing` обновляет `self.positions` из `tdata['poss']`; поддержка `fast_mode/idx` обязательна (см. `UTEP1_SPARTACUS`); тест — только `PairTETrader` (`history_pair_test.py`).

---

## 12. Точки входа, каталоги и данные

| Точка входа | Что делает |
|---|---|
| `startCS.py` (+ `__bats/startCS.bat`) | Боевой GUI |
| `history_test.py` | Ручной тест одной стратегии |
| `history_pair_test.py` | Ручной тест парной стратегии |
| `group__optuna_optimization.py` (+ `__bats/group_optuna.bat`) | Оптимизация группы (⚠️ §13) |
| `post_optuna_test_auto.py` (+ `__bats/pos_optuna_test.bat`) | Оконная перепроверка (⚠️ §13) |
| `some_downloads.py` | Загрузка данных MOEX |
| `test.py` | Пинг SDK-сервера |

Каталоги: `_data_for_tests/` (данные: `_temp` — рабочие parquet, `data_stock_1m`, `data_small` — для оптимизации), `_logs/` (`csf`, `debug_cs`, `error_logs_CSTrader`, `inspector`), `_test_results/` (optuna, post_optuna_results, today), `__docs/`, `__bats/`, `archive/`.

---

## 13. Известные проблемы и долги (на 25.11.2026)

1. **Рефакторинг EG→TE не завершён.** Битые импорты: `optimization/OptimizatorOptuna.py`, `today_test.py`, `current_test.py`, `post_optuna_test_auto.py` — `from testing.CheckEGTrader import CheckEGTrader` (файл удалён, есть только `testing/CheckTETrader.py` с классом `CheckTETrader`); `optimization/optuna_grops/*.py`, `current_test.py`, `post_optuna_test_auto.py` — `from strategies.all_egs import *` (есть только `all_tes.py`), и все имена в группах — `PEG*/UEG*/SEG*/VEG*` (реальные классы — `PTE*/UTE*/STE*/VTE*`). `today_test.py` и `current_test.py` также импортируют `traders.VT.bot_on_ticker` (удалён). Работают только `history_test.py`, `history_pair_test.py`, `startCS.py`.
2. **`OptimizatorOptuna.objective` — сдвиг аргументов:** `strategy_class(symbol, price_step, 1, None, sl_value, tp_value, *params)` — `None` занимает позицию `stop`, из-за чего `sl_value` попадает в `take`, а `tp_value` — в первый стратегический параметр. Плюс `check_strategy_window(window=...)` не принимает `window` (в `CheckTETrader` — только `normalization`). Возрождать оптимизацию — после фикса.
3. **`PTE30_MURKY` / `PTE31_HYPERION`** переопределяют `get_raw_action` без поддержки `fast_mode/idx`.
4. **`List[OrderCords]`** (PTE31_HYPERION, OrderManager) — легаси клик-робота; в текущем CSTrader не исполняется (результат = снятие всех заявок по тикеру).
5. `'open_all'` описан в `__docs/possible_actions.py`, но не обрабатывается ни бойцом, ни тестерами.
6. **`WTE10_sleep` / `WTE10_`**: второй `np.where` перезаписывает первый `signal` (вероятный баг).
7. **`PTE24_DEATHWING`**: группы long/short в action перепутаны местами (осознанный/неосознанный инверт — проверять при использовании).
8. `debugTE.DebugAction.print_actions()` ссылается на несуществующий `self.actions_log`.
9. В `check_strategy_faster` окно уменьшается на длину срезанного прогрева, но стратегии с `needs_info=None`/без slice дают рассинхрон `sync_step_data` (заполняется нулевой ценой).

---

## 14. Зависимости (`requirements.txt`, обновлён 25.11.2026)

Импортируемые сторонние пакеты (по скану AST всех .py, 73 файла): `pandas`, `numpy`, `scipy` (classic/ml_indicators, equity_metrics), `matplotlib`, `requests` (CscalpClient, ApiMoexLoader), `apimoex`, `optuna`, `scikit-learn` (STEML2b_RAPTOR), `tqdm`, `psutil`, `PyQt5` (startCS), `xlsxwriter`/`openpyxl` (Excel-отчёты), `pyarrow` (parquet, косвенно).

Удалены как неиспользуемые (легаси автокликера VT и пр.): `opencv-python`, `PyDirectInput`, `pyautogui`, `keyboard`, `torch`, `plotly`, `pytz`, `python-dotenv`, `fastparquet`. Версии закреплены по рабочей среде (см. файл).

Архивный `archive/sample_use.py` импортирует `cscalp_client` — локальный пакет старого проекта, в требования не входит.
