from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QDoubleSpinBox, QComboBox, QPushButton, QLabel, QDialogButtonBox,
    QGroupBox, QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt
from scanner.scanner import Channel
from config.settings import CTCSS_TONES


class FrequencyEditor(QDialog):
    def __init__(self, channel: Channel = None, parent=None, banks: list = None):
        super().__init__(parent)
        self._channel = channel or Channel(frequency=145.500e6)
        self._banks = banks or ["Default"]
        self.setWindowTitle("Editor frekvence" if not channel else "Upravit frekvenci")
        self.setMinimumWidth(480)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        main_group = QGroupBox("Parametry kanálu")
        form = QFormLayout(main_group)
        self._freq = QDoubleSpinBox()
        self._freq.setRange(0, 10000)
        self._freq.setDecimals(5)
        self._freq.setValue(self._channel.frequency / 1e6)
        self._freq.setSuffix(" MHz")
        self._freq.setSingleStep(0.0125)
        self._label = QLineEdit(self._channel.label)
        self._label.setPlaceholderText("Název stanice")
        self._mod = QComboBox()
        self._mod.addItems(["NFM", "FM", "AM", "WFM", "USB", "LSB"])
        self._mod.setCurrentText(self._channel.modulation)
        self._step = QDoubleSpinBox()
        self._step.setRange(0.1, 1000)
        self._step.setValue(self._channel.step_khz)
        self._step.setSuffix(" kHz")
        self._bw = QDoubleSpinBox()
        self._bw.setRange(1, 200)
        self._bw.setValue(self._channel.bandwidth / 1000)
        self._bw.setSuffix(" kHz")
        self._priority = QSpinBox()
        self._priority.setRange(0, 10)
        self._priority.setValue(self._channel.priority)
        self._bank = QComboBox()
        self._bank.addItems(self._banks)
        if self._channel.bank in self._banks:
            self._bank.setCurrentText(self._channel.bank)
        form.addRow("Frekvence:", self._freq)
        form.addRow("Label:", self._label)
        form.addRow("Modulace:", self._mod)
        form.addRow("Krok:", self._step)
        form.addRow("Šířka pásma:", self._bw)
        form.addRow("Priorita:", self._priority)
        form.addRow("Banka:", self._bank)
        layout.addWidget(main_group)
        squelch_group = QGroupBox("Squelch a tóny")
        sq = QFormLayout(squelch_group)
        self._squelch = QDoubleSpinBox()
        self._squelch.setRange(0, 1)
        self._squelch.setSingleStep(0.05)
        self._squelch.setValue(self._channel.squelch)
        self._squelch_type = QComboBox()
        self._squelch_type.addItems(["noise", "power", "ctcss", "off"])
        self._ctcss = QComboBox()
        self._ctcss.addItem("---")
        for t in CTCSS_TONES:
            self._ctcss.addItem(f"{t:.1f} Hz")
        if self._channel.ctcss > 0:
            idx = self._ctcss.findText(f"{self._channel.ctcss:.1f} Hz")
            if idx >= 0:
                self._ctcss.setCurrentIndex(idx)
        self._tone_squelch = QCheckBox("Tónový squelch")
        self._tone_squelch.setChecked(self._channel.tone_squelch)
        self._agc = QCheckBox("AGC")
        self._agc.setChecked(self._channel.agc)
        self._nb = QCheckBox("Noise blanker")
        self._nb.setChecked(self._channel.noise_blanker)
        sq.addRow("Squelch:", self._squelch)
        sq.addRow("Typ squelche:", self._squelch_type)
        sq.addRow("CTCSS:", self._ctcss)
        sq.addRow("", self._tone_squelch)
        sq.addRow("", self._agc)
        sq.addRow("", self._nb)
        layout.addWidget(squelch_group)
        trunk_group = QGroupBox("Trunking")
        tr = QFormLayout(trunk_group)
        self._trunk_system = QLineEdit(self._channel.trunk_system)
        self._trunk_system.setPlaceholderText("Název trunk systému")
        self._color_code = QSpinBox()
        self._color_code.setRange(0, 15)
        self._color_code.setValue(self._channel.color_code)
        self._nac = QSpinBox()
        self._nac.setRange(0, 4095)
        self._nac.setValue(self._channel.nac)
        tr.addRow("Trunk systém:", self._trunk_system)
        tr.addRow("Color code:", self._color_code)
        tr.addRow("NAC:", self._nac)
        layout.addWidget(trunk_group)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_channel(self) -> Channel:
        self._channel.frequency = self._freq.value() * 1e6
        self._channel.label = self._label.text()
        self._channel.modulation = self._mod.currentText()
        self._channel.step_khz = self._step.value()
        self._channel.bandwidth = self._bw.value() * 1000
        self._channel.priority = self._priority.value()
        self._channel.bank = self._bank.currentText()
        self._channel.squelch = self._squelch.value()
        self._channel.squelch_type = self._squelch_type.currentText()
        ctcss_text = self._ctcss.currentText()
        self._channel.ctcss = float(ctcss_text.split()[0]) if ctcss_text != "---" else 0.0
        self._channel.tone_squelch = self._tone_squelch.isChecked()
        self._channel.agc = self._agc.isChecked()
        self._channel.noise_blanker = self._nb.isChecked()
        self._channel.trunk_system = self._trunk_system.text()
        self._channel.color_code = self._color_code.value()
        self._channel.nac = self._nac.value()
        return self._channel
