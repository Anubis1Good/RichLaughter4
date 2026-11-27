import os
import shutil
import pandas as pd
from tqdm import tqdm


def build_optuna_summary(
    main_folder: str = r'_test_results/optuna',
    ignore_folders: tuple = ('archive', 'best_images'),
    amount_var: int = 1,
    sort_metric: str = 'total_fee_per',
):
    df_total = pd.DataFrame()
    best_images_root = os.path.join(main_folder, 'best_images')

    # Пересоздаём общую папку для лучших графиков
    if os.path.exists(best_images_root):
        shutil.rmtree(best_images_root)
    os.makedirs(best_images_root, exist_ok=True)

    inner_folders = os.listdir(main_folder)
    for inner_folder in tqdm(inner_folders, desc="Сбор результатов Optuna"):
        inner_folder_path = os.path.join(main_folder, inner_folder)
        if inner_folder in ignore_folders or not os.path.isdir(inner_folder_path):
            continue

        variant_folders = os.listdir(inner_folder_path)
        for variant_folder in variant_folders:
            variant_folder_path = os.path.join(inner_folder_path, variant_folder)
            if not os.path.isdir(variant_folder_path):
                continue

            files = os.listdir(variant_folder_path)
            for file in files:
                if file.endswith('.xlsx'):
                    file_path = os.path.join(variant_folder_path, file)
                    df_file = pd.read_excel(file_path, 'total')
                    if not df_file.empty:
                        top_rows = df_file.head(amount_var)
                        df_total = top_rows if df_total.empty else pd.concat([df_total, top_rows], ignore_index=True)

                        # Копируем графики лучших прогонов в общую папку best_images/<TICKER>/
                        images_src_dir = os.path.join(variant_folder_path, 'Images')
                        if os.path.isdir(images_src_dir):
                            for _, row in top_rows.iterrows():
                                img_name = f"{row['name']}.png"
                                src_img = os.path.join(images_src_dir, img_name)
                                if os.path.isfile(src_img):
                                    ticker_dst_dir = os.path.join(best_images_root, str(row['origin']))
                                    os.makedirs(ticker_dst_dir, exist_ok=True)
                                    shutil.copy2(src_img, os.path.join(ticker_dst_dir, img_name))

    if df_total.empty:
        print("Нет данных для агрегации.")
        return

    # Убираем ненужные технические колонки
    cols_to_drop = ['Unnamed: 0', 'amount_sl', 'amount_tp', 'sl/tp', 'sl_pct', 'tp_pct']
    df_total = df_total.drop(columns=[c for c in cols_to_drop if c in df_total.columns])

    # Переставляем 'origin' в начало и сортируем по тикеру и выбранной метрике
    cols = df_total.columns.tolist()
    if 'origin' in cols:
        cols.remove('origin')
        cols = ['origin'] + cols
        df_total = df_total[cols]

    df_total = df_total.sort_values(['origin', sort_metric], ascending=[True, False]).reset_index(drop=True)
    df_total['ws_name'] = df_total['ws'].str.extract(r'^\(?([^,(]+)')
    df_total['ws_type'] = df_total['ws_name'].str[:3]

    # 1. Ранжирование внутри каждого тикера
    df_ranked = df_total.copy()
    df_ranked['rank'] = df_ranked.groupby('origin')[sort_metric].rank(method='min', ascending=False)
    df_ranked = df_ranked.sort_values(['origin', 'rank']).reset_index(drop=True)

    # 2. Агрегация по ws_name (по среднему рангу)
    df_ws_name_agg = df_ranked.groupby('ws_name').agg({
        'rank': 'mean',
        'count': 'mean',
        'total_fee_per': 'mean',
        'win_rate_wf': 'mean',
    }).reset_index()
    df_ws_name_agg.columns = ['ws_name', 'avg_rank', 'avg_count', 'avg_total_fee_per', 'avg_win_rate_wf']
    df_ws_name_agg = df_ws_name_agg.sort_values('avg_rank').reset_index(drop=True)

    # 3. Агрегация по ws_type (по среднему рангу)
    df_ws_type_agg = df_ranked.groupby('ws_type').agg({
        'rank': 'mean',
        'count': 'mean',
        'total_fee_per': 'mean',
        'win_rate_wf': 'mean',
    }).reset_index()
    df_ws_type_agg.columns = ['ws_type', 'avg_rank', 'avg_count', 'avg_total_fee_per', 'avg_win_rate_wf']
    df_ws_type_agg = df_ws_type_agg.sort_values('avg_rank').reset_index(drop=True)

    # 4. Агрегация по доходности (ws_name)
    df_fee_agg = df_ranked.groupby('ws_name').agg({
        'total_fee_per': 'mean',
        'count': 'mean',
        'win_rate_wf': 'mean',
    }).reset_index()
    df_fee_agg.columns = ['ws_name', 'avg_total_fee_per', 'avg_count', 'avg_win_rate_wf']
    df_fee_agg = df_fee_agg.sort_values('avg_total_fee_per', ascending=False).reset_index(drop=True)

    # 5. Агрегация по доходности (ws_type)
    df_fee_type_agg = df_ranked.groupby('ws_type').agg({
        'total_fee_per': 'mean',
        'count': 'mean',
        'win_rate_wf': 'mean',
    }).reset_index()
    df_fee_type_agg.columns = ['ws_type', 'avg_total_fee_per', 'avg_count', 'avg_win_rate_wf']
    df_fee_type_agg = df_fee_type_agg.sort_values('avg_total_fee_per', ascending=False).reset_index(drop=True)

    # === СОХРАНЕНИЕ В EXCEL ===
    full_name_doc = os.path.join(main_folder, 'total_optuna.xlsx')
    with pd.ExcelWriter(full_name_doc, engine='xlsxwriter') as writer:
        df_total.to_excel(writer, sheet_name='total', index=True)
        worksheet = writer.sheets['total']
        workbook = writer.book
        worksheet.set_column(0, 0, 8)

        for i, col in enumerate(df_total.columns):
            col_idx = i + 1
            width = min(max(df_total[col].astype(str).apply(len).max(), len(col)) + 2, 55)
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
            ('ws_type_agg', df_ws_type_agg),
            ('fee_agg', df_fee_agg),
            ('fee_type_agg', df_fee_type_agg),
        ]
        for sheet_name, df_sheet in sheets:
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=True)
            ws_sheet = writer.sheets[sheet_name]
            ws_sheet.set_column(0, 0, 8)
            for i, col in enumerate(df_sheet.columns):
                col_idx = i + 1
                width = min(max(df_sheet[col].astype(str).apply(len).max(), len(col)) + 2, 55)
                ws_sheet.set_column(col_idx, col_idx, width)

    print(f"Готово! Сводный отчёт сохранён: {full_name_doc}")
    print(f"Графики лучших роботов скопированы в: {best_images_root}")


if __name__ == '__main__':
    build_optuna_summary()
