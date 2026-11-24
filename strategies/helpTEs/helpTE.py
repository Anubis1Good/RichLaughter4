import os
import json
from datetime import datetime
from typing import Dict, Any
import pandas as pd
from strategies.BaseTE import BaseTE

class TestTE(BaseTE):
    def __init__(self, symbol='Test',price_step=None,mode=None, stop=None, take=None):
        super().__init__(symbol, price_step, mode, stop, take)
        self.needs_info = {'chart':True,'full_glass':True}
        self.type_te = 2
        # tdata - trading data
    def preprocessing(self,tdata):
        pdata = {}
        df = tdata['chart']
        df['test_top_level'] = df['high'].rolling(20).max()
        df['test_bottom_level'] = df['low'].rolling(20).min()
        top_level = df['test_top_level'].iat[-1]
        bottom_level = df['test_bottom_level'].iat[-1]
        # print(self.symbol,tdata)
        pdata['levels'] = [top_level,bottom_level]
        return pdata
    
    # pdata - processed data
    def get_raw_action(self,pdata):
        return 'spred_all_level'
        return 'test'
    

class CloseAllTE(BaseTE):
    def __init__(self, symbol='Test', price_step=None, mode=None, stop=None, take=None):
        super().__init__(symbol, price_step, mode, stop, take)
    
    def get_raw_action(self, pdata):
        return 'close_all'






class InspectorTE(BaseTE):
    """
    Вспомогательный робот-инспектор.
    Запрашивает ВСЕ доступные типы данных через needs_info и сохраняет их
    в папку `_logs/inspector/` для изучения форматов.
    Торговых заявок не выставляет (всегда возвращает None).
    """

    def __init__(self, symbol: str = 'Test', price_step=None, mode=None, save_once: bool = True, **kwargs):
        super().__init__(symbol=symbol, price_step=price_step, mode=mode, **kwargs)
        self.save_once = save_once
        self._already_saved = False

        # Запрашиваем абсолютно все каналы данных из CSTrader._collect_tdata
        self.needs_info = {
            'chart': True,
            'charts': (self.symbol,),
            'tapes': (self.symbol,),
            'spred': True,
            'full_glass': True,
            'poss': (self.symbol,),
            'orders': True,
            'clusters': True
        }

    def preprocessing(self, tdata: Dict[str, Any]) -> Dict[str, Any]:
        if self.save_once and self._already_saved:
            return tdata

        out_dir = os.path.join('_logs', 'inspector', f"{self.symbol}_{datetime.now().strftime('%H%M%S')}")
        os.makedirs(out_dir, exist_ok=True)

        summary = []

        for key, val in tdata.items():
            if isinstance(val, pd.DataFrame):
                val.to_csv(os.path.join(out_dir, f"{key}.csv"), index=False)
                summary.append(f"[{key}] DataFrame shape={val.shape}, cols={list(val.columns)}")
            elif isinstance(val, dict):
                # Проверяем, нет ли внутри словаря DataFrame (как в 'charts' или 'tapes')
                serializable = {}
                for sub_k, sub_v in val.items():
                    if isinstance(sub_v, pd.DataFrame):
                        sub_v.to_csv(os.path.join(out_dir, f"{key}_{sub_k}.csv"), index=False)
                        summary.append(f"[{key}][{sub_k}] DataFrame shape={sub_v.shape}, cols={list(sub_v.columns)}")
                    elif isinstance(sub_v, list) and sub_v and isinstance(sub_v[0], pd.DataFrame):
                        for idx, df_item in enumerate(sub_v):
                            df_item.to_csv(os.path.join(out_dir, f"{key}_{sub_k}_{idx}.csv"), index=False)
                            summary.append(f"[{key}][{sub_k}][{idx}] DataFrame shape={df_item.shape}, cols={list(df_item.columns)}")
                    else:
                        serializable[str(sub_k)] = sub_v

                if serializable:
                    with open(os.path.join(out_dir, f"{key}.json"), 'w', encoding='utf-8') as f:
                        json.dump(serializable, f, ensure_ascii=False, indent=2, default=str)
                    summary.append(f"[{key}] JSON keys={list(serializable.keys())}")
            else:
                with open(os.path.join(out_dir, f"{key}.txt"), 'w', encoding='utf-8') as f:
                    f.write(f"type: {type(val)}\nvalue: {val}\n")
                summary.append(f"[{key}] {type(val).__name__} = {val}")

        with open(os.path.join(out_dir, "_SUMMARY.txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(summary))

        print(f"\n=== [InspectorTE: {self.symbol}] Данные сохранены в {out_dir} ===")
        for line in summary:
            print("  ", line)
        print("=" * 60 + "\n")

        self._already_saved = True
        return tdata

    def get_raw_action(self, pdata: Dict[str, Any]) -> Any:
        # Никогда не торгуем, только наблюдаем
        return None
