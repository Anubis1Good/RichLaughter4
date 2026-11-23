import shutil
from PyQt5.QtCore import QThread, pyqtSignal, QMutex
from PyQt5.QtWidgets import (
    QApplication, QWidget, QListWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QLabel, QCheckBox
)

from traders.cscalp_sdk_trader.CSTrader import CSTrader
from traders.cscalp_sdk_trader.sgs import pc_groups

ERROR_FOLDER = '_logs/error_logs_CSTrader'


class CSTradeWorker(QThread):
    status_signal = pyqtSignal(str)

    def __init__(self, group_key: str, debug_mode: bool = True, poll_ms: int = 500):
        super().__init__()
        self.group_key = group_key
        self.debug_mode = debug_mode
        self.poll_ms = poll_ms
        self._lock = QMutex()
        self.trader: CSTrader | None = None
        self._pending_force_mode: int | None = None

    def set_force_mode(self, mode: int | None):
        self._lock.lock()
        self._pending_force_mode = mode
        if self.trader is not None:
            self.trader.set_force_mode(mode)
        self._lock.unlock()

    def run(self):
        try:
            shutil.rmtree(ERROR_FOLDER, ignore_errors=True)
            group_cfg = pc_groups[self.group_key]
            self.status_signal.emit(f"Подключение ({self.group_key})...")

            trader = CSTrader(group_cfg, debug_mode=self.debug_mode)

            self._lock.lock()
            trader.set_force_mode(self._pending_force_mode)
            self.trader = trader
            self._lock.unlock()

            self.status_signal.emit(f"Торгуем: {self.group_key}")

            while not self.isInterruptionRequested():
                self.trader.run_once()
                # Дробим паузу на шаги по 50 мс для мгновенной реакции на StopTrade
                steps = max(1, self.poll_ms // 50)
                for _ in range(steps):
                    if self.isInterruptionRequested():
                        return
                    self.msleep(50)

        except Exception as e:
            print(f"[CSTradeWorker ERROR] {type(e).__name__}: {e}")
            self.status_signal.emit(f"Ошибка: {e}")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('StartCS (CScalp SDK)')
        self.resize(650, 420)

        self.init_btn_style = """
            QPushButton {
                background-color: #006561;
                color: white;
                padding: 10px;
                border-radius: 5px;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6C0AAB;
            }
            QPushButton:pressed {
                background-color: #A6A600;
            }
            QPushButton:disabled {
                background-color: #4A7A78;
                color: #CCCCCC;
            }
        """

        self.setStyleSheet(f"""
            QWidget {{
                background-color: #5CCDC9;
            }}
            QListWidget {{
                background-color: #FFFFFF;
                border-radius: 5px;
                border: none;
                font-size: 15px;
            }}
            QListWidget::item {{
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 8px;
                margin: 3px;
                background-color: #009B95;
                color: white;
            }}
            QListWidget::item:selected {{
                background-color: #A6A600;
                border: 1px solid #999;
            }}
            QListWidget::item:hover {{
                background-color: #6C0AAB;
                border: 1px solid #999;
            }}
            QLabel {{
                background-color: #009B95;
                qproperty-alignment: 'AlignCenter';
                border-radius: 5px;
                color: white;
                font-size: 16px;
                padding: 8px;
            }}
            QCheckBox {{
                color: #003B38;
                font-size: 15px;
                font-weight: bold;
                padding: 4px;
            }}
            {self.init_btn_style}
        """)

        line1 = QVBoxLayout()
        line2 = QVBoxLayout()

        self.list_sgs = QListWidget()
        self.list_sgs.addItems(list(pc_groups.keys()))
        self.list_sgs.setCurrentRow(0)
        line1.addWidget(self.list_sgs)

        self.cur_sg = list(pc_groups.keys())[0]
        self.sg_lbl = QLabel(text=f"Группа: {self.cur_sg}")
        self.status_lbl = QLabel(text="Статус: Ожидание")

        self.debug_chk = QCheckBox("Debug Mode (чёрный ящик)")
        self.debug_chk.setChecked(True)

        self.trader_btn = QPushButton(text='StartTrade')
        self.stop_btn = QPushButton(text='StopTrade')
        self.stop_btn.setDisabled(True)

        # Две кнопки управления режимами закрытия
        self.only_close_btn = QPushButton(text='Only Close (-2)')
        self.only_close_btn.setCheckable(True)

        self.force_close_btn = QPushButton(text='Force Close All (-1)')
        self.force_close_btn.setCheckable(True)

        line2.addWidget(self.sg_lbl)
        line2.addWidget(self.status_lbl)
        line2.addWidget(self.debug_chk)
        line2.addWidget(self.trader_btn)
        line2.addWidget(self.stop_btn)
        line2.addSpacing(10)
        line2.addWidget(self.only_close_btn)
        line2.addWidget(self.force_close_btn)

        main_layout = QHBoxLayout()
        main_layout.addLayout(line1, stretch=1)
        main_layout.addLayout(line2, stretch=2)
        self.setLayout(main_layout)

        self.worker: CSTradeWorker | None = None

        self.list_sgs.itemClicked.connect(self.set_sg)
        self.trader_btn.clicked.connect(self.start_worker)
        self.stop_btn.clicked.connect(self.stop_worker)
        self.only_close_btn.clicked.connect(self.on_only_close_toggled)
        self.force_close_btn.clicked.connect(self.on_force_close_toggled)

    def set_sg(self):
        self.cur_sg = self.list_sgs.currentItem().text()
        self.sg_lbl.setText(f"Группа: {self.cur_sg}")

    def _get_selected_force_mode(self) -> int | None:
        if self.force_close_btn.isChecked():
            return -1
        if self.only_close_btn.isChecked():
            return -2
        return None

    def _update_mode_buttons_style(self):
        if self.only_close_btn.isChecked():
            self.only_close_btn.setStyleSheet('background-color: #D97706; color: white; padding: 10px; border-radius: 5px; font-size: 16px; font-weight: bold;')
        else:
            self.only_close_btn.setStyleSheet(self.init_btn_style)

        if self.force_close_btn.isChecked():
            self.force_close_btn.setStyleSheet('background-color: #DC2626; color: white; padding: 10px; border-radius: 5px; font-size: 16px; font-weight: bold;')
        else:
            self.force_close_btn.setStyleSheet(self.init_btn_style)

    def on_only_close_toggled(self, checked: bool):
        if checked:
            self.force_close_btn.setChecked(False)
        self._update_mode_buttons_style()
        mode = self._get_selected_force_mode()
        if self.worker and self.worker.isRunning():
            self.worker.set_force_mode(mode)

    def on_force_close_toggled(self, checked: bool):
        if checked:
            self.only_close_btn.setChecked(False)
        self._update_mode_buttons_style()
        mode = self._get_selected_force_mode()
        if self.worker and self.worker.isRunning():
            self.worker.set_force_mode(mode)

    def start_worker(self):
        if self.worker and self.worker.isRunning():
            return

        self.worker = CSTradeWorker(self.cur_sg, debug_mode=self.debug_chk.isChecked())
        self.worker.set_force_mode(self._get_selected_force_mode())
        self.worker.status_signal.connect(self.status_lbl.setText)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

        self.trader_btn.setText("Trading...")
        self.trader_btn.setStyleSheet('background-color: #A6A600; color: white; padding: 10px; border-radius: 5px; font-size: 16px; font-weight: bold;')
        self.trader_btn.setDisabled(True)
        self.stop_btn.setDisabled(False)
        self.list_sgs.setDisabled(True)
        self.debug_chk.setDisabled(True)

    def on_worker_finished(self):
        self.trader_btn.setText("StartTrade")
        self.trader_btn.setStyleSheet(self.init_btn_style)
        self.trader_btn.setDisabled(False)
        self.stop_btn.setDisabled(True)
        self.list_sgs.setDisabled(False)
        self.debug_chk.setDisabled(False)
        self.status_lbl.setText("Статус: Остановлен")
        print('Trading has been stopped')

    def stop_worker(self):
        if self.worker and self.worker.isRunning():
            self.status_lbl.setText("Остановка...")
            self.worker.requestInterruption()
            self.worker.quit()
            self.worker.wait(3000)

    def closeEvent(self, event):
        self.stop_worker()
        event.accept()


if __name__ == '__main__':
    app = QApplication([])
    main_window = MainWindow()
    main_window.show()
    app.exec()
