#!/usr/bin/env python3
"""
SDRTrunk - Profesionální SDR rádio pro radioamatéry
Optimalizováno pro RTL-SDR, podpora Airspy

Funkce:
  - RTL-SDR a Airspy podpora s plnou kontrolou gainu
  - FM/NFM/WFM/AM/USB/LSB demodulace s AGC a filtry
  - Digitální dekodéry (DMR, P25, APRS) s detekcí synchronizace
  - CTCSS, DCS, DTMF dekódování
  - Trunk tracking (P25 Phase 1, DMR/MotoTRBO)
  - Spektrální analyzátor s peak hold a waterfall
  - Band plan overlay pro radioamatérská pásma
  - Skener s prioritními kanály a search módem
  - Memory banky, import/export CSV
  - Databáze českých retranslátorů a simplex kmitočtů
  - S-meter, nahrávání do WAV, detekce USB zařízení
  - Profesionální tmavé GUI (PyQt6)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow


DARK_THEME = """
QMainWindow, QWidget {
    background-color: #0d0d1a;
    color: #d0d0e0;
}
QGroupBox {
    border: 1px solid #2a2a4e;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 14px;
    font-weight: bold;
    color: #88aacc;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QTableWidget {
    background-color: #0f0f20;
    color: #d0d0e0;
    gridline-color: #1a1a3a;
    selection-background-color: #1a3a6a;
    selection-color: #ffffff;
}
QTableWidget::item:selected {
    background-color: #1a4a8a;
}
QHeaderView::section {
    background-color: #12122a;
    color: #88aacc;
    padding: 4px;
    border: 1px solid #1a1a3a;
    font-weight: bold;
}
QPushButton {
    background-color: #1a1a3a;
    color: #d0d0e0;
    border: 1px solid #2a4a6a;
    padding: 4px 10px;
    border-radius: 3px;
}
QPushButton:hover {
    background-color: #2a3a5a;
    border-color: #3a6a9a;
}
QPushButton:pressed {
    background-color: #0f1f3a;
}
QPushButton:disabled {
    background-color: #1a1a2a;
    color: #555;
    border-color: #1a1a2a;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #0f0f20;
    color: #d0d0e0;
    border: 1px solid #2a2a4e;
    padding: 3px;
    border-radius: 2px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #3a6a9a;
}
QComboBox::drop-down {
    background-color: #1a1a3a;
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #0f0f20;
    color: #d0d0e0;
    selection-background-color: #1a3a6a;
}
QSlider::groove:horizontal {
    background: #1a1a3a;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #00ff88;
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #1a4a8a;
    border-radius: 3px;
}
QCheckBox {
    color: #d0d0e0;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #2a4a6a;
    border-radius: 2px;
    background: #0f0f20;
}
QCheckBox::indicator:checked {
    background: #1a5a2a;
    border-color: #00aa44;
}
QTabWidget::pane {
    border: 1px solid #2a2a4e;
    background: #0d0d1a;
}
QTabBar::tab {
    background: #12122a;
    color: #888;
    padding: 6px 14px;
    border: 1px solid #1a1a3a;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #1a2a4a;
    color: #ffffff;
    border-color: #2a4a6a;
}
QTabBar::tab:hover {
    background: #1a2a3a;
    color: #ccc;
}
QTextEdit {
    background-color: #08081a;
    color: #00cc88;
    border: 1px solid #1a3a2a;
    font-family: "Courier New", monospace;
}
QStatusBar {
    background-color: #0f0f20;
    color: #88aacc;
    border-top: 1px solid #1a1a3a;
}
QLabel {
    color: #c0c0d0;
}
QSplitter::handle {
    background: #1a1a3a;
    height: 2px;
}
QMenuBar {
    background: #0f0f20;
    color: #c0c0d0;
    border-bottom: 1px solid #1a1a3a;
}
QMenuBar::item:selected {
    background: #1a3a6a;
}
QMenu {
    background: #0f0f20;
    color: #c0c0d0;
    border: 1px solid #2a2a4e;
}
QMenu::item:selected {
    background: #1a3a6a;
}
QScrollBar:vertical {
    background: #0a0a18;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #2a2a4e;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #3a5a7a;
}
"""


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("SDRTrunk")
    app.setOrganizationName("SDRTrunk")
    app.setStyleSheet(DARK_THEME)

    win = MainWindow()
    win.show()
    QApplication.processEvents()
    win._enumerate_devices()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
