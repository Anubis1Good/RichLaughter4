"""zai_classic_indicators — популярные классические индикаторы, отсутствующие в проекте.

Конвенции проекта (см. PROJECT_CONTEXT.md, разделы 7 и 11.2):
- каждая функция add_*(df, ...) мутирует переданный df на месте (добавляет колонки) и возвращает df;
- строгая каузальность: только конечные скользящие окна и положительные shift; никаких ewm,
  рекурсивных фильтров и глобальных статистик — значение на баре i совпадает с расчётом на любом
  окне df.iloc[i-W:i+1], где W накрывает прогрев индикатора;
- нужны только стандартные колонки OHLCV; служебные колонки проекта не перезаписываются.
"""

import numpy as np
import pandas as pd


def add_ichimoku(df: pd.DataFrame, tenkan_period: int = 9, kijun_period: int = 26,
                 senkou_b_period: int = 52, displacement: int = 26) -> pd.DataFrame:
    """Columns: ['ichi_tenkan', 'ichi_kijun', 'ichi_senkou_a', 'ichi_senkou_b', 'ichi_cloud_top', 'ichi_cloud_bottom']

    Облако Ишимоку в каузальной форме: senkou-линии вычислены по прошлым барам и сдвинуты ВПЕРЁД
    на displacement (pandas shift(+displacement)), поэтому значение облака на баре i построено
    только по барам 0..i. Chikou Span (close, сдвинутый назад) намеренно не добавляется — он
    требует будущих данных.

    Пример стратегии: close > ichi_cloud_top и ichi_tenkan > ichi_kijun -> 'open_long';
    выход из лонга при close < ichi_kijun; пробой ichi_cloud_bottom -> 'open_short'.
    """
    hh_t = df['high'].rolling(tenkan_period).max()
    ll_t = df['low'].rolling(tenkan_period).min()
    df['ichi_tenkan'] = (hh_t + ll_t) / 2.0

    hh_k = df['high'].rolling(kijun_period).max()
    ll_k = df['low'].rolling(kijun_period).min()
    df['ichi_kijun'] = (hh_k + ll_k) / 2.0

    df['ichi_senkou_a'] = ((df['ichi_tenkan'] + df['ichi_kijun']) / 2.0).shift(displacement)

    hh_b = df['high'].rolling(senkou_b_period).max()
    ll_b = df['low'].rolling(senkou_b_period).min()
    df['ichi_senkou_b'] = ((hh_b + ll_b) / 2.0).shift(displacement)

    spans = pd.concat([df['ichi_senkou_a'], df['ichi_senkou_b']], axis=1)
    df['ichi_cloud_top'] = spans.max(axis=1)
    df['ichi_cloud_bottom'] = spans.min(axis=1)
    return df


def add_aroon(df: pd.DataFrame, period: int = 25) -> pd.DataFrame:
    """Columns: ['aroon_up', 'aroon_down', 'aroon_diff']

    Aroon: aroon_up — как давно был максимум high за окно period (100 = максимум на текущем баре,
    ~0 = максимум был в начале окна); aroon_down — зеркало по минимумам low; diff = up − down.
    Векторный расчёт через sliding_window_view (без циклов по барам).

    Пример стратегии: aroon_up > 70 и aroon_down < 30 -> 'open_long';
    пересечение aroon_up вниз через aroon_down -> 'close_long' / 'open_short'.
    """
    cols = ['aroon_up', 'aroon_down', 'aroon_diff']
    n = len(df)
    if n < period:
        for c in cols:
            df[c] = np.nan
        return df

    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    win_h = np.lib.stride_tricks.sliding_window_view(high, period)
    win_l = np.lib.stride_tricks.sliding_window_view(low, period)
    pos_h = win_h.argmax(axis=1).astype(float)  # 0 = максимум на самом старом баре окна
    pos_l = win_l.argmin(axis=1).astype(float)
    up = 100.0 * (pos_h + 1.0) / period
    dn = 100.0 * (pos_l + 1.0) / period

    pad = np.full(period - 1, np.nan)
    df['aroon_up'] = np.concatenate([pad, up])
    df['aroon_down'] = np.concatenate([pad, dn])
    df['aroon_diff'] = df['aroon_up'] - df['aroon_down']
    return df


