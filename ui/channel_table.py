from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QHBoxLayout, QVBoxLayout, QWidget, QAbstractItemView,
    QMenu, QMessageBox, QFileDialog, QComboBox, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from scanner.scanner import Channel
import csv


class ChannelTableWidget(QWidget):
    channel_selected = pyqtSignal(Channel)
    channel_double_clicked = pyqtSignal(Channel)
    channels_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._channels: list[Channel] = []
        self._banks: dict[str, list[Channel]] = {"Default": []}
        self._current_bank = "Default"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        top = QHBoxLayout()
        top.addWidget(QLabel("Banka:"))
        self._bank_combo = QComboBox()
        self._bank_combo.addItem("Default")
        self._bank_combo.currentTextChanged.connect(self._bank_changed)
        top.addWidget(self._bank_combo)
        self._btn_new_bank = QPushButton("+")
        self._btn_new_bank.setFixedWidth(30)
        self._btn_new_bank.clicked.connect(self._new_bank)
        top.addWidget(self._btn_new_bank)
        layout.addLayout(top)
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "Frekvence", "Label", "Mod", "Squelch", "Krok",
            "Priorita", "CTCSS", "Bank", "Systém"
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.itemDoubleClicked.connect(
            lambda i: self.channel_double_clicked.emit(self._channels[i.row()])
        )
        btn_layout = QHBoxLayout()
        self._btn_remove = QPushButton("Odebrat")
        self._btn_remove.clicked.connect(self._remove_selected)
        self._btn_clear = QPushButton("Vyčistit")
        self._btn_clear.clicked.connect(self._clear_all)
        self._btn_import = QPushButton("Import CSV")
        self._btn_import.clicked.connect(self._import_csv)
        self._btn_export = QPushButton("Export CSV")
        self._btn_export.clicked.connect(self._export_csv)
        btn_layout.addWidget(self._btn_remove)
        btn_layout.addWidget(self._btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_import)
        btn_layout.addWidget(self._btn_export)
        layout.addWidget(self._table)
        layout.addLayout(btn_layout)
        self._status = QLabel("0 kanálů")
        layout.addWidget(self._status)

    def set_channels(self, channels: list[Channel]):
        self._channels = channels
        self._sync_banks()
        self._refresh()

    def add_channel(self, ch: Channel):
        ch.bank = self._current_bank
        self._channels.append(ch)
        if ch.bank not in self._banks:
            self._banks[ch.bank] = []
        self._banks[ch.bank].append(ch)
        self._refresh()
        self.channels_changed.emit()

    def _set_frequencies(self, channels: list[Channel]):
        self._channels = channels
        self._sync_banks()
        self._refresh()

    def _sync_banks(self):
        self._banks.clear()
        for ch in self._channels:
            b = ch.bank if ch.bank else "Default"
            if b not in self._banks:
                self._banks[b] = []
            self._banks[b].append(ch)
        current = self._bank_combo.currentText()
        self._bank_combo.blockSignals(True)
        self._bank_combo.clear()
        for b in self._banks:
            self._bank_combo.addItem(b)
        idx = self._bank_combo.findText(current)
        if idx >= 0:
            self._bank_combo.setCurrentIndex(idx)
        self._bank_combo.blockSignals(False)

    def _bank_changed(self, name: str):
        self._current_bank = name
        self._refresh()

    def _new_bank(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nová banka", "Název banky:")
        if ok and name.strip():
            name = name.strip()
            if name not in self._banks:
                self._banks[name] = []
                self._bank_combo.addItem(name)
                self._bank_combo.setCurrentText(name)

    def _refresh(self):
        bank = self._current_bank
        bank_channels = self._banks.get(bank, self._channels)
        if bank == "Default":
            bank_channels = self._channels
        else:
            bank_channels = self._banks.get(bank, [])
        self._table.setRowCount(len(bank_channels))
        for i, ch in enumerate(bank_channels):
            self._table.setItem(i, 0, QTableWidgetItem(f"{ch.frequency / 1e6:.5f}"))
            self._table.setItem(i, 1, QTableWidgetItem(ch.label))
            self._table.setItem(i, 2, QTableWidgetItem(ch.modulation))
            self._table.setItem(i, 3, QTableWidgetItem(f"{ch.squelch:.1f}"))
            self._table.setItem(i, 4, QTableWidgetItem(f"{ch.step_khz:.1f}"))
            self._table.setItem(i, 5, QTableWidgetItem(str(ch.priority)))
            self._table.setItem(i, 6, QTableWidgetItem(f"{ch.ctcss:.0f}" if ch.ctcss else ""))
            self._table.setItem(i, 7, QTableWidgetItem(ch.bank))
            self._table.setItem(i, 8, QTableWidgetItem(ch.trunk_system))
        self._status.setText(f"{len(bank_channels)} kanálů (banka: {bank})")

    def _on_selection(self):
        rows = self._table.selectedIndexes()
        if rows:
            idx = rows[0].row()
            bank = self._current_bank
            channels = self._banks.get(bank, self._channels)
            if 0 <= idx < len(channels):
                self.channel_selected.emit(channels[idx])

    def _remove_selected(self):
        rows = self._table.selectedIndexes()
        bank = self._current_bank
        channels = self._banks.get(bank, self._channels)
        indices = sorted(set(r.row() for r in rows), reverse=True)
        for idx in indices:
            if 0 <= idx < len(channels):
                ch = channels[idx]
                if ch in self._channels:
                    self._channels.remove(ch)
        self._sync_banks()
        self._refresh()
        self.channels_changed.emit()

    def _clear_all(self):
        self._channels.clear()
        self._banks.clear()
        self._banks["Default"] = []
        self._bank_combo.clear()
        self._bank_combo.addItem("Default")
        self._refresh()
        self.channels_changed.emit()

    def _context_menu(self, pos):
        menu = QMenu()
        menu.addAction("Upravit", self._edit_selected)
        menu.addAction("Ladit", self._tune_selected)
        menu.addSeparator()
        menu.addAction("Smazat", self._remove_selected)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _edit_selected(self):
        rows = self._table.selectedIndexes()
        if rows:
            from ui.frequency_editor import FrequencyEditor
            idx = rows[0].row()
            bank = self._current_bank
            channels = self._banks.get(bank, self._channels)
            if 0 <= idx < len(channels):
                dlg = FrequencyEditor(channels[idx], self)
                if dlg.exec():
                    self._refresh()
                    self.channels_changed.emit()

    def _tune_selected(self):
        rows = self._table.selectedIndexes()
        if rows:
            idx = rows[0].row()
            bank = self._current_bank
            channels = self._banks.get(bank, self._channels)
            if 0 <= idx < len(channels):
                self.channel_double_clicked.emit(channels[idx])

    def _import_csv(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV (*.csv)")
        if not fname:
            return
        count = 0
        with open(fname, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ch = Channel(
                        frequency=float(row.get('freq', row.get('frequency', 0))) * 1e6,
                        label=row.get('label', row.get('name', '')),
                        modulation=row.get('mod', row.get('modulation', 'NFM')),
                        squelch=float(row.get('squelch', 0.5)),
                        step_khz=float(row.get('step', row.get('step_khz', 12.5))),
                        bank=row.get('bank', self._current_bank),
                    )
                    self.add_channel(ch)
                    count += 1
                except:
                    pass
        QMessageBox.information(self, "Import", f"Importováno {count} kanálů")

    def _export_csv(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Export CSV", "channels.csv", "CSV (*.csv)")
        if not fname:
            return
        with open(fname, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['frequency', 'label', 'modulation', 'squelch', 'step_khz', 'bank'])
            for ch in self._channels:
                writer.writerow([
                    f"{ch.frequency / 1e6:.5f}", ch.label, ch.modulation,
                    ch.squelch, ch.step_khz, ch.bank
                ])
        QMessageBox.information(self, "Export", f"Exportováno {len(self._channels)} kanálů")

    @property
    def channels(self) -> list[Channel]:
        return self._channels

    @property
    def banks(self) -> dict:
        return self._banks
