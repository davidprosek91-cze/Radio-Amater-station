from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QDoubleSpinBox, QGroupBox, QFormLayout, QComboBox,
    QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from scanner.scanner import ScannerEngine


class ScannerPanel(QWidget):
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    hold_requested = pyqtSignal()
    resume_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: ScannerEngine = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        group = QGroupBox("Skener")
        gl = QVBoxLayout(group)
        btn_layout = QHBoxLayout()
        self._btn_start = QPushButton("▶ Start")
        self._btn_start.setStyleSheet("QPushButton { color: #00ff88; font-weight: bold; }")
        self._btn_start.clicked.connect(self.start_requested)
        self._btn_stop = QPushButton("■ Stop")
        self._btn_stop.clicked.connect(self.stop_requested)
        self._btn_stop.setEnabled(False)
        self._btn_hold = QPushButton("❚ Hold")
        self._btn_hold.clicked.connect(self.hold_requested)
        self._btn_hold.setEnabled(False)
        self._btn_resume = QPushButton("▶ Resume")
        self._btn_resume.clicked.connect(self.resume_requested)
        self._btn_resume.setEnabled(False)
        btn_layout.addWidget(self._btn_start)
        btn_layout.addWidget(self._btn_stop)
        btn_layout.addWidget(self._btn_hold)
        btn_layout.addWidget(self._btn_resume)
        gl.addLayout(btn_layout)
        form = QFormLayout()
        self._hold_time = QSpinBox()
        self._hold_time.setRange(100, 30000)
        self._hold_time.setValue(3000)
        self._hold_time.setSuffix(" ms")
        self._hold_time.valueChanged.connect(self._on_param_change)
        self._hang_time = QSpinBox()
        self._hang_time.setRange(100, 30000)
        self._hang_time.setValue(2000)
        self._hang_time.setSuffix(" ms")
        self._hang_time.valueChanged.connect(self._on_param_change)
        self._threshold_db = QDoubleSpinBox()
        self._threshold_db.setRange(-120, 0)
        self._threshold_db.setValue(-40)
        self._threshold_db.setSuffix(" dB")
        self._threshold_db.valueChanged.connect(self._on_param_change)
        self._priority_interval = QSpinBox()
        self._priority_interval.setRange(1, 20)
        self._priority_interval.setValue(3)
        self._priority_interval.setSuffix(" cyklů")
        form.addRow("Hold čas:", self._hold_time)
        form.addRow("Hang čas:", self._hang_time)
        form.addRow("Práh signálu:", self._threshold_db)
        form.addRow("Priorita každých:", self._priority_interval)
        gl.addLayout(form)
        search_group = QGroupBox("Search mód")
        sg = QFormLayout(search_group)
        self._search_lo = QDoubleSpinBox()
        self._search_lo.setRange(0, 6000)
        self._search_lo.setValue(144.0)
        self._search_lo.setSuffix(" MHz")
        self._search_hi = QDoubleSpinBox()
        self._search_hi.setRange(0, 6000)
        self._search_hi.setValue(148.0)
        self._search_hi.setSuffix(" MHz")
        self._search_step = QDoubleSpinBox()
        self._search_step.setRange(0.001, 100)
        self._search_step.setValue(12.5)
        self._search_step.setSuffix(" kHz")
        self._chk_search = QCheckBox("Povolit search")
        sg.addRow("Od:", self._search_lo)
        sg.addRow("Do:", self._search_hi)
        sg.addRow("Krok:", self._search_step)
        sg.addRow("", self._chk_search)
        gl.addWidget(search_group)
        self._status = QLabel("Stav: Zastaveno")
        gl.addWidget(self._status)
        layout.addWidget(group)
        layout.addStretch()

    def set_engine(self, engine: ScannerEngine):
        self._engine = engine

    def update_status(self, text: str):
        self._status.setText(f"Stav: {text}")

    def set_running(self, running: bool):
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self._btn_hold.setEnabled(running)
        if not running:
            self._btn_hold.setEnabled(False)
            self._btn_resume.setEnabled(False)

    def set_holding(self, holding: bool):
        self._btn_hold.setEnabled(not holding)
        self._btn_resume.setEnabled(holding)

    def _on_param_change(self):
        if self._engine:
            self._engine.set_hold_time(self._hold_time.value())
            self._engine.set_hang_time(self._hang_time.value())