def add_donchian_width(df: pd.DataFrame, period: int = 20, squeeze_period: int = 100,
                       squeeze_q: float = 0.25) -> pd.DataFrame:
    """Columns: ['dcw_width', 'dcw_squeeze']

    Ширина канала Дончиана в процентах от цены (scale-free) и флаг «сжатия»: dcw_squeeze True,
    когда ширина не выше своего squeeze_q-квантиля за ПРЕДЫДУЩИЕ squeeze_period баров (без
    само-включения текущего бара). Аналог squeeze Bollinger, но на границах Donchian.

    Пример стратегии: dcw_squeeze True, затем close пробивает high.rolling(period).max().shift(1)
    -> 'open_long' (пробой после сжатия); DC-стратегии проекта (max_hb/min_hb) можно фильтровать
    условием dcw_squeeze == False.
    """
    dc_h = df['high'].rolling(period).max()
    dc_l = df['low'].rolling(period).min()
    df['dcw_width'] = (dc_h - dc_l) / df['close'] * 100.0
    base = df['dcw_width'].shift(1).rolling(squeeze_period, min_periods=squeeze_period).quantile(squeeze_q)
    df['dcw_squeeze'] = df['dcw_width'] <= base
    return df


def add_elder_ray(df: pd.DataFrame, period: int = 13) -> pd.DataFrame:
    """Columns: ['elder_bull', 'elder_bear', 'elder_dir']

    Elder Ray Index: bull power = high − MA(period), bear power = low − MA(period).
    Вместо EMA Элдера используется SMA — рекурсивные фильтры нарушают инвариантность к окну.
    elder_dir: +1 (оба > 0, устойчивый аптренд), −1 (оба < 0, даунтренд), 0 (смешанно).

    Пример стратегии: elder_dir == 1 -> удерживать лонг; elder_bear > 0 после падения
    (медведи не пробивают среднюю) -> подтверждение 'open_long'.
    """
    ma = df['close'].rolling(period).mean()
    df['elder_bull'] = df['high'] - ma
    df['elder_bear'] = df['low'] - ma
    up = (df['elder_bull'] > 0) & (df['elder_bear'] > 0)
    dn = (df['elder_bull'] < 0) & (df['elder_bear'] < 0)
    df['elder_dir'] = np.select([up, dn], [1, -1], default=0)
    return df


def add_vortex(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Columns: ['vtx_plus', 'vtx_minus', 'vtx_diff']

    Vortex Indicator: VI+ = Σ|high − low_prev| / ΣTR, VI− = Σ|low − high_prev| / ΣTR за период.
    Растущий vtx_plus — движение вверх «закручивает» вихрь; diff = VI+ − VI−.
    TR использует close.shift(1) — только прошлые бары.

    Пример стратегии: пересечение vtx_plus вверх через vtx_minus -> 'open_long';
    обратное пересечение -> 'close_long' / 'open_short'.
    """
    h = df['high'].to_numpy(dtype=float)
    l = df['low'].to_numpy(dtype=float)
    c_prev = df['close'].shift(1).to_numpy(dtype=float)

    vm_p = np.abs(h - np.roll(l, 1))
    vm_m = np.abs(l - np.roll(h, 1))
    tr = np.maximum(np.maximum(h - l, np.abs(h - c_prev)), np.abs(l - c_prev))
    vm_p[0] = np.nan  # np.roll заворачивает хвост в начало — первый бар недействителен
    vm_m[0] = np.nan
    tr[0] = np.nan

    s_p = pd.Series(vm_p, index=df.index).rolling(period).sum()
    s_m = pd.Series(vm_m, index=df.index).rolling(period).sum()
    s_tr = pd.Series(tr, index=df.index).rolling(period).sum()
    s_tr = s_tr.replace(0, np.nan)

    df['vtx_plus'] = s_p / s_tr
    df['vtx_minus'] = s_m / s_tr
    df['vtx_diff'] = df['vtx_plus'] - df['vtx_minus']
    return df


def add_chaikin_money_flow(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Columns: ['cmf_value']

    Chaikin Money Flow: CMF = Σ(MFM × volume) / Σvolume за период, где
    MFM = ((close − low) − (high − close)) / (high − low) — где закрылся бар внутри диапазона.
    CMF > 0 — деньги в акцию (закрытия у верхов), CMF < 0 — отток. Бары с нулевым диапазоном
    считаются нейтральными (MFM = 0).

    Пример стратегии: cmf_value > 0.2 и close пробивает high.rolling(20).max().shift(1) -> 'open_long';
    cmf_value < -0.2 при пробое минимума -> 'open_short'.
    """
    rng = (df['high'] - df['low']).replace(0, np.nan)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / rng
    mfv = mfm.fillna(0.0) * df['volume']
    vol_sum = df['volume'].rolling(period).sum().replace(0, np.nan)
    df['cmf_value'] = mfv.rolling(period).sum() / vol_sum
    return df
