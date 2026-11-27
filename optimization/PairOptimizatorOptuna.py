import os
import glob
import warnings
import psutil
import matplotlib.pyplot as plt
import pandas as pd
import optuna
from time import time
from multiprocessing import Pool
from functools import partial
from testing.PairTETrader import PairTETrader

warnings.filterwarnings("ignore", category=UserWarning, module="optuna")
optuna.logging.set_verbosity(optuna.logging.CRITICAL)


class PairOptimizatorOptuna:
    """
    Многопроцессорный Optuna-оптимизатор для парных и портфельных стратегий на базе PairTETrader
    (LTEP1_SINGULARITY, UTEP1_SPARTACUS, UTEP2_PROMETHEUS).
    """

    def __init__(
        self,
        test_folder: str,
        pairs: list,
        main_folder: str = '_test_results/pair_optuna',
        fee: float = 0.0002,
        close_on_time: bool = True,
        close_map: tuple = ((22, 30), (22, 30), (22, 30), (22, 30), (22, 30), (17, 30), (17, 30)),
        bottom_limit: int = 20,
        top_limit: int = 2000,
        n_trials: int = 100,
        need_plot: bool = False,
        save_cores: int = 1,
        window_size: int = 150,
        use_window_test: bool = False,
        metric: str = 'total_wfee',
        days_mode=None,
        top_n: int = 1,
    ):
        """
        pairs: список пар вида [('TATN', 'TATNP', {'TATN': 1, 'TATNP': 1}), ...]
               или [('TATN', 'TATNP'), ...] (тогда quantity по умолчанию 1:1).
        """
        self.test_folder = test_folder
        self.pairs = pairs
        self.main_folder = main_folder
        self.fee = fee
        self.close_on_time = close_on_time
        self.close_map = close_map
        self.bottom_limit = bottom_limit
        self.top_limit = top_limit
        self.n_trials = n_trials
        self.need_plot = need_plot
        self.save_cores = save_cores
        self.phys_cores = psutil.cpu_count(logical=False) or 1
        self.window_size = window_size
        self.use_window_test = use_window_test
        self.metric = metric
        self.days_mode = days_mode
        self.top_n = top_n
        self.pair_traders = []
        self.results_cache = {}

        os.makedirs(main_folder, exist_ok=True)
        optuna.logging.disable_default_handler()
        optuna.logging.set_verbosity(optuna.logging.ERROR)

    def _find_ticker_file(self, ticker: str) -> str:
        pattern = os.path.join(self.test_folder, f"{ticker}_*.parquet")
        matches = glob.glob(pattern)
        if not matches:
            pattern_csv = os.path.join(self.test_folder, f"{ticker}_*.csv")
            matches = glob.glob(pattern_csv)
        if not matches:
            raise FileNotFoundError(f"Не найден файл данных для тикера {ticker} в {self.test_folder}")
        return matches[0]

    def load_pair_traders(self):
        self.pair_traders = []
        for item in self.pairs:
            s1, s2 = item[0], item[1]
            qty = item[2] if len(item) > 2 else {s1: 1.0, s2: 1.0}
            f1 = self._find_ticker_file(s1)
            f2 = self._find_ticker_file(s2)

            pt = PairTETrader(
                dfs={s1: f1, s2: f2},
                ws=None,
                quantity=qty,
                fee=self.fee,
                close_on_time=self.close_on_time,
                close_map=self.close_map,
                use_tqdm=False,
                window=self.window_size,
                days_mode=self.days_mode,
            )
            self.pair_traders.append((f"{s1}_{s2}", s1, s2, pt))
        print(f"Loaded {len(self.pair_traders)} pair traders")

    def _resolve_price_marker(self, trial, param_name: str, marker: str, pt: PairTETrader, s1: str) -> float:
        """Универсальный расчёт ценовых границ относительно диапазона цен инструмента s1."""
        closes = pt.dfs[s1]['close']
        p_min = float(closes.min())
        p_max = float(closes.max())
        span = max(p_max - p_min, pt.main_price_step * 10)
        step = max(round(span / 50, 4), pt.main_price_step)

        if marker == '*low_price':
            low, high = p_min, p_min + span * 0.45
        elif marker == '*high_price':
            low, high = p_min + span * 0.55, p_max
        elif marker == '*subbuf_price':
            low, high = max(pt.main_price_step, p_min - span * 0.25), p_min
        elif marker == '*overbuf_price':
            low, high = p_max, p_max + span * 0.25
        else:
            raise ValueError(f"Неизвестный ценовой маркер: {marker}")

        val = trial.suggest_float(param_name, round(low, 4), round(high, 4), step=step)
        return round(round(val / pt.main_price_step) * pt.main_price_step, 6)

    def objective(self, trial, pair_key, s1, s2, pt: PairTETrader, strategy_class, param_options):
        params = []
        for i, options in enumerate(param_options):
            param_name = f"param_{i}"
            first_elem = options[0]

            # 1. Специальный ценовой маркер вида ('*low_price',)
            if isinstance(options, (list, tuple)) and len(options) == 1 and isinstance(first_elem, str) and first_elem.startswith('*'):
                params.append(self._resolve_price_marker(trial, param_name, first_elem, pt, s1))
                continue

            # 2. Категориальный список строк, кортежей или булевых значений
            # 2. Категориальный список строк, кортежей, булевых значений или с None
            if isinstance(options, (list, tuple)) and len(options) > 0 and (
                first_elem is None or isinstance(first_elem, (str, tuple, bool))
            ):
                params.append(trial.suggest_categorical(param_name, list(options)))
            # 3. Одиночное константное значение вида (0,) или (18,)
            elif isinstance(options, (list, tuple)) and len(options) == 1:
                params.append(first_elem)
            # 4. Диапазон с шагом (min, max, step)
            elif isinstance(options, (list, tuple)) and len(options) == 3:
                min_v, max_v, step_v = options
                if isinstance(step_v, int) and isinstance(min_v, int) and isinstance(max_v, int):
                    params.append(trial.suggest_int(param_name, min_v, max_v, step=step_v))
                else:
                    params.append(trial.suggest_float(param_name, min_v, max_v, step=step_v))
            # 5. Диапазон (min, max)
            elif isinstance(options, (list, tuple)) and len(options) == 2:
                min_v, max_v = options
                if isinstance(min_v, int) and isinstance(max_v, int):
                    params.append(trial.suggest_int(param_name, min_v, max_v))
                else:
                    params.append(trial.suggest_float(param_name, min_v, max_v))
            else:
                params.append(trial.suggest_categorical(param_name, list(options)))

        # Передаём s2 первым аргументом после (s1, price_step, mode)
        strategy = strategy_class(s1, pt.main_price_step, None, s2, *params)
        pt.ws = strategy

        if self.use_window_test:
            pt.check_strategy_window()
        else:
            pt.check_strategy_faster()

        stats = pt.get_statistics()
        if not (self.bottom_limit <= stats['count'] <= self.top_limit):
            raise optuna.TrialPruned()

        self.results_cache.setdefault(pair_key, {})[trial.number] = {
            'stats': stats,
            'params': params,
            'eq_unclosed': pt.get_portfolio_equity(unclosed=True).copy(),
            'eq_closed': pt.get_portfolio_equity(unclosed=False).copy(),
        }
        return float(stats[self.metric])

    def optimize_single_pair(self, pair_item, strategy_config):
        pair_key, s1, s2, pt = pair_item
        strategy_class, param_options = strategy_config
        name_bot = strategy_class.__name__

        self.results_cache[pair_key] = {}

        study = optuna.create_study(direction="maximize")
        study.optimize(
            lambda trial: self.objective(trial, pair_key, s1, s2, pt, strategy_class, param_options),
            n_trials=self.n_trials,
        )

        completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        if not completed:
            print(f"{pair_key} - N")
            return None

        top_trials = sorted(completed, key=lambda t: t.value, reverse=True)[:self.top_n]
        out_dir = os.path.join(self.main_folder, name_bot, pair_key)
        os.makedirs(out_dir, exist_ok=True)

        rows = []
        for t in top_trials:
            cached = self.results_cache[pair_key][t.number]
            p_list = cached['params']
            formatted_args = [f"'{s2}'"] + [f"'{v}'" if isinstance(v, str) else str(v) for v in p_list]
            ws_str = f"({name_bot},({','.join(formatted_args)},),None),"

            row = {'pair': pair_key, 'ws': ws_str} | cached['stats']
            rows.append(row)

            if self.need_plot:
                plt.figure(figsize=(12, 6))
                plt.plot(cached['eq_unclosed'], label='Portfolio Unclosed')
                plt.plot(cached['eq_closed'], label='Portfolio Closed')
                plt.title(f"{name_bot} {pair_key} (Trial {t.number})")
                plt.legend()
                plt.savefig(os.path.join(out_dir, f"{pair_key}_{name_bot}_trial{t.number}.png"), bbox_inches='tight')
                plt.close()

        df_res = pd.DataFrame(rows)
        df_res.to_excel(os.path.join(out_dir, f"{pair_key}_{name_bot}.xlsx"), index=False)
        best = df_res.iloc[0]
        print(f"{pair_key} - Y (best {self.metric}: {best[self.metric]:.2f}, trades: {best['count']})")
        return df_res

    def optimize_pair_strategy(self, strategy_config, n_trials=None):
        start_time = time()
        if n_trials is not None:
            self.n_trials = n_trials
        if not self.pair_traders:
            self.load_pair_traders()

        self.results_cache = {}
        strategy_class, _ = strategy_config
        print(f"\nTesting Pair Strategy: {strategy_class.__name__}")

        num_processes = min(max(1, self.phys_cores - self.save_cores), len(self.pair_traders))

        if num_processes > 1:
            print(f"Using {num_processes} processes...")
            worker = partial(self.optimize_single_pair, strategy_config=strategy_config)
            with Pool(processes=num_processes) as pool:
                pool.map(worker, self.pair_traders)
        else:
            print("Processing sequentially...")
            for pair_item in self.pair_traders:
                self.optimize_single_pair(pair_item, strategy_config)
        print(f"⏱ Pair optimization finished in {time() - start_time:.1f}s")