"""zai_smc_indicators — индикаторы Smart Money Concepts, СТРОГО каузальные.

Вся классика SMC (swing-фракталы, order blocks) в «наивном» виде требует будущих баров
(right-side окна). Здесь каждый сигнал появляется ТОЛЬКО после подтверждения прошлыми барами:
- FVG фиксируется строго на 3-й свече паттерна;
- свинги подтверждаются с задержкой left_bars (сравнение только с ПРЕДЫДУЩИМИ барами);
- «последний уровень» хранится ограниченным forward-fill (не более memory баров), поэтому
  значение любого бара полностью определяется окном длиной чуть больше left_bars + memory.

Конвенции проекта (см. PROJECT_CONTEXT.md, разделы 7 и 11.2):
- add_*(df, ...) мутирует df на месте и возвращает df;
- нужны только стандартные колонки OHLCV; служебные колонки проекта не перезаписываются.
"""

import numpy as np
import pandas as pd


def _confirmed_swings(series: pd.Series, left_bars: int, higher: bool) -> pd.Series:
    """Свинг-экстремумы с задержкой подтверждения left_bars.

    Пик на баре c: экстремум строго больше/меньше left_bars ПРЕДЫДУЩИХ баров (окно c-left..c-1).
    Значение появляется в колонке на баре c + left_bars (shift(+left_bars)) — будущего нет.
    """
    prev = series.shift(1).rolling(left_bars, min_periods=left_bars)
    prev_ext = prev.max() if higher else prev.min()
    is_swing = (series > prev_ext) if higher else (series < prev_ext)
    raw = pd.Series(np.where(is_swing, series, np.nan), index=series.index)
    return raw.shift(left_bars)


def _shift_bool(arr: np.ndarray, k: int) -> np.ndarray:
    if k == 0:
        return arr.copy()
    out = np.zeros(len(arr), dtype=bool)
    out[k:] = arr[:-k]
    return out


