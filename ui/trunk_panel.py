from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QLineEdit, QComboBox, QAbstractItemView,
    QDoubleSpinBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from trunking.trunk_manager import TrunkSystem, TrunkChannel


class TrunkPanel(QWidget):
    system_added = pyqtSignal(TrunkSystem)
    system_removed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._systems: dict[str, TrunkSystem] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        group = QGroupBox("Trunking systémy")
        gl = QVBoxLayout(group)
        form = QFormLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Název systému")
        self._type_combo = QComboBox()
        self._type_combo.addItems(["P25 Phase 1", "DMR/MotoTRBO", "SmartNet"])
        self._band_plan = QComboBox()
        self._band_plan.addItems(["800MHz", "VHF/UHF", "1.3GHz"])
        ctrl_freq = QDoubleSpinBox()
        ctrl_freq.setRange(0, 6000)
        ctrl_freq.setValue(0)
        ctrl_freq.setSuffix(" MHz")
        ctrl_freq.setDecimals(5)
        self._ctrl_freq = ctrl_freq
        self._btn_add_sys = QPushButton("Přidat systém")
        self._btn_add_sys.clicked.connect(self._add_system)
        form.addRow("Název:", self._name_edit)
        form.addRow("Typ:", self._type_combo)
        form.addRow("Band plán:", self._band_plan)
        form.addRow("Control ch.:", ctrl_freq)
        form.addRow("", self._btn_add_sys)
        gl.addLayout(form)
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Systém", "Typ", "Kanály", "Hovory", "Stav"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        gl.addWidget(self._table)
        self._btn_remove = QPushButton("Odebrat systém")
        self._btn_remove.clicked.connect(self._remove_system)
        self._btn_edit = QPushButton("Upravit systém")
        gl.addWidget(self._btn_edit)
        gl.addWidget(self._btn_remove)
        self._calls_table = QTableWidget()
        self._calls_table.setColumnCount(4)
        self._calls_table.setHorizontalHeaderLabels(["Frekvence", "Talkgroup", "Čas", "Typ"])
        self._calls_table.horizontalHeader().setStretchLastSection(True)
        self._calls_table.setMaximumHeight(120)
        gl.addWidget(QLabel("Aktivní hovory:"))
        gl.addWidget(self._calls_table)
        layout.addWidget(group)

    def _add_system(self):
        name = self._name_edit.text().strip()
        if not name or name in self._systems:
            return
        stype = self._type_combo.currentText()
        proto = "P25" if "P25" in stype else ("DMR" if "DMR" in stype else "SmartNet")
        sys = TrunkSystem(name=name, system_type=proto, band_plan=self._band_plan.currentIndex())
        cf = self._ctrl_freq.value()
        if cf > 0:
            sys.control_channels.append(TrunkChannel(frequency=cf * 1e6, usage="control"))
        self._systems[name] = sys
        self.system_added.emit(sys)
        self._refresh()
        self._name_edit.clear()

    def _remove_system(self):
        rows = self._table.selectedIndexes()
        if rows:
            idx = rows[0].row()
            names = list(self._systems.keys())
            if 0 <= idx < len(names):
                self._systems.pop(names[idx])
                self.system_removed.emit(names[idx])
                self._refresh()

    def add_system_obj(self, sys: TrunkSystem):
        self._systems[sys.name] = sys
        self._refresh()

    def _refresh(self):
        self._table.setRowCount(len(self._systems))
        for i, (name, sys) in enumerate(self._systems.items()):
            self._table.setItem(i, 0, QTableWidgetItem(name))
            self._table.setItem(i, 1, QTableWidgetItem(sys.system_type))
            total = len(sys.control_channels) + len(sys.voice_channels)
            self._table.setItem(i, 2, QTableWidgetItem(str(total)))
            self._table.setItem(i, 3, QTableWidgetItem(str(len(sys.active_calls))))
            active = "▶ Aktivní" if sys.current_voice else "⏸ Pohotovost"
            self._table.setItem(i, 4, QTableWidgetItem(active))
        self._refresh_calls()

    def _refresh_calls(self):
        all_calls = []
        for sys in self._systems.values():
            for call in sys.active_calls[-20:]:
                all_calls.append(call)
        all_calls = all_calls[-50:]
        self._calls_table.setRowCount(len(all_calls))
        for i, call in enumerate(all_calls):
            self._calls_table.setItem(i, 0, QTableWidgetItem(f"{call.freq / 1e6:.5f}"))
            self._calls_table.setItem(i, 1, QTableWidgetItem(f"TG {call.talkgroup}"))
            t = __import__('time').strftime("%H:%M:%S", __import__('time').localtime(call.time))
            self._calls_table.setItem(i, 2, QTableWidgetItem(t))
            self._calls_table.setItem(i, 3, QTableWidgetItem("Voice" if not call.encrypted else "Encrypted"))

    def update_call_info(self, system_name: str, freq: float, **kw):
        sys = self._systems.get(system_name)
        if sys:
            sys.current_voice = freq
            self._refresh()

    @property
    def systems(self) -> dict:
        return self._systems
