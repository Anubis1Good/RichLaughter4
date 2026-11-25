"""zai_vsa_indicators — VSA-индикаторы (Volume Spread Analysis), отсутствующие в проекте.

Дополняют for_strategies/vsa_indicators.py (там: CDV/dvsai/cdvsai, стоп-действия, rails,
volume zones, reversal_patterns). Здесь — классические VSA-сценарии: effort vs result,
кульминации объёма, no demand / no supply, churn, поглощение на экстремумах.

Конвенции проекта (см. PROJECT_CONTEXT.md, разделы 7 и 11.2):
- add_*(df, ...) мутирует df на месте и возвращает df; строгая каузальность (только конечные
  скользящие окна, средние «фона» берутся со shift(1) — без само-включения текущего бара);
- нужны только стандартные колонки OHLCV; служебные колонки проекта не перезаписываются.
"""

import numpy as np
import pandas as pd


def _mean_prev(series: pd.Series, period: int) -> pd.Series:
    """Среднее по ПРЕДЫДУЩИМ period барам (shift(1)) — «фоновая» статистика без само-включения."""
    return series.shift(1).rolling(period, min_periods=period).mean()


def _close_pos(df: pd.DataFrame) -> pd.Series:
    """Позиция закрытия внутри диапазона бара: 1 = у high, 0 = у low; NaN при high == low."""
    rng = (df['high'] - df['low']).replace(0, np.nan)
    return (df['close'] - df['low']) / rng


