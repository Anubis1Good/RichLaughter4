"""zai_ml_indicators — быстрые статистические и ML-признаки.

Все признаки векторизованы на NumPy (sliding_window_view, без циклов по барам) и строго
каузальны: только конечные скользящие окна, никаких глобальных статистик по всей истории и
никаких рекурсивных фильтров — расчёт на полном df и на окне совпадают до последнего бита.

Конвенции проекта (см. PROJECT_CONTEXT.md, разделы 7 и 11.2):
- add_*(df, ...) мутирует df на месте и возвращает df;
- нужны только стандартные колонки OHLCV; служебные колонки проекта не перезаписываются.
"""

import numpy as np
import pandas as pd


def _rolling_linreg(values: np.ndarray, period: int):
    """Векторная скользящая линейная регрессия по окнам длиной period.

    Возвращает (r2, slope, ymean) — массивы длины len(values), первые period-1 значений NaN.
    r2 — коэффициент детерминации fit'а, slope — наклон (цена за бар), ymean — средняя цена окна.
    """
    n = len(values)
    nan = np.full(n, np.nan)
    if n < period:
        return nan, nan, nan

    win = np.lib.stride_tricks.sliding_window_view(np.asarray(values, dtype=float), period)
    x = np.arange(period, dtype=float)
    xm = x - x.mean()
    denom = float((xm * xm).sum())

    ym = win - win.mean(axis=1, keepdims=True)
    cov = (ym * xm).sum(axis=1)
    var_y = (ym * ym).sum(axis=1)

    with np.errstate(divide='ignore', invalid='ignore'):
        r2 = np.where(var_y > 0, (cov * cov) / (denom * var_y), 0.0)
    slope = cov / denom
    ymean = win.mean(axis=1)

    out_r2 = np.full(n, np.nan)
    out_slope = np.full(n, np.nan)
    out_mean = np.full(n, np.nan)
    out_r2[period - 1:] = r2
    out_slope[period - 1:] = slope
    out_mean[period - 1:] = ymean
    return out_r2, out_slope, out_mean


def add_return_autocorr(df: pd.DataFrame, period: int = 50, lag: int = 1) -> pd.DataFrame:
    """Columns: ['rac_corr']

    Скользящая автокорреляция доходностей с лагом lag за период period: насколько шаг цены
    «помнит» предыдущий шаг. Близко к +1 — персистентность (тренд), к −1 — антиперсистентность
    (возврат к среднему), около 0 — случайный блуждательный режим.

    Пример стратегии: rac_corr < -0.1 — режим mean-reversion, разрешить контр-трендовые входы;
    rac_corr > 0.25 — трендовый режим, включить трендовые TE и запретить фейды.
    """
    r = df['close'].pct_change(fill_method=None)
    df['rac_corr'] = r.rolling(period, min_periods=period).corr(r.shift(lag))
    return df


def add_market_entropy(df: pd.DataFrame, period: int = 50, bins: int = 5) -> pd.DataFrame:
    """Columns: ['ent_norm']

    Нормированная энтропия Шеннона распределения доходностей внутри окна (0 — все шаги в одной
    корзине/полный порядок, 1 — равномерное распределение/чистый шум). Границы корзин
    детерминированы min/max ТОЛЬКО данных окна, поэтому значение инвариантно к объёму истории.

    Пример стратегии: ent_norm < 0.5 — упорядоченное движение, разрешить трендовые TE;
    ent_norm > 0.85 — шум, запрет новых входов и принудительное сокращение позиции.
    """
    r = df['close'].pct_change(fill_method=None)

    def _entropy(x: np.ndarray) -> float:
        x = x[np.isfinite(x)]
        if len(x) == 0:
            return np.nan
        lo, hi = float(x.min()), float(x.max())
        if hi <= lo:
            return 0.0
        counts, _ = np.histogram(x, bins=bins, range=(lo, hi))
        p = counts / counts.sum()
        p = p[p > 0]
        return float(-(p * np.log(p)).sum() / np.log(bins))

    df['ent_norm'] = r.rolling(period, min_periods=period).apply(_entropy, raw=True)
    return df


def add_trend_r2(df: pd.DataFrame, period: int = 50) -> pd.DataFrame:
    """Columns: ['tr2_r2', 'tr2_slope_pct']

    Качество линейного тренда в окне: tr2_r2 — R² регрессии close на номер бара (0..1, насколько
    движение похоже на прямую); tr2_slope_pct — наклон в процентах от средней цены окна за бар.
    Векторный расчёт без циклов.

    Пример стратегии: tr2_r2 > 0.7 и tr2_slope_pct > 0 — сильный аптренд, разрешить 'open_long'
    на откатах; падение tr2_r2 ниже 0.4 при позиции по тренду -> 'close_long'.
    """
    close = df['close'].to_numpy(dtype=float)
    r2, slope, ymean = _rolling_linreg(close, period)
    df['tr2_r2'] = r2
    with np.errstate(divide='ignore', invalid='ignore'):
        df['tr2_slope_pct'] = np.where(ymean != 0, slope / ymean * 100.0, np.nan)
    return df


def add_return_zscore(df: pd.DataFrame, period: int = 50) -> pd.DataFrame:
    """Columns: ['rz_value', 'rz_extreme']

    Z-score текущей доходности относительно распределения доходностей ПРЕДЫДУЩИХ period баров
    (shift(1) — фон без само-включения). Показывает, насколько текущий шаг цены аномален.

    Пример стратегии: rz_value <= -2 при восходящем тренде (tr2_slope_pct > 0) -> 'open_long'
    (откат к среднему); rz_value >= 2 при даунтренде -> 'open_short'; |rz_value| < 0.5 —
    норма, фиксация контр-трендовой позиции.
    """
    r = df['close'].pct_change(fill_method=None)
    mean_prev = r.shift(1).rolling(period, min_periods=period).mean()
    std_prev = r.shift(1).rolling(period, min_periods=period).std()
    df['rz_value'] = (r - mean_prev) / std_prev.replace(0, np.nan)
    df['rz_extreme'] = df['rz_value'].abs() >= 2.0
    return df


def add_price_dynamics(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Columns: ['dyn_slope', 'dyn_accel']

    Локальная динамика цены: dyn_slope — наклон линейной регрессии close за период (цена за бар,
    NumPy без циклов); dyn_accel — изменение наклона за бар (ускорение тренда).

    Пример стратегии: dyn_slope > 0 и dyn_accel > 0 — тренд ускоряется, удерживать/пирамидить
    лонг; dyn_accel < 0 при dyn_slope > 0 — замедление, готовиться к 'close_long';
    dyn_accel < 0 и dyn_slope < 0 — ускоряющееся падение, шорт.
    """
    _, slope, _ = _rolling_linreg(df['close'].to_numpy(dtype=float), period)
    df['dyn_slope'] = slope
    df['dyn_accel'] = pd.Series(slope, index=df.index).diff()
    return df
