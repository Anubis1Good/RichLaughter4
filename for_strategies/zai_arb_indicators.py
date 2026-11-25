"""zai_arb_indicators — индикаторы парного трейдинга и статистического арбитража.

Стиль for_strategies/arb_indicators.py: функции работают с ЗАРАНЕЕ ВЫРОВНЕННЫМИ по строкам
датафреймами (как PairTETrader._align_dfs) — строка i в df1 соответствует строке i в df2.
Сигнатура: def add_<name>(df1: pd.DataFrame, df2: pd.DataFrame, ...) -> pd.DataFrame;
колонки добавляются в df1, df1 возвращается. При несовпадении длин — ValueError.

Строгая каузальность: только конечные скользящие окна (средние/σ/корреляции по window баров),
никаких глобальных статистик и рекурсивных фильтров — расчёт на полном df и на окне, накрывающем
прогрев, совпадают.
"""

import numpy as np
import pandas as pd


def _check_aligned(df1: pd.DataFrame, df2: pd.DataFrame) -> None:
    if len(df1) != len(df2):
        raise ValueError(
            f"zai_arb: датафреймы должны быть выровнены по строкам (PairTETrader._align_dfs): "
            f"len(df1)={len(df1)} != len(df2)={len(df2)}"
        )


def add_pair_zscore(df1: pd.DataFrame, df2: pd.DataFrame, window: int = 145,
                    kind: str = 'log') -> pd.DataFrame:
    """Columns: ['pz_spread', 'pz_zscore']

    Скользящий Z-Score спреда пары: pz_spread = ln(close1) − ln(close2) при kind='log'
    (или close1/close2 − 1 при kind='pct'); pz_zscore = (spread − среднее за window баров) /
    σ за те же window баров. Строго каузально — только прошлое окно.

    Пример стратегии: pz_zscore > 2 и режим пары пригоден (pcr_half_life < window/3) -> шорт df1 /
    лонг df2 (спред растянут); pz_zscore < -2 -> зеркально; выход при pz_zscore -> 0;
    стоп/развал пары — при |pz_zscore| > 3.5.
    """
    _check_aligned(df1, df2)
    c1 = df1['close']
    c2 = df2['close']

    if kind == 'log':
        s = np.log(c1) - np.log(c2)
    elif kind == 'pct':
        s = c1 / c2.replace(0, np.nan) - 1.0
    else:
        raise ValueError("kind должен быть 'log' или 'pct'")

    df1['pz_spread'] = s
    mean = s.rolling(window, min_periods=window).mean()
    std = s.rolling(window, min_periods=window).std()
    df1['pz_zscore'] = (s - mean) / std.replace(0, np.nan)
    return df1


def add_pair_beta_spread(df1: pd.DataFrame, df2: pd.DataFrame, window: int = 100) -> pd.DataFrame:
    """Columns: ['pb_beta', 'pb_spread', 'pb_spread_z']

    Динамический коэффициент хеджирования: pb_beta — скользящий OLS-наклон доходностей df1 к df2
    за window баров (cov/var, сколько единиц df2 хеджирует 1 df1); pb_spread = ln(close1) −
    pb_beta × ln(close2) — остаток спреда после хеджа; pb_spread_z — z-score остатка за то же окно.

    Пример стратегии: pb_spread_z > 2 -> шорт df1 / лонг df2 в пропорции pb_beta;
    pb_spread_z < -2 -> лонг df1 / шорт df2; выход при pb_spread_z -> 0; |pb_spread_z| > 3.5 —
    развал пары (стоп). pb_beta в боевой конфиг: lot2 = round(lot1 * pb_beta).

    Прогрев: 2×window (window на бета + window на статистики остатка pb_spread).
    """
    _check_aligned(df1, df2)
    c1 = df1['close']
    c2 = df2['close']
    r1 = c1.pct_change(fill_method=None)
    r2 = c2.pct_change(fill_method=None)

    cov = r1.rolling(window, min_periods=window).cov(r2)
    var = r2.rolling(window, min_periods=window).var()
    beta = cov / var.replace(0, np.nan)
    df1['pb_beta'] = beta

    spread = np.log(c1) - beta * np.log(c2)
    df1['pb_spread'] = spread
    mean = spread.rolling(window, min_periods=window).mean()
    std = spread.rolling(window, min_periods=window).std()
    df1['pb_spread_z'] = (spread - mean) / std.replace(0, np.nan)
    return df1