def _shift_float(arr: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if k < len(arr):
        out[k:] = arr[:-k]
    return out


def add_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Columns: ['fvg_bull', 'fvg_bear', 'fvg_bull_mid', 'fvg_bear_mid']

    Fair Value Gap, фиксируется СТРОГО на 3-й свече: бычий FVG на баре i, если low[i] > high[i-2]
    (гэп между телами 1-й и 3-й свечи трёхбарного импульса); медвежий — если high[i] < low[i-2].
    fvg_bull_mid / fvg_bear_mid — середина гэпа (магнит цены и уровень лимитного входа).
    Используются только бары i-2..i — ноль заглядывания в будущее.

    Пример стратегии: после fvg_bull выставить лимитную покупку на fvg_bull_mid (стоп под low[i-1],
    цель — следующий smc_swing_high_last); fvg_bear — зеркально для шорта.
    """
    h2 = df['high'].shift(2)
    l2 = df['low'].shift(2)
    df['fvg_bull'] = df['low'] > h2
    df['fvg_bear'] = df['high'] < l2
    df['fvg_bull_mid'] = np.where(df['fvg_bull'], (df['low'] + h2) / 2.0, np.nan)
    df['fvg_bear_mid'] = np.where(df['fvg_bear'], (df['high'] + l2) / 2.0, np.nan)
    return df


def add_swing_points(df: pd.DataFrame, left_bars: int = 3, memory: int = 20) -> pd.DataFrame:
    """Columns: ['smc_swing_high', 'smc_swing_low', 'smc_swing_high_last', 'smc_swing_low_last']

    Каузальные свинг-хаи/лои: экстремум на баре c подтверждается ТОЛЬКО на баре c + left_bars
    (строгое сравнение с left_bars предыдущими барами) — колонка smc_swing_high/smc_swing_low
    содержит уровень свинга на баре ПОДТВЕРЖДЕНИЯ (задержка left_bars, будущего нет).
    *_last — уровень последнего подтверждённого свинга с ограниченной памятью (ffill не более
    memory баров) — зависит только от последних left_bars + memory баров, инвариантен к окну.

    Пример стратегии: лимитный вход на ретест smc_swing_low_last (стоп под уровень, выход на
    smc_swing_high_last); структурный пробой: close > smc_swing_high_last -> 'open_long'.
    """
    sh = _confirmed_swings(df['high'], left_bars, higher=True)
    sl = _confirmed_swings(df['low'], left_bars, higher=False)
    df['smc_swing_high'] = sh
    df['smc_swing_low'] = sl
    df['smc_swing_high_last'] = sh.ffill(limit=memory)
    df['smc_swing_low_last'] = sl.ffill(limit=memory)
    return df


def add_order_blocks(df: pd.DataFrame, vol_period: int = 20, vol_mult: float = 1.1) -> pd.DataFrame:
    """Columns: ['ob_bull_top', 'ob_bull_bot', 'ob_bear_top', 'ob_bear_bot']

    Order Blocks через FVG (каузальная версия): на баре i формирования бычьего FVG ищем последнюю
    падающую свечу среди i-2..i-1 (предпочтение ближайшей к импульсу) с объёмом >= vol_mult ×
    среднего фонового объёма — её тело становится зоной спроса [ob_bull_bot; ob_bull_top].
    Медвежий FVG — зеркально: тело последней бычьей свечи = зона предложения. Зона появляется
    одновременно с FVG (на 3-й свече) и не перерисовывается.

    Пример стратегии: buy limit внутри [ob_bull_bot; ob_bull_top] на ретесте, стоп за нижнюю
    границу зоны, цель — smc_swing_high_last; цена ниже ob_bull_bot при закрытии бара
    -> зона слита, 'close_long'.
    """
    o = df['open'].to_numpy(dtype=float)
    c = df['close'].to_numpy(dtype=float)
    v = df['volume'].to_numpy(dtype=float)
    mv = df['volume'].shift(1).rolling(vol_period, min_periods=vol_period).mean().to_numpy()

    body_top = np.maximum(o, c)
    body_bot = np.minimum(o, c)
    is_dn = c < o
    is_up = c > o
    vol_ok = v >= vol_mult * mv  # NaN в mv -> False

    fvg_bull = (df['low'] > df['high'].shift(2)).to_numpy(dtype=bool)
    fvg_bear = (df['high'] < df['low'].shift(2)).to_numpy(dtype=bool)

    # Бычий OB: происхождение — падающая свеча i-1 (приоритет) или i-2
    c1 = fvg_bull & _shift_bool(is_dn, 1) & _shift_bool(vol_ok, 1)
    c2 = (~c1) & fvg_bull & _shift_bool(is_dn, 2) & _shift_bool(vol_ok, 2)
    df['ob_bull_top'] = np.where(c1, _shift_float(body_top, 1), np.where(c2, _shift_float(body_top, 2), np.nan))
    df['ob_bull_bot'] = np.where(c1, _shift_float(body_bot, 1), np.where(c2, _shift_float(body_bot, 2), np.nan))

    # Медвежий OB: происхождение — бычья свеча i-1 (приоритет) или i-2
    c1 = fvg_bear & _shift_bool(is_up, 1) & _shift_bool(vol_ok, 1)
    c2 = (~c1) & fvg_bear & _shift_bool(is_up, 2) & _shift_bool(vol_ok, 2)
    df['ob_bear_top'] = np.where(c1, _shift_float(body_top, 1), np.where(c2, _shift_float(body_top, 2), np.nan))
    df['ob_bear_bot'] = np.where(c1, _shift_float(body_bot, 1), np.where(c2, _shift_float(body_bot, 2), np.nan))
    return df


def add_liquidity_sweep(df: pd.DataFrame, left_bars: int = 3, memory: int = 20) -> pd.DataFrame:
    """Columns: ['sweep_up', 'sweep_down', 'sweep_level_up', 'sweep_level_down']

    Liquidity Sweep (снятие ликвидности): бар прокалывает уровень ПОСЛЕДНЕГО подтверждённого
    свинга (уровень строго из прошлого, shift(1) от ограниченно-заполненного ряда свингов), но
    закрывается обратно по свою сторону уровня — стоп-ликвидация, ложный пробой.
    sweep_up — прокол свинг-хая вверх с закрытием под ним (медвежий); sweep_down — прокол
    свинг-лоу вниз с закрытием над ним (бычий).

    Пример стратегии: sweep_down -> 'open_long' со стопом под low бара, цель — smc_swing_high_last;
    sweep_up -> 'open_short' (стоп над high бара). Связка sweep_down + abs_at_bottom
    (zai_vsa_indicators) — самый сильный сетап разворота.
    """
    sh = _confirmed_swings(df['high'], left_bars, higher=True).ffill(limit=memory)
    sl = _confirmed_swings(df['low'], left_bars, higher=False).ffill(limit=memory)

    lvl_up = sh.shift(1)  # уровень строго из прошлого
    lvl_dn = sl.shift(1)
    df['sweep_up'] = (df['high'] > lvl_up) & (df['close'] < lvl_up)
    df['sweep_down'] = (df['low'] < lvl_dn) & (df['close'] > lvl_dn)
    df['sweep_level_up'] = np.where(df['sweep_up'], lvl_up, np.nan)
    df['sweep_level_down'] = np.where(df['sweep_down'], lvl_dn, np.nan)
    return df


def add_premium_discount(df: pd.DataFrame, period: int = 50, premium: float = 0.7,
                         discount: float = 0.3) -> pd.DataFrame:
    """Columns: ['pd_pos', 'pd_premium', 'pd_discount']

    Premium/Discount относительно СКОЛЬЗЯЩЕГО диапазона (rolling max/min за period — никакой
    глобальной статистики по всей истории): pd_pos = (close − rolling_low) / (rolling_high −
    rolling_low) ∈ [0; 1]. pd_premium — цена в верхнем сегменте диапазона (>= premium);
    pd_discount — в нижнем (<= discount).

    Пример стратегии: pd_discount и бычий sweep/поглощение -> 'open_long'; pd_premium и
    sv_up_climax/churn_bar -> 'open_short'; нейтральная зона (0.3..0.7) — не входить.
    """
    r_hi = df['high'].rolling(period).max()
    r_lo = df['low'].rolling(period).min()
    width = (r_hi - r_lo).replace(0, np.nan)
    df['pd_pos'] = (df['close'] - r_lo) / width
    df['pd_premium'] = df['pd_pos'] >= premium
    df['pd_discount'] = df['pd_pos'] <= discount
    return df
