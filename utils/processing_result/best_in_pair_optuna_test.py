import os
import shutil
import pandas as pd
from tqdm import tqdm


def build_pair_optuna_summary(
    main_folder: str = r'_test_results\pair_optuna',
    ignore_folders: tuple = ('archive', 'best_images'),
    amount_var: int = 1,
    sort_metric: str = 'total_wfee',
):
    if not os.path.exists(main_folder):
        print(f"Папка не найдена: {main_folder}")
        return

    df_total = pd.DataFrame()
    best_images_root = os.path.join(main_folder, 'best_images')

    if os.path.exists(best_images_root):
        shutil.rmtree(best_images_root)
    os.makedirs(best_images_root, exist_ok=True)

    strategy_folders = os.listdir(main_folder)
    for strat_folder in tqdm(strategy_folders, desc="Сбор результатов Pair Optuna"):
        strat_path = os.path.join(main_folder, strat_folder)
        if strat_folder in ignore_folders or not os.path.isdir(strat_path):
            continue

        pair_folders = os.listdir(strat_path)
        for pair_folder in pair_folders:
            pair_path = os.path.join(strat_path, pair_folder)
            if not os.path.isdir(pair_path):
                continue

            for file in os.listdir(pair_path):
                if file.endswith('.xlsx'):
                    file_path = os.path.join(pair_path, file)
                    df_file = pd.read_excel(file_path)
                    if not df_file.empty:
                        top_rows = df_file.head(amount_var).copy()
                        df_total = top_rows if df_total.empty else pd.concat([df_total, top_rows], ignore_index=True)

                        # Копируем графики лучших прогонов в best_images/<PAIR>/
                        for img_file in os.listdir(pair_path):
                            if img_file.endswith('.png'):
                                src_img = os.path.join(pair_path, img_file)
                                pair_dst_dir = os.path.join(best_images_root, str(pair_folder))
                                os.makedirs(pair_dst_dir, exist_ok=True)
                                shutil.copy2(src_img, os.path.join(pair_dst_dir, img_file))

    if df_total.empty:
        print("Нет данных для агрегации.")
        return

    # Удаляем лишние колонки при наличии
    cols_to_drop = ['Unnamed: 0', 'curve_composite', 'curve_lex']
    param_cols = [c for c in df_total.columns if str(c).startswith('Param_')]
    df_total = df_total.drop(columns=[c for c in (cols_to_drop + param_cols) if c in df_total.columns])

    # Переставляем 'pair' в начало и сортируем
    cols = df_total.columns.tolist()
    if 'pair' in cols:
        cols.remove('pair')
        cols = ['pair'] + cols
        df_total = df_total[cols]

    df_total = df_total.sort_values(['pair', sort_metric], ascending=[True, False]).reset_index(drop=True)
    df_total['ws_name'] = df_total['ws'].str.extract(r'^\(?([^,(]+)')

    # 1. Ранжирование внутри каждой пары
    df_ranked = df_total.copy()
    df_ranked['rank'] = df_ranked.groupby('pair')[sort_metric].rank(method='min', ascending=False)
    df_ranked = df_ranked.sort_values(['pair', 'rank']).reset_index(drop=True)

    # 2. Агрегация по стратегиям (по среднему рангу)
    df_ws_name_agg = df_ranked.groupby('ws_name').agg({
        'rank': 'mean',
        'count': 'mean',
        'total_wfee': 'mean',
        'eq_day': 'mean',
        'max_dropdown': 'mean',
    }).reset_index()
    df_ws_name_agg.columns = ['ws_name', 'avg_rank', 'avg_count', 'avg_total_wfee', 'avg_eq_day', 'avg_max_dd']
    df_ws_name_agg = df_ws_name_agg.sort_values('avg_rank').reset_index(drop=True)

    # 3. Агрегация по парам инструментов
    df_pair_agg = df_ranked.groupby('pair').agg({
        'total_wfee': 'mean',
        'eq_day': 'mean',
        'count': 'mean',
        'max_dropdown': 'mean',
    }).reset_index()
    df_pair_agg.columns = ['pair', 'avg_total_wfee', 'avg_eq_day', 'avg_count', 'avg_max_dd']
    df_pair_agg = df_pair_agg.sort_values('avg_total_wfee', ascending=False).reset_index(drop=True)

    # 4. Агрегация стратегий по средней доходности
    df_fee_agg = df_ws_name_agg.sort_values('avg_total_wfee', ascending=False).reset_index(drop=True)

    # === СОХРАНЕНИЕ В EXCEL ===
    full_name_doc = os.path.join(main_folder, 'total_pair_optuna.xlsx')
    with pd.ExcelWriter(full_name_doc, engine='xlsxwriter') as writer:
        df_total.to_excel(writer, sheet_name='total', index=True)
        worksheet = writer.sheets['total']
        workbook = writer.book
        worksheet.set_column(0, 0, 8)

        for i, col in enumerate(df_total.columns):
            col_idx = i + 1
            width = min(max(df_total[col].astype(str).apply(len).max(), len(col)) + 2, 60)
            worksheet.set_column(col_idx, col_idx, width)
            worksheet.conditional_format(1, col_idx, len(df_total), col_idx, {
                'type': 'cell',
                'criteria': 'less than',
                'value': 0,
                'format': workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
            })
            worksheet.conditional_format(1, col_idx, len(df_total), col_idx, {
                'type': '3_color_scale',
                'min_color': '#DA9694',
                'mid_color': '#FFFFFF',
                'max_color': '#00B0F0'
            })

        sheets = [
            ('ranked', df_ranked),
            ('ws_name_agg', df_ws_name_agg),
            ('pair_agg', df_pair_agg),
            ('fee_agg', df_fee_agg),
        ]
        for sheet_name, df_sheet in sheets:
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=True)
            ws_sheet = writer.sheets[sheet_name]
            ws_sheet.set_column(0, 0, 8)
            for i, col in enumerate(df_sheet.columns):
                col_idx = i + 1
                width = min(max(df_sheet[col].astype(str).apply(len).max(), len(col)) + 2, 60)
                ws_sheet.set_column(col_idx, col_idx, width)

    print(f"Готово! Сводный отчёт по парам сохранён: {full_name_doc}")
    print(f"Графики лучших парных роботов скопированы в: {best_images_root}")


if __name__ == '__main__':
    build_pair_optuna_summary()
