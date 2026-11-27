import os
import re
import traceback
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date, timedelta

from loaders.ApiMoexLoader import ApiMoexLoader
from utils.work_dfs.convert_tf import convert_timeframe
from traders.cscalp_sdk_trader.bot_on_ticker import bot_on_ticker
from testing.CheckTETrader import CheckTETrader
from testing.test_constants import *
from strategies.BaseTE import BaseTE


def flatten_bot_configs(cfg: dict) -> list:
    """Разворачивает словарь bot_on_ticker (вложенный по слотам или плоский) в список (slot, key, ws)."""
    items = []
    for k, v in cfg.items():
        if isinstance(v, dict):
            for ticker_key, ws_tuple in v.items():
                items.append((str(k), str(ticker_key), ws_tuple))
        elif isinstance(v, (tuple, list)):
            items.append(('default', str(k), v))
    return items


if __name__ == '__main__':
    today = date.today()
    start_date = str(today - timedelta(days=3))  # Берём 3 дня с запасом на выходные/праздники для прогрева 80 баров

    folder_date = str(today).replace('-', '_')
    main_folder = os.path.join('_test_results/today', folder_date)
    os.makedirs(main_folder, exist_ok=True)

    df_cache = {}
    configs = flatten_bot_configs(bot_on_ticker)

    for slot_name, ticker_key, ws_tuple in configs:
        try:
            strategy_class = ws_tuple[0]
            if strategy_class is BaseTE or 'PAIRTEs' in getattr(strategy_class, '__module__', ''):
                continue

            # Убираем цифры в конце ключа (ALRS2 -> ALRS)
            load_ticker = re.sub(r'\d+$', '', ticker_key)

            if load_ticker not in df_cache:
                loader = ApiMoexLoader(load_ticker)
                raw_df = loader.load_data(start_date)
                proc_df = loader.processing_df(raw_df)
                proc_df = convert_timeframe(proc_df, '5min')
                proc_df['ms'] = pd.to_datetime(proc_df['ms'])
                proc_df = proc_df.sort_values('ms').reset_index(drop=True)

                last_day = proc_df['ms'].dt.date.max()
                df_last_day = proc_df[proc_df['ms'].dt.date == last_day]
                df_previous_last_80 = proc_df[proc_df['ms'].dt.date < last_day].tail(80)

                df_final = pd.concat([df_previous_last_80, df_last_day], ignore_index=True).reset_index(drop=True)
                df_final['x'] = df_final.index
                df_cache[load_ticker] = df_final


            df = df_cache[load_ticker].copy()

            cwd = CheckTETrader(
                df=df,
                ws=ws_tuple,
                fee=MAIN_FEE,
                symbol=load_ticker,
                use_tqdm=True,
                window=80,
                days_mode=DAYS_MODE,
                slip_stop_delta=SLIP_STOP_DELTA,
            )

            cwd.check_strategy_window(normalization=False)
            cwd.plot_chart_and_sequtity(show=False)

            safe_slot = re.sub(r'[^\w\-]', '_', slot_name)
            img_prefix = f"{safe_slot}_{ticker_key}" if slot_name != 'default' else ticker_key
            full_name_img = os.path.join(main_folder, f"{img_prefix}.png")

            plt.title(f"{img_prefix} ({strategy_class.__name__})")
            plt.savefig(full_name_img, bbox_inches='tight', dpi=200)
            plt.close()
            print(f"[OK] {img_prefix} -> {full_name_img}")

        except Exception as e:
            print(f"[FAIL] {slot_name} | {ticker_key} не вышло: {e}")
            traceback.print_exc()
