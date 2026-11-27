import os
import re
import traceback
import psutil
import pandas as pd
import matplotlib.pyplot as plt
from time import time
from multiprocessing import Pool

from testing.CheckTETrader import CheckTETrader
from testing.test_constants import *
from strategies.all_tes import *
from strategies.BaseTE import BaseTE


class CurrentTester:
    def __init__(
        self,
        data_folder: str,
        output_folder: str = '_test_results/current_test',
        fee: float = 0.001,
        close_on_time: bool = True,
        close_map: tuple = ((22, 30), (22, 30), (22, 30), (22, 30), (22, 30), (17, 30), (17, 30)),
        window_size: int = 60,
        normalization: bool = False,
        use_window_test: bool = False,
        save_cores: int = 1,
        need_plot: bool = False,
        days_mode=None,
        slip_stop_delta: int = 1,
        strategies_dict: dict = None,
    ):
        self.data_folder = data_folder
        self.output_folder = output_folder
        self.fee = fee
        self.close_on_time = close_on_time
        self.close_map = close_map
        self.window_size = window_size
        self.normalization = normalization
        self.use_window_test = use_window_test
        self.save_cores = save_cores
        self.phys_cores = psutil.cpu_count(logical=False) or 1
        self.need_plot = need_plot
        self.days_mode = days_mode
        self.slip_stop_delta = slip_stop_delta
        self.strategies_dict = strategies_dict or {}

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

    def get_ticker_from_key(self, key: str) -> str:
        """Извлекает чистый тикер из ключа (убирает цифры в конце)."""
        return re.sub(r'\d+$', '', key)

    def load_trader(self, ticker: str):
        """Загружает CheckTETrader для указанного тикера."""
        files = [
            f for f in os.listdir(self.data_folder)
            if os.path.isfile(os.path.join(self.data_folder, f)) and f.startswith(f"{ticker}_")
        ]

        if not files:
            print(f"Data file for {ticker} not found")
            return None

        file_path = os.path.join(self.data_folder, files[0])

        return CheckTETrader(
            df=file_path,
            ws=None,
            fee=self.fee,
            symbol=ticker,
            close_on_time=self.close_on_time,
            close_map=self.close_map,
            measure_time=False,
            use_tqdm=False,
            window=self.window_size,
            days_mode=self.days_mode,
            slip_stop_delta=self.slip_stop_delta,
        )

    def test_single_row(self, row_data: dict, chunk_index: int, results_list: list, output_path: str) -> bool:
        """Тестирует одну стратегию из bot_on_ticker и сохраняет промежуточный результат."""
        row_name = row_data.get('name', 'unknown')
        slot_name = row_data.get('slot', 'default')
        try:
            strategy_tuple = row_data.get('strategy_tuple')
            if not strategy_tuple:
                return False

            strategy_class = strategy_tuple[0]
            if strategy_class is BaseTE or 'PAIRTEs' in getattr(strategy_class, '__module__', ''):
                return False

            params = strategy_tuple[1] if len(strategy_tuple) > 1 else tuple()
            mode = strategy_tuple[2] if len(strategy_tuple) > 2 else None
            ticker = self.get_ticker_from_key(row_name)

            processed_params = [
                None if (isinstance(p, str) and p == 'None') else p
                for p in params
            ]

            trader = self.load_trader(ticker)
            if trader is None:
                print(f"[{os.getpid()}] Trader not loaded for {ticker}, skipping {row_name}")
                return False

            try:
                strategy = strategy_class(
                    trader.symbol,
                    trader.price_step,
                    mode,
                    *processed_params,
                )
            except Exception as e:
                print(f"[{os.getpid()}] Error creating strategy for {row_name}: {e}")
                return False

            trader.ws = strategy
            trader.reload_data()

            # Быстрый тест
            trader.check_strategy_window()
            trades_fast, _, _, _, _, _ = trader.process_old_type_result()
            ef_fast = trader.trade_data['step_eq_fee'].copy()

            result = {
                'slot': slot_name,
                'name': row_name,
                'ticker': ticker,
                'strategy': str(strategy_class.__name__),
                'params': str(processed_params),
                'total_fast': round(trades_fast['total'], 2),
                'total_abs_fee_fast': round(trades_fast.get('total_abs_fee', 0), 2),
                'total_fee_per_fast': round(trades_fast.get('total_fee_per', 0), 2),
                'count_fast': trades_fast['count'],
                'win_rate_fast': trades_fast.get('win_rate_wf', 0),
                'max_dd_fast': round(trades_fast.get('max_dropdown', 0), 2),
            }

            ef_window = None
            if self.use_window_test:
                trader.reload_data()
                trader.check_strategy_window(normalization=self.normalization)
                trades_window, _, _, _, _, _ = trader.process_old_type_result()
                ef_window = trader.trade_data['step_eq_fee'].copy()

                result.update({
                    'total_window': round(trades_window['total'], 2),
                    'total_fee_per_window': round(trades_window.get('total_fee_per', 0), 2),
                    'count_window': trades_window['count'],
                    'win_rate_window': trades_window.get('win_rate_wf', 0),
                    'diff_total_fee_per': round(
                        trades_window.get('total_fee_per', 0) - trades_fast.get('total_fee_per', 0), 2
                    ),
                })

            if self.need_plot:
                img_folder = os.path.join(self.output_folder, 'imgs')
                os.makedirs(img_folder, exist_ok=True)
                safe_slot = re.sub(r'[^\w\-]', '_', slot_name)
                full_name_img = os.path.join(img_folder, f"{safe_slot}_{row_name}.png")
                plt.figure(figsize=(12, 6))
                plt.plot(ef_fast, color='blue', label='Equity_fast (with fee)')
                if ef_window is not None:
                    plt.plot(ef_window, color='red', label='Equity_window (with fee)')
                plt.title(f"{slot_name} | {row_name} ({strategy_class.__name__})")
                plt.legend()
                plt.savefig(full_name_img, bbox_inches='tight')
                plt.close()

            results_list.append(result)

            if results_list:
                temp_df = pd.DataFrame(results_list)
                temp_df = temp_df.sort_values('total_fee_per_fast', ascending=False).reset_index(drop=True)

                with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                    temp_df.to_excel(writer, sheet_name='results', index=False)
                    worksheet = writer.sheets['results']
                    for i, col in enumerate(temp_df.columns):
                        max_len = max(temp_df[col].astype(str).map(len).max(), len(col))
                        worksheet.set_column(i, i, min(max_len + 2, 50))

            return True

        except Exception as e:
            print(f"[{os.getpid()}] Error testing {row_name}: {e}")
            traceback.print_exc()
            return False

    def test_rows_chunk(self, chunk_data: list, chunk_index: int) -> bool:
        """Тестирует чанк стратегий."""
        results = []
        output_path = os.path.join(self.output_folder, f'process_{chunk_index}_results.xlsx')

        if os.path.exists(output_path):
            os.remove(output_path)

        for i, row_data in enumerate(chunk_data):
            row_name = row_data.get('name', 'unknown')
            print(f"[{os.getpid()}] Chunk {chunk_index}: {i + 1}/{len(chunk_data)} - {row_name}")
            self.test_single_row(row_data, chunk_index, results, output_path)

        if results:
            return True
        if os.path.exists(output_path):
            os.remove(output_path)
        return False

    @staticmethod
    def process_chunk_static(
        data_folder, output_folder, fee, close_on_time,
        close_map, window_size, normalization, use_window_test,
        chunk_data, chunk_index, need_plot, days_mode,
        slip_stop_delta, strategies_dict,
    ):
        tester = CurrentTester(
            data_folder=data_folder,
            output_folder=output_folder,
            fee=fee,
            close_on_time=close_on_time,
            close_map=close_map,
            window_size=window_size,
            normalization=normalization,
            use_window_test=use_window_test,
            save_cores=1,
            need_plot=need_plot,
            days_mode=days_mode,
            slip_stop_delta=slip_stop_delta,
            strategies_dict=strategies_dict,
        )
        return tester.test_rows_chunk(chunk_data, chunk_index)

    def _prepare_strategies_list(self) -> list:
        """Разворачивает словарь bot_on_ticker (как вложенный по слотам, так и плоский)."""
        strategies_list = []
        for key, val in self.strategies_dict.items():
            if isinstance(val, dict):
                for ticker_key, strategy_tuple in val.items():
                    strategies_list.append({
                        'slot': str(key),
                        'name': str(ticker_key),
                        'strategy_tuple': strategy_tuple,
                    })
            elif isinstance(val, (tuple, list)):
                strategies_list.append({
                    'slot': 'default',
                    'name': str(key),
                    'strategy_tuple': val,
                })
        return strategies_list

    def run_tests(self):
        start_time = time()
        strategies_list = self._prepare_strategies_list()
        print(f"Loaded {len(strategies_list)} strategies from bot_on_ticker")

        if not strategies_list:
            print("No strategies to test")
            return

        num_processes = min(max(1, self.phys_cores - self.save_cores), len(strategies_list))
        print(f"Using {num_processes} processes...")

        chunk_size = max(1, (len(strategies_list) + num_processes - 1) // num_processes)
        chunks = [strategies_list[i:i + chunk_size] for i in range(0, len(strategies_list), chunk_size)]

        args_list = [
            (
                self.data_folder,
                self.output_folder,
                self.fee,
                self.close_on_time,
                self.close_map,
                self.window_size,
                self.normalization,
                self.use_window_test,
                chunk_data,
                i,
                self.need_plot,
                self.days_mode,
                self.slip_stop_delta,
                self.strategies_dict,
            )
            for i, chunk_data in enumerate(chunks)
        ]

        if num_processes > 1:
            with Pool(processes=num_processes) as pool:
                results = pool.starmap(self.process_chunk_static, args_list)
            success_count = sum(results)
        else:
            success_count = sum(1 for args in args_list if self.process_chunk_static(*args))

        print("\n" + "=" * 50)
        print("Merging all results...")

        all_results = []
        for file in os.listdir(self.output_folder):
            if file.startswith('process_') and file.endswith('_results.xlsx'):
                file_path = os.path.join(self.output_folder, file)
                all_results.append(pd.read_excel(file_path))
                os.remove(file_path)

        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            final_df = final_df.sort_values('total_fee_per_fast', ascending=False).reset_index(drop=True)

            final_filename = f"current_test_results_{int(time())}.xlsx"
            output_path = os.path.join(self.output_folder, final_filename)
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, sheet_name='results', index=False)
                worksheet = writer.sheets['results']
                for i, col in enumerate(final_df.columns):
                    max_len = max(final_df[col].astype(str).map(len).max(), len(col))
                    worksheet.set_column(i, i, min(max_len + 2, 50))

            print(f"[OK] Final results saved to: {output_path}")
            print(f"Total rows: {len(final_df)}")
        else:
            print("[FAIL] No results to merge")

        elapsed = time() - start_time
        print(f"\n{'=' * 50}")
        print(f"Current test completed in {int(elapsed // 60)}m {int(elapsed % 60)}s! Chunks: {success_count}/{len(chunks)}")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    DATA_FOLDER = "_data_for_tests/data_stock_5m"
    OUTPUT_FOLDER = "_test_results/current_test"
    from traders.cscalp_sdk_trader.bot_on_ticker import bot_on_ticker

    tester = CurrentTester(
        data_folder=DATA_FOLDER,
        output_folder=OUTPUT_FOLDER,
        fee=MAIN_FEE,
        close_on_time=True,
        close_map=((22, 30), (22, 30), (22, 30), (22, 30), (22, 30), (17, 30), (17, 30)),
        window_size=WINDOW,
        normalization=False,
        use_window_test=False,
        save_cores=0,
        need_plot=True,
        days_mode=DAYS_MODE,
        slip_stop_delta=SLIP_STOP_DELTA,
        strategies_dict=bot_on_ticker,
    )

    tester.run_tests()

