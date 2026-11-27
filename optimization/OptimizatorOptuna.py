import os
import matplotlib.pyplot as plt
import pandas as pd
import optuna
import psutil
from time import time
from multiprocessing import Pool
from functools import partial
from testing.CheckTETrader import CheckTETrader

optuna.logging.set_verbosity(optuna.logging.CRITICAL)
phys_cores = psutil.cpu_count(logical=False)


class OptimizatorOptuna:
    def __init__(
        self,
        test_folder: str,
        main_folder: str = '_test_results/optuna',
        fee: float = 0.001,
        max_period: int = 55,
        close_on_time: bool = True,
        close_map: tuple = ((22, 30), (22, 30), (22, 30), (22, 30), (22, 30), (17, 30), (17, 30)),
        bottom_limit: int = 100,
        top_limit: int = 1000,
        n_trials: int = 100,
        n_jobs: int = 1,
        need_plot: bool = False,
        save_cores: int = 1,
        measure_time: bool = False,
        # Параметры SL/TP в процентах
        sl_min_pct: float = 0.1,
        sl_max_pct: float = 0.5,
        tp_min_pct: float = 0.1,
        tp_max_pct: float = 1.0,
        use_window_test: bool = False,
        window_size: int = 60,
        normalization: bool = True,
        metric: str = 'total_fee_per',
        days_mode=None,
        slip_slope_delta=1,
        use_stop=0,  # 0 - пробовать оба варианта, -1 - всегда без стопа, 1 - всегда стоп
        use_take=0,
        top_n: int = 1
    ):
        self.top_n = top_n
        self.use_stop = use_stop
        self.use_take = use_take
        self.metric = metric
        self.use_window_test = use_window_test
        self.window_size = window_size
        self.normalization = normalization
        self.test_folder = test_folder
        self.main_folder = main_folder
        self.fee = fee
        self.max_period = max_period + 1
        self.close_on_time = close_on_time
        self.close_map = close_map
        self.bottom_limit = bottom_limit
        self.top_limit = top_limit
        self.n_trials = n_trials
        self.n_jobs = n_jobs
        self.need_plot = need_plot
        self.save_cores = save_cores
        self.measure_time = measure_time
        self.phys_cores = psutil.cpu_count(logical=False)
        self.sl_min_pct = sl_min_pct
        self.sl_max_pct = sl_max_pct
        self.tp_min_pct = tp_min_pct
        self.tp_max_pct = tp_max_pct
        self.traders = []
        self.results_cache = {}
        self.days_mode = days_mode
        self.slip_slope_delta = slip_slope_delta

        self.metric_sign = -1 if metric in {
            'curve_rmse_reg_norm', 'curve_max_dev_reg_norm', 'curve_max_dd_norm',
            'curve_rmse_chord', 'curve_max_dev_chord', 'curve_jump_ratio',
            'curve_l1_mean_chord'
        } else 1

        if not os.path.exists(main_folder):
            os.makedirs(main_folder)

        optuna.logging.disable_default_handler()
        optuna.logging.set_verbosity(optuna.logging.ERROR)

    def load_traders(self):
        files = [
            os.path.join(self.test_folder, f)
            for f in os.listdir(self.test_folder)
            if os.path.isfile(os.path.join(self.test_folder, f))
        ]

        print(f"Loading {len(files)} files...")

        for file in files:
            ticker = os.path.basename(file).split('_')[0]
            trader = CheckTETrader(
                df=file,
                ws=None,
                fee=self.fee,
                symbol=ticker,
                close_on_time=self.close_on_time,
                close_map=self.close_map,
                measure_time=self.measure_time,
                use_tqdm=False,
                window=self.window_size,
                days_mode=self.days_mode,
                slip_stop_delta=self.slip_slope_delta,
            )
            self.traders.append(trader)

        print(f"Loaded {len(self.traders)} traders")

    def get_sl_tp_params(self, trader):
        price_step_per = trader.price_step_per
        min_steps_sl = max(1, int(self.sl_min_pct / price_step_per))
        max_steps_sl = max(min_steps_sl, int(self.sl_max_pct / price_step_per))
        min_steps_tp = max(1, int(self.tp_min_pct / price_step_per))
        max_steps_tp = max(min_steps_tp, int(self.tp_max_pct / price_step_per))

        return {
            'sl': (min_steps_sl, max_steps_sl),
            'tp': (min_steps_tp, max_steps_tp),
        }

    def objective(self, trial, trader, strategy_class, param_options):
        sl_tp_params = self.get_sl_tp_params(trader)

        params = []
        for i, options in enumerate(param_options):
            param_name = f"param_{i}"

            if isinstance(options[0], str):
                params.append(trial.suggest_categorical(param_name, options))
                continue

            if len(options) == 3:
                min_val, max_val, step_val = options
                if min_val >= max_val:
                    raise ValueError(f"min ({min_val}) must be less than max ({max_val}) for param_{i}")
                if step_val <= 0:
                    raise ValueError(f"step ({step_val}) must be positive for param_{i}")

                if isinstance(step_val, int) and all(isinstance(x, int) for x in [min_val, max_val]):
                    params.append(trial.suggest_int(param_name, min_val, max_val, step=step_val))
                else:
                    params.append(trial.suggest_float(param_name, min_val, max_val, step=step_val))

            elif len(options) == 2:
                min_val, max_val = options
                if min_val >= max_val:
                    raise ValueError(f"min ({min_val}) must be less than max ({max_val}) for param_{i}")

                if all(isinstance(x, int) for x in [min_val, max_val]):
                    params.append(trial.suggest_int(param_name, min_val, max_val))
                else:
                    params.append(trial.suggest_float(param_name, min_val, max_val))
            else:
                if len(options) == 1:
                    params.append(options[0])
                elif all(isinstance(x, int) for x in options):
                    params.append(trial.suggest_int(param_name, min(options), max(options)))
                else:
                    params.append(trial.suggest_float(param_name, min(options), max(options)))

        sl_min, sl_max = sl_tp_params['sl']
        tp_min, tp_max = sl_tp_params['tp']

        if self.use_stop == 1:
            sl_value = trial.suggest_int('sl', sl_min, sl_max, step=1)
        elif self.use_stop == -1:
            sl_value = None
        else:
            use_sl = trial.suggest_categorical('use_sl', [True, False])
            sl_value = trial.suggest_int('sl', sl_min, sl_max, step=1) if use_sl else None

        if self.use_take == 1:
            tp_value = trial.suggest_int('tp', tp_min, tp_max, step=1)
        elif self.use_take == -1:
            tp_value = None
        else:
            use_tp = trial.suggest_categorical('use_tp', [True, False])
            tp_value = trial.suggest_int('tp', tp_min, tp_max, step=1) if use_tp else None

        # Строгий контракт BaseTE(symbol, price_step, mode, stop, take, *params)
        strategy = strategy_class(
            trader.symbol,
            trader.price_step,
            None,
            sl_value,
            tp_value,
            *params
        )

        trader.ws = strategy
        trader.reload_data()
        if self.use_window_test:
            trader.check_strategy_window(normalization=self.normalization)
        else:
            trader.check_strategy_faster(history_bars=self.max_period)

        trades, eq, eq_f, _, _, _ = trader.process_old_type_result()

        if not self.bottom_limit <= trades['count'] <= self.top_limit:
            raise optuna.TrialPruned()

        symbol = trader.symbol
        if symbol not in self.results_cache:
            self.results_cache[symbol] = {}

        self.results_cache[symbol][trial.number] = {
            'trades': trades,
            'eq': eq,
            'eq_f': eq_f,
            'params': trial.params.copy(),
            'amount_sl': getattr(strategy, 'amount_sl', None),
            'amount_tp': getattr(strategy, 'amount_tp', None),
        }

        value = trades[self.metric]
        return value * self.metric_sign

    def get_results_table(self, study, trader, strategy_class, param_options):
        results = []
        name_bot = strategy_class.__name__
        ticker = trader.symbol

        images_folder = os.path.join(self.main_folder, name_bot, ticker, 'Images')
        file_folder = os.path.join(self.main_folder, name_bot, ticker)

        os.makedirs(images_folder, exist_ok=True)
        os.makedirs(file_folder, exist_ok=True)

        completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        n_top = min(self.top_n, len(completed_trials))
        top_trials = sorted(
            completed_trials,
            key=lambda x: x.value * self.metric_sign,
            reverse=True
        )[:n_top]

        if not top_trials:
            return pd.DataFrame()

        symbol = trader.symbol

        for trial in top_trials:
            params = []
            param_values = []
            for i, options in enumerate(param_options):
                param_name = f"param_{i}"
                param_value = trial.params.get(param_name, options[0] if len(options) == 1 else None)

                if param_value is None:
                    param_value_str = 'None'
                elif isinstance(param_value, str):
                    param_value_str = f"'{param_value}'"
                elif isinstance(param_value, float):
                    param_value_str = str(round(param_value, 4))
                else:
                    param_value_str = str(param_value)

                params.append(param_value)
                param_values.append(param_value_str)

            sl_value = trial.params.get('sl', None)
            tp_value = trial.params.get('tp', None)

            sl_display = 'None' if sl_value is None else str(sl_value)
            tp_display = 'None' if tp_value is None else str(tp_value)

            all_param_values = [sl_display, tp_display] + param_values

            if symbol in self.results_cache and trial.number in self.results_cache[symbol]:
                cached = self.results_cache[symbol][trial.number]
                trades = cached['trades']
                eq = cached['eq']
                eq_f = cached['eq_f']
            else:
                continue

            name_doc = f"{ticker}_{name_bot}"
            name_file = f"{name_doc}_{'_'.join(all_param_values)}"
            params_tuple = f"({name_bot},({','.join(all_param_values)},),None),"

            result_row = {
                "origin": ticker,
                "ws": params_tuple,
            }

            result_row = result_row | trades
            result_row['name'] = name_file

            results.append(result_row)

            if self.need_plot:
                full_name_img = os.path.join(images_folder, f"{name_file}.png")
                plt.figure(figsize=(12, 6))
                plt.plot(eq, color='red', label='Equity')
                plt.plot(eq_f, color='blue', label='Equity with Fees')
                plt.title(f"{name_bot} (Trial {trial.number})")
                plt.legend()
                plt.savefig(full_name_img, bbox_inches='tight')
                plt.close()

        df_results = pd.DataFrame(results)
        df_results = df_results.drop_duplicates()
        df_results = df_results.sort_values(self.metric, ascending=False)
        df_results = df_results.reset_index(drop=True)

        full_name_doc = os.path.join(file_folder, name_doc + '.xlsx')
        with pd.ExcelWriter(full_name_doc, engine='xlsxwriter') as writer:
            df_results.to_excel(writer, sheet_name='total', index=False)
            worksheet = writer.sheets['total']
            for i, col in enumerate(df_results.columns, start=1):
                max_len = max(
                    df_results[col].astype(str).apply(len).max(),
                    len(col)
                )
                width = min(max_len + 2, 50)
                worksheet.set_column(i - 1, i - 1, width)

        return df_results

    def optimize_trader(self, trader, strategy_config):
        ticker = trader.symbol
        strategy_class, param_options = strategy_config

        study = optuna.create_study(direction="maximize")
        study.optimize(
            lambda trial: self.objective(trial, trader, strategy_class, param_options),
            n_trials=self.n_trials,
            n_jobs=self.n_jobs
        )

        results = self.get_results_table(study, trader, strategy_class, param_options)

        if results is not None and not results.empty:
            best_result = results.iloc[0]
            print(f"{ticker} - Y (best: {best_result[self.metric]:.2f}, trades: {best_result['count']})")
        else:
            print(f"{ticker} - N")

        return results

    def process_group(self, strategy_config, n_trials=None, n_jobs=None, need_plot=None):
        start_time = time()
        self.results_cache = {}
        if n_trials is not None:
            self.n_trials = n_trials
        if n_jobs is not None:
            self.n_jobs = n_jobs
        if need_plot is not None:
            self.need_plot = need_plot

        if not self.traders:
            self.load_traders()

        strategy_name = strategy_config[0].__name__
        print(f"\nTesting strategy: {strategy_name}")
        print(f"Files to test: {len(self.traders)}")
        print("-" * 50)

        num_processes = min(max(1, self.phys_cores - self.save_cores), len(self.traders))

        if num_processes > 1:
            print(f"Using {num_processes} processes...")
            worker = partial(self.optimize_trader, strategy_config=strategy_config)

            with Pool(processes=num_processes) as pool:
                results = list(pool.imap_unordered(worker, self.traders))
        else:
            print("Processing sequentially...")
            results = [self.optimize_trader(trader, strategy_config) for trader in self.traders]

        success_count = sum(1 for r in results if r is not None and not r.empty)

        elapsed = time() - start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        print("-" * 50)
        print(f"Completed: {success_count}/{len(self.traders)}")
        print(f"⏱ Group time: {hours}h {minutes}m {seconds}s")

        return success_count

    def optimize_multiple_groups(self, groups):
        start_time = time()
        total_groups = len(groups)
        total_success = 0
        for i, group in enumerate(groups):
            print(f"\n📊 GROUP {i + 1}/{total_groups}")
            success = self.process_group(group)
            total_success += success

        print(f"\n{'=' * 50}")
        print(f"Total: {total_success} successful")
        print(f"{'=' * 50}")
        elapsed = time() - start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        print(f"⏱ Total time: {hours}h {minutes}m {seconds}s")