"""zai_volume_indicators — продвинутые объёмные индикаторы, отсутствующие в проекте.

Конвенции проекта (см. PROJECT_CONTEXT.md, разделы 7 и 11.2):
- add_*(df, ...) мутирует df на месте и возвращает df;
- строгая каузальность: дневной VWAP сбрасывается по дате ms (значение внутри дня зависит только
  от баров текущего дня), все сглаживания — конечные скользящие окна (SMA вместо EMA/рекурсивных
  фильтров, чтобы расчёт на любом окне давал идентичный результат);
- нужны только стандартные колонки OHLCV (+ ms для дневного VWAP); служебные колонки не трогаем.
"""

import numpy as np
import pandas as pd


def add_vwap_daily(df: pd.DataFrame, band: float = 2.0) -> pd.DataFrame:
    """Columns: ['vwap_value', 'vwap_std', 'vwap_up', 'vwap_dn']

    Каузальный дневной VWAP со сбросом в начале торгового дня (группировка по ms.dt.normalize) и
    полосами стандартного отклонения: vwap_std — объёмно-взвешенная дисперсия типичных цен
    (high+low+close)/3 относительно текущего vwap, копившаяся ВНУТРИ текущего дня; vwap_up/dn —
    vwap ± band × std. Значение любого бара зависит только от баров его дня — заглядывания нет.

    Пример стратегии: откат close к vwap_value сверху с бычьим закрытием -> 'open_long';
    close > vwap_up — перегрев, 'close_long' / 'open_short'; vwap как intraday-якорь для
    average-стратегий проекта.
    """
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    day = df['ms'].dt.normalize()
    v = df['volume']

    cs_pv = (tp * v).groupby(day).cumsum()
    cs_v = v.groupby(day).cumsum().replace(0, np.nan)
    df['vwap_value'] = cs_pv / cs_v

    dev = tp - df['vwap_value']
    var_num = ((dev * dev) * v).groupby(day).cumsum()
    df['vwap_std'] = np.sqrt(var_num / cs_v)
    df['vwap_up'] = df['vwap_value'] + band * df['vwap_std']
    df['vwap_dn'] = df['vwap_value'] - band * df['vwap_std']
    return df


def add_obv_net(df: pd.DataFrame, period: int = 20, sig_period: int = 50) -> pd.DataFrame:
    """Columns: ['obv_net', 'obv_net_sig']

    Оконный аналог OBV: чистый объём за окно — obv_net = Σ sign(Δclose) × volume за period баров.
    Это «скорость» классического OBV (накопительная кривая OBV не инвариантна к окну, а её
    оконная дельта — да). obv_net_sig — сигнальная SMA от obv_net; SMA вместо EMA ради строгой
    каузальности и инвариантности к окну.

    Пример стратегии: obv_net пересекает obv_net_sig снизу вверх при close у поддержки ->
    'open_long'; пересечение вниз при close у сопротивления -> 'open_short'.
    """
    signed_vol = (np.sign(df['close'].diff()) * df['volume']).fillna(0.0)
    df['obv_net'] = signed_vol.rolling(period).sum()
    df['obv_net_sig'] = df['obv_net'].rolling(sig_period).mean()
    return df


def add_force_index(df: pd.DataFrame, period: int = 13) -> pd.DataFrame:
    """Columns: ['fi_raw', 'fi_ma', 'fi_norm']

    Force Index (с SMA-сглаживанием вместо EMA Элдера — ради каузальности):
    fi_raw = Δclose × volume (сырой денежный поток бара); fi_ma — средний импульс за период;
    fi_norm = fi_ma / средний объём за период — безразмерная сила, сравнимая между тикерами.

    Пример стратегии: fi_ma разворачивается из минуса вверх при close у поддержки -> 'open_long';
    fi_ma пересекает 0 сверху вниз в лонге -> 'close_long'; fi_norm < -0.5 на падении — паника,
    ждать сигнала sv_stopping (zai_vsa_indicators).
    """
    df['fi_raw'] = df['close'].diff() * df['volume']
    df['fi_ma'] = df['fi_raw'].rolling(period).mean()
    mean_vol = df['volume'].rolling(period).mean().replace(0, np.nan)
    df['fi_norm'] = df['fi_ma'] / mean_vol
    return df


def add_ease_of_movement(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Columns: ['eom_raw', 'eom_ma']

    Ease of Movement: eom_raw = Δmid × (high − low) / volume — насколько «легко» цена проходит
    расстояние при текущем объёме (большое движение на малом объёме = лёгкость);
    eom_ma — SMA-сглаживание за период. Бары с нулевым диапазоном (high == low) или нулевым
    объёмом не несут информации о «лёгкости» и дают eom_raw = 0.0 (не NaN).

    Пример стратегии: eom_ma > 0 и растёт — восходящее движение «лёгкое», удерживать лонг;
    пересечение eom_ma нуля сверху вниз -> 'close_long' / 'open_short'.
    """
    mid = (df['high'] + df['low']) / 2.0
    dm = mid.diff().to_numpy(dtype=float)
    rng = (df['high'] - df['low']).to_numpy(dtype=float)
    vol = df['volume'].to_numpy(dtype=float)
    # Бар без диапазона (high == low) или без объёма не содержит информации о «лёгкости» -> 0.0
    with np.errstate(divide='ignore', invalid='ignore'):
        eom = np.where((rng > 0) & (vol > 0), dm * rng / vol, 0.0)
    df['eom_raw'] = eom
    df['eom_ma'] = df['eom_raw'].rolling(period).mean()
    return df


def add_relative_volume(df: pd.DataFrame, period: int = 20, z_spike: float = 2.0) -> pd.DataFrame:
    """Columns: ['rvol_ratio', 'rvol_z', 'rvol_spike']

    Относительный объём и объёмный выброс: фон — ПРЕДЫДУЩИЕ period баров (shift(1), без
    само-включения). rvol_ratio = volume / средний фон; rvol_z — z-score объёма по фону
    (mean/std того же окна); rvol_spike — выброс (rvol_z >= z_spike).

    Пример стратегии: rvol_spike и пробой high.rolling(20).max().shift(1) -> 'open_long' на объёме;
    rvol_ratio < 0.5 — рынок «спит», новые входы не открывать; rvol_ratio как фильтр к любым
    другим индикаторам (пробой без объёма не считается).
    """
    mean_prev = df['volume'].shift(1).rolling(period, min_periods=period).mean()
    std_prev = df['volume'].shift(1).rolling(period, min_periods=period).std()
    df['rvol_ratio'] = df['volume'] / mean_prev.replace(0, np.nan)
    df['rvol_z'] = (df['volume'] - mean_prev) / std_prev.replace(0, np.nan)
    df['rvol_spike'] = df['rvol_z'] >= z_spike
    return df