def add_pair_corr_regime(df1: pd.DataFrame, df2: pd.DataFrame, window: int = 100) -> pd.DataFrame:
    """Columns: ['pcr_corr', 'pcr_phi', 'pcr_half_life']

    Режим пары: pcr_corr — корреляция Пирсона доходностей за window баров (связность пары);
    pcr_phi — AR(1)-коэффициент спреда ln(c1)−ln(c2) (корреляция спреда с самим собой со сдвигом
    1 за окно); pcr_half_life — полупериод возврата к среднему из phi: ln(0.5)/ln(phi), NaN при
    phi вне (0; 1). Всё строго по прошлому окну.

    Пример стратегии: торговать расхождение (pz_zscore/pb_spread_z) только при pcr_corr > 0.5 и
    pcr_half_life < window/3; pcr_half_life > window или NaN — спред «стоит»/развалён, пару не
    торговать; рост pcr_corr — сигнал наращивать размер.
    """
    _check_aligned(df1, df2)
    r1 = df1['close'].pct_change(fill_method=None)
    r2 = df2['close'].pct_change(fill_method=None)

    df1['pcr_corr'] = r1.rolling(window, min_periods=window).corr(r2)

    spread = np.log(df1['close']) - np.log(df2['close'])
    phi = spread.rolling(window, min_periods=window).corr(spread.shift(1))
    df1['pcr_phi'] = phi

    phi_valid = phi.where((phi > 0) & (phi < 1))
    df1['pcr_half_life'] = np.log(0.5) / np.log(phi_valid)
    return df1


def add_pair_spread_oscillators(df1: pd.DataFrame, df2: pd.DataFrame, window: int = 20,
                                rsi_period: int = 14, n_std: float = 2.0) -> pd.DataFrame:
    """Columns: ['pso_spread', 'pso_mid', 'pso_up', 'pso_dn', 'pso_rsi']

    Осцилляторы синтетического спреда пары: pso_spread = (close1/close2 − 1) × 100 (%-спред);
    полосы Боллинджера по скользящим mean/std за window баров (pso_mid/pso_up/pso_dn) и
    SMA-RSI спреда (pso_rsi; классическая Wilder-EMA заменена SMA ради каузальности).

    Пример стратегии: pso_spread < pso_dn и pso_rsi < 30 -> лонг df1 / шорт df2;
    pso_spread > pso_up и pso_rsi > 70 -> шорт df1 / лонг df2; выход при возврате спреда к
    pso_mid; усиление сигнала — совпадение с pz_zscore (см. add_pair_zscore).
    """
    _check_aligned(df1, df2)
    s = (df1['close'] / df2['close'].replace(0, np.nan) - 1.0) * 100.0
    df1['pso_spread'] = s

    mean = s.rolling(window, min_periods=window).mean()
    std = s.rolling(window, min_periods=window).std()
    df1['pso_mid'] = mean
    df1['pso_up'] = mean + n_std * std
    df1['pso_dn'] = mean - n_std * std

    d = s.diff()
    gain = d.clip(lower=0).rolling(rsi_period, min_periods=rsi_period).mean()
    loss = (-d).clip(lower=0).rolling(rsi_period, min_periods=rsi_period).mean()
    df1['pso_rsi'] = 100.0 * gain / (gain + loss).replace(0, np.nan)
    return df1