def add_effort_result(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Columns: ['evr_effort', 'evr_result', 'evr_ratio']

    Effort vs Result: evr_effort = volume / средний объём прошлых period баров (сколько «усилий»);
    evr_result = спред бара / средний спред прошлых баров (что получили); evr_ratio = result/effort.
    ratio < 1 — большой объём почти не двинул цену (поглощение), ratio > 2 — лёгкое движение
    на малом объёме (нет интереса).

    Пример стратегии: evr_ratio < 0.5, evr_effort > 1.5 и 3 падающих закрытия подряд -> 'open_long'
    (усилие продавцов поглощено); evr_ratio > 2.5 на подъёме в шорт-позиции -> 'close_short'.
    """
    df['evr_effort'] = df['volume'] / _mean_prev(df['volume'], period).replace(0, np.nan)
    spread = df['high'] - df['low']
    df['evr_result'] = spread / _mean_prev(spread, period).replace(0, np.nan)
    df['evr_ratio'] = df['evr_result'] / df['evr_effort'].replace(0, np.nan)
    return df


def add_stopping_volume(df: pd.DataFrame, period: int = 20, vol_mult: float = 1.5,
                        spread_mult: float = 1.3) -> pd.DataFrame:
    """Columns: ['sv_close_pos', 'sv_up_climax', 'sv_down_climax', 'sv_stopping']

    Кульминации и стоп-объём: sv_close_pos — позиция закрытия в диапазоне бара (0..1).
    sv_up_climax — сверхобъёмный широкий бар с закрытием у верха на растущем рынке (кульминация
    покупок, риск разворота вниз); sv_down_climax — зеркальная кульминация продаж;
    sv_stopping — сверхобъёмный УЗКИЙ бар с закрытием у верха после падения (объём не двинул цену
    вниз — продавцы иссякли, классический «stopping volume»).

    Пример стратегии: sv_stopping True -> 'open_long' со стопом под low бара; sv_up_climax True
    при позиции long -> 'close_long' / 'open_short' на следующем слабом баре.
    """
    cpos = _close_pos(df)
    df['sv_close_pos'] = cpos

    high_vol = df['volume'] >= vol_mult * _mean_prev(df['volume'], period)
    spread = df['high'] - df['low']
    wide = spread >= spread_mult * _mean_prev(spread, period)
    sma = df['close'].rolling(period).mean()
    up_trend = df['close'] > sma
    dn_trend = df['close'] < sma

    df['sv_up_climax'] = high_vol & wide & (cpos >= 0.7) & up_trend
    df['sv_down_climax'] = high_vol & wide & (cpos <= 0.3) & dn_trend
    df['sv_stopping'] = high_vol & ~wide & (cpos >= 0.7) & dn_trend
    return df


def add_no_demand_supply(df: pd.DataFrame, period: int = 20, vol_k: float = 0.7) -> pd.DataFrame:
    """Columns: ['nds_low_vol', 'nds_no_demand', 'nds_no_supply']

    No Demand — восходящий бар (close > open) на объёме ниже vol_k × среднего фонового объёма в
    падающем рынке: быки не могут поднять цену. No Supply — нисходящий бар на низком объёме в
    растущем рынке: медведи не могут опустить цену. Фоновый объём — предыдущие period баров.

    Пример стратегии: nds_no_demand при позиции long -> 'close_long'; nds_no_supply в лонге —
    удерживать/добирать; nds_no_supply после sweep_down (см. zai_smc_indicators) -> 'open_long'.
    """
    low_vol = df['volume'] < vol_k * _mean_prev(df['volume'], period)
    df['nds_low_vol'] = low_vol
    sma = df['close'].rolling(period).mean()
    df['nds_no_demand'] = (df['close'] > df['open']) & low_vol & (df['close'] < sma)
    df['nds_no_supply'] = (df['close'] < df['open']) & low_vol & (df['close'] > sma)
    return df


def add_climax_churn(df: pd.DataFrame, period: int = 20, vol_q: float = 0.9,
                     spread_k: float = 0.5) -> pd.DataFrame:
    """Columns: ['churn_vol_hi', 'churn_bar', 'churn_dir']

    Climax Churn: объём бара в верхних vol_q-квантилях скользящего распределения ПРЕДЫДУЩИХ баров
    при спреде не больше spread_k × среднего фонового спреда — «борьба» гигантских объёмов без
    движения цены. churn_dir — направление бара в момент churn (+1 растущий, −1 падающий).

    Пример стратегии: churn_bar True у верхней границы диапазона (pd_pos > 0.7 из
    zai_smc_indicators.add_premium_discount) -> 'open_short'; churn_bar у нижней границы -> 'open_long'.
    """
    vol_base = df['volume'].shift(1).rolling(period, min_periods=period).quantile(vol_q)
    df['churn_vol_hi'] = df['volume'] >= vol_base
    spread = df['high'] - df['low']
    narrow = spread <= spread_k * _mean_prev(spread, period)
    df['churn_bar'] = df['churn_vol_hi'] & narrow
    df['churn_dir'] = np.where(df['churn_bar'], np.sign(df['close'] - df['open']), 0).astype(int)
    return df


def add_volume_absorption(df: pd.DataFrame, period: int = 20, vol_mult: float = 1.5,
                          lookback: int = 10) -> pd.DataFrame:
    """Columns: ['abs_at_top', 'abs_at_bottom', 'abs_sign']

    Поглощение объёмом на локальных экстремумах: сверхобъёмный бар (volume >= vol_mult × фон),
    обновляющий максимум недавних lookback баров, но закрывающийся в нижней части диапазона —
    покупки поглощены (abs_at_top, медвежий). Зеркально abs_at_bottom — продажи поглощены
    (бычий). abs_sign: +1 бычье поглощение, −1 медвежье, 0 — ничего.

    Пример стратегии: abs_at_bottom у поддержки -> 'open_long' со стопом под low бара;
    abs_at_top в лонге -> 'close_long'; связка abs_at_top + sv_up_climax — сильный шорт-сетап.
    """
    cpos = _close_pos(df)
    high_vol = df['volume'] >= vol_mult * _mean_prev(df['volume'], period)
    at_top = df['high'] >= df['high'].shift(1).rolling(lookback).max()
    at_bot = df['low'] <= df['low'].shift(1).rolling(lookback).min()

    df['abs_at_top'] = high_vol & at_top & (cpos <= 0.4)
    df['abs_at_bottom'] = high_vol & at_bot & (cpos >= 0.6)
    df['abs_sign'] = np.where(df['abs_at_bottom'], 1, np.where(df['abs_at_top'], -1, 0)).astype(int)
    return df
