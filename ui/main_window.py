import sys, threading, time, numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QSlider, QCheckBox, QStatusBar,
    QSplitter, QFrame, QMessageBox, QFileDialog, QApplication,
    QToolBar, QDial, QTextEdit, QInputDialog, QMenu, QMenuBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QFont, QIcon

from config.settings import Settings, BAND_PLANS, CZ_REPEATERS, SIMPAX
from sdr.device_manager import DeviceManager
from demodulator.demodulator import DemodulatorFactory
from decoder.digital_voice import DecoderFactory, CTCSSDecoder, DTMFDecoder
from trunking.trunk_manager import TrunkManager, TrunkSystem, TrunkChannel
from scanner.scanner import ScannerEngine, Channel
from audio.output import AudioEngine, AudioRecorder
from detector.usb_detector import USBDetector, SignalDetector
from ui.waterfall_widget import WaterfallWidget, SpectrumWidget, SMeterWidget
from ui.channel_table import ChannelTableWidget
from ui.scanner_panel import ScannerPanel
from ui.trunk_panel import TrunkPanel
from ui.frequency_editor import FrequencyEditor


class SignalBridge(QObject):
    psd_ready = pyqtSignal(np.ndarray)
    audio_ready = pyqtSignal(np.ndarray)
    channel_changed = pyqtSignal(object)
    signal_detected = pyqtSignal(object, float)
    decoder_metadata = pyqtSignal(dict)
    usb_event = pyqtSignal(str, dict)
    trunk_event = pyqtSignal(str, dict)
    device_list = pyqtSignal(list)
    status_message = pyqtSignal(str)
    s_meter_update = pyqtSignal(float)
    ctcss_detected = pyqtSignal(float)
    dtmf_detected = pyqtSignal(str)
    frequency_changed = pyqtSignal(float)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.bridge = SignalBridge()
        self._init_components()
        self._running = False
        self._current_freq: float = self.settings.last_freq or 145.500e6
        self._current_mod: str = self.settings.last_modulation or "NFM"
        self._current_channel: Channel = None
        self._init_ui()
        self._connect_signals()
        self._sdr_thread_running = False
        self._ctcss_decoder = CTCSSDecoder()
        self._dtmf_decoder = DTMFDecoder()
        self._demod = None
        self._squelched_count = 0
        self._restore_state()

    def _init_components(self):
        self.device_mgr = DeviceManager()
        self.audio_engine = AudioEngine(sample_rate=48000)
        self.recorder = AudioRecorder()
        self.scanner = ScannerEngine()
        self.trunk_mgr = TrunkManager()
        self.usb_detector = USBDetector()
        self.signal_detector = SignalDetector()
        self._decoder = None

    def _init_ui(self):
        self.setWindowTitle("SDRTrunk - Profesionální SDR rádio pro radioamatéry")
        self.setMinimumSize(1280, 860)

        self._setup_menus()
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(4, 2, 4, 2)

        self._build_receiver_bar(main_layout)
        self._build_vfo_controls(main_layout)
        self._build_audio_bar(main_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        top_split = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.spectrum = SpectrumWidget()
        self.spectrum.setMinimumHeight(130)
        self.waterfall = WaterfallWidget()
        self.waterfall.setMinimumHeight(150)

        band_bands = []
        for key, bp in BAND_PLANS.items():
            if bp['lo'] < self._current_freq < bp['hi']:
                band_bands.append((key, bp['lo'], bp['hi'], (60, 60, 100)))
        self._update_band_display()

        left_layout.addWidget(self.spectrum, 2)
        left_layout.addWidget(self.waterfall, 3)
        top_split.addWidget(left_widget)

        self._tabs = QTabWidget()
        self.channel_table = ChannelTableWidget()
        self.scanner_panel = ScannerPanel()
        self.trunk_panel = TrunkPanel()
        self._tabs.addTab(self.channel_table, "📡 Kanály")
        self._tabs.addTab(self.scanner_panel, "🔍 Skener")
        self._tabs.addTab(self.trunk_panel, "📞 Trunking")

        self._build_info_tab()
        top_split.addWidget(self._tabs)
        top_split.setSizes([650, 550])

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        self._log.setFont(QFont("Courier", 9))
        self._log.setStyleSheet("QTextEdit { background-color: #0a0a12; color: #00cc88; }")

        splitter.addWidget(top_split)
        splitter.addWidget(self._log)
        splitter.setSizes([550, 80])
        main_layout.addWidget(splitter, 1)

        self._build_status_bar()

    def _setup_menus(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("Soubor")
        file_menu.addAction("Import CSV", lambda: self.channel_table._import_csv())
        file_menu.addAction("Export CSV", lambda: self.channel_table._export_csv())
        file_menu.addSeparator()
        file_menu.addAction("Konec", self.close)
        rx_menu = mb.addMenu("Přijímač")
        rx_menu.addAction("Ztlumit", lambda: self.audio_engine.set_muted(True))
        rx_menu.addAction("Odmlčet", lambda: self.audio_engine.set_muted(False))
        rx_menu.addSeparator()
        rx_menu.addAction("Nahrávat", lambda: self._toggle_record(True))
        rx_menu.addAction("Zastavit nahrávání", lambda: self._toggle_record(False))
        bands_menu = mb.addMenu("Pásma")
        for key in BAND_PLANS:
            bands_menu.addAction(f"{key} ({BAND_PLANS[key]['name']})",
                                 lambda k=key: self._jump_to_band(k))
        tools_menu = mb.addMenu("Nástroje")
        tools_menu.addAction("DMR dekodér", lambda: self._set_decoder("DMR"))
        tools_menu.addAction("P25 dekodér", lambda: self._set_decoder("P25"))
        tools_menu.addAction("APRS dekodér", lambda: self._set_decoder("APRS"))
        tools_menu.addAction("Vypnout dekodér", lambda: self._set_decoder(""))
        repeaters_menu = mb.addMenu("Retranslátory")
        for r in CZ_REPEATERS:
            repeaters_menu.addAction(f"{r['name']} ({r['freq']/1e6:.3f} MHz - {r['city']})",
                                     lambda r=r: self._jump_to_repeater(r))
        simpx_menu = mb.addMenu("Simplex")
        for s in SIMPAX:
            simpx_menu.addAction(f"{s['name']} ({s['freq']/1e6:.3f} MHz)",
                                  lambda s=s: self._set_frequency(s['freq']))

    def _build_receiver_bar(self, parent):
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._lbl_device = QLabel("SDR:")
        self._cmb_device = QComboBox()
        self._cmb_device.setMinimumWidth(160)
        self._btn_refresh = QPushButton("🔍")
        self._btn_refresh.setToolTip("Vyhledat SDR zařízení")
        self._btn_refresh.clicked.connect(self._enumerate_devices)
        self._btn_start = QPushButton("▶ START")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #1a5a1a; color: #00ff88; font-weight: bold; "
            "padding: 4px 16px; border: 1px solid #2a8a2a; border-radius: 4px; }"
            "QPushButton:hover { background: #2a7a2a; }"
        )
        self._btn_start.clicked.connect(self._toggle_stream)
        bar.addWidget(self._lbl_device)
        bar.addWidget(self._cmb_device)
        bar.addWidget(self._btn_refresh)
        bar.addWidget(self._btn_start)
        bar.addWidget(QLabel("  S-meter:"))
        self._s_meter = SMeterWidget()
        bar.addWidget(self._s_meter)
        bar.addStretch()
        self._lbl_mode = QLabel("NFM")
        self._lbl_mode.setStyleSheet("font-size: 14px; font-weight: bold; color: #00ff88; padding: 0 8px;")
        self._lbl_band_name = QLabel("2m")
        self._lbl_band_name.setStyleSheet("font-size: 12px; color: #888; padding: 0 4px;")
        bar.addWidget(self._lbl_band_name)
        bar.addWidget(self._lbl_mode)
        parent.addLayout(bar)

    def _build_vfo_controls(self, parent):
        vfo = QHBoxLayout()
        self._lbl_freq = QLabel(f"{self._current_freq / 1e6:.5f}")
        self._lbl_freq.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #00ff88; "
            "font-family: 'Courier New', monospace; padding: 2px 10px; "
            "background: #0a0a14; border: 1px solid #2a3a2a; border-radius: 4px;"
        )
        self._lbl_freq.setMinimumWidth(240)
        vfo.addWidget(self._lbl_freq)
        band_combo = QComboBox()
        band_combo.setMinimumWidth(120)
        for key in BAND_PLANS:
            band_combo.addItem(f"{key} - {BAND_PLANS[key]['name']}")
        band_combo.currentTextChanged.connect(lambda t: self._jump_to_band(t.split(" ")[0]))
        vfo.addWidget(QLabel("Pásmo:"))
        vfo.addWidget(band_combo)
        vfo.addWidget(QLabel("Mod:"))
        self._cmb_mod = QComboBox()
        self._cmb_mod.addItems(["NFM", "FM", "AM", "WFM", "USB", "LSB"])
        self._cmb_mod.setCurrentText(self._current_mod)
        self._cmb_mod.currentTextChanged.connect(self._on_modulation_change)
        vfo.addWidget(self._cmb_mod)
        vfo.addWidget(QLabel("Krok:"))
        self._cmb_step = QComboBox()
        self._cmb_step.addItems(["5 kHz", "8.33 kHz", "10 kHz", "12.5 kHz", "25 kHz", "50 kHz", "100 kHz"])
        self._cmb_step.setCurrentText("12.5 kHz")
        vfo.addWidget(self._cmb_step)
        self._btn_up = QPushButton("+")
        self._btn_up.setFixedWidth(36)
        self._btn_up.clicked.connect(lambda: self._step_freq(1))
        self._btn_down = QPushButton("-")
        self._btn_down.setFixedWidth(36)
        self._btn_down.clicked.connect(lambda: self._step_freq(-1))
        vfo.addWidget(self._btn_down)
        vfo.addWidget(self._btn_up)
        vfo.addStretch()
        self._lbl_ctcss = QLabel("")
        self._lbl_ctcss.setStyleSheet("color: #8888ff; font-size: 11px;")
        self._lbl_dtmf = QLabel("")
        self._lbl_dtmf.setStyleSheet("color: #ffaa00; font-size: 11px;")
        self._lbl_decoder = QLabel("Dekodér: ---")
        self._lbl_decoder.setStyleSheet("color: #88ff88; font-size: 11px;")
        self._lbl_talkgroup = QLabel("")
        self._lbl_talkgroup.setStyleSheet("color: #ff8888; font-size: 11px;")
        vfo.addWidget(self._lbl_ctcss)
        vfo.addWidget(self._lbl_dtmf)
        vfo.addWidget(self._lbl_decoder)
        vfo.addWidget(self._lbl_talkgroup)
        parent.addLayout(vfo)

    def _build_audio_bar(self, parent):
        audio = QHBoxLayout()
        audio.addWidget(QLabel("Hlasitost:"))
        self._sld_vol = QSlider(Qt.Orientation.Horizontal)
        self._sld_vol.setRange(0, 100)
        self._sld_vol.setValue(int(self.settings.audio.volume * 100))
        self._sld_vol.setFixedWidth(120)
        self._sld_vol.valueChanged.connect(lambda v: self.audio_engine.set_volume(v / 100))
        audio.addWidget(self._sld_vol)
        self._lbl_vol = QLabel(f"{int(self.settings.audio.volume * 100)}%")
        audio.addWidget(self._lbl_vol)
        self._btn_mute = QPushButton("Ztlumit")
        self._btn_mute.setCheckable(True)
        self._btn_mute.toggled.connect(self.audio_engine.set_muted)
        audio.addWidget(self._btn_mute)
        audio.addWidget(QLabel("  Squelch:"))
        self._sld_squelch = QSlider(Qt.Orientation.Horizontal)
        self._sld_squelch.setRange(0, 100)
        self._sld_squelch.setValue(30)
        self._sld_squelch.setFixedWidth(100)
        self._sld_squelch.valueChanged.connect(self._on_squelch_change)
        audio.addWidget(self._sld_squelch)
        self._lbl_squelch = QLabel("30%")
        audio.addWidget(self._lbl_squelch)
        self._chk_agc = QCheckBox("AGC")
        self._chk_agc.setChecked(True)
        audio.addWidget(self._chk_agc)
        self._chk_nb = QCheckBox("NB")
        self._chk_nb.setToolTip("Noise blanker")
        audio.addWidget(self._chk_nb)
        self._chk_record = QCheckBox("Nahrávat")
        self._chk_record.toggled.connect(self._toggle_record)
        audio.addStretch()
        self._btn_scan_start = QPushButton("🔍 Scan")
        self._btn_scan_start.clicked.connect(self._start_scanner)
        audio.addWidget(self._btn_scan_start)
        self._btn_add_ch = QPushButton("+ Kanál")
        self._btn_add_ch.clicked.connect(self._add_channel_dialog)
        audio.addWidget(self._btn_add_ch)
        parent.addLayout(audio)

    def _build_info_tab(self):
        info = QWidget()
        il = QVBoxLayout(info)
        self._info_text = QTextEdit()
        self._info_text.setReadOnly(True)
        self._info_text.setStyleSheet("QTextEdit { background: #0a0a14; color: #ccc; font-family: Courier; }")
        il.addWidget(QLabel("Informace o signálu:"))
        il.addWidget(self._info_text)
        self._tabs.addTab(info, "ℹ Info")

    def _build_status_bar(self):
        self.sb = QStatusBar()
        self.setStatusBar(self.sb)
        self._sb_freq = QLabel("Freq: ---")
        self._sb_dev = QLabel("Dev: ---")
        self._sb_sr = QLabel("SR: ---")
        self._sb_state = QLabel("● STOP")
        self._sb_state.setStyleSheet("color: #ff4444; font-weight: bold;")
        self._sb_sig = QLabel("Sig: --- dBm")
        self.sb.addWidget(self._sb_freq)
        self.sb.addWidget(self._sb_dev)
        self.sb.addWidget(self._sb_sr)
        self.sb.addPermanentWidget(self._sb_sig)
        self.sb.addPermanentWidget(self._sb_state)

    def _connect_signals(self):
        self.bridge.psd_ready.connect(self.spectrum.update_psd)
        self.bridge.psd_ready.connect(self.waterfall.push_fft)
        self.bridge.audio_ready.connect(self.audio_engine.push_audio)
        self.bridge.audio_ready.connect(self.recorder.push_audio)
        self.bridge.channel_changed.connect(self._on_channel_change)
        self.bridge.signal_detected.connect(self._on_signal_detected)
        self.bridge.decoder_metadata.connect(self._on_decoder_metadata)
        self.bridge.usb_event.connect(self._on_usb_event)
        self.bridge.trunk_event.connect(self._on_trunk_event)
        self.bridge.device_list.connect(self._on_device_list)
        self.bridge.status_message.connect(self.sb.showMessage)
        self.bridge.s_meter_update.connect(self._s_meter.set_dbm)
        self.bridge.ctcss_detected.connect(self._on_ctcss)
        self.bridge.dtmf_detected.connect(self._on_dtmf)
        self.bridge.frequency_changed.connect(self._on_freq_changed)
        self.scanner_panel.start_requested.connect(self._start_scanner)
        self.scanner_panel.stop_requested.connect(self._stop_scanner)
        self.scanner_panel.hold_requested.connect(self.scanner.hold)
        self.scanner_panel.resume_requested.connect(self.scanner.resume)
        self.trunk_panel.system_added.connect(self.trunk_mgr.add_system)
        self.trunk_panel.system_removed.connect(self.trunk_mgr.remove_system)
        self.trunk_mgr.add_listener(self._trunk_notify)
        self.channel_table.channel_double_clicked.connect(self._on_channel_double_click)

    def _enumerate_devices(self):
        self.bridge.status_message.emit("Vyhledávám SDR zařízení...")
        results = self.device_mgr.enumerate()
        self._cmb_device.clear()
        if results:
            for idx, name in results:
                self._cmb_device.addItem(name, idx)
            self.bridge.device_list.emit([n for _, n in results])
            self.bridge.status_message.emit(f"Nalezeno {len(results)} zařízení")
        else:
            self._cmb_device.addItem("Žádné SDR zařízení", -1)
            self.bridge.status_message.emit("Nenalezeno SDR - pouze demo režim")

    def _toggle_stream(self):
        if self._running:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self):
        idx = self._cmb_device.currentData()
        dev = None
        if idx is not None and idx >= 0:
            dev = self.device_mgr.select_device(idx)
            opened = False
            if dev:
                try:
                    opened = dev.open()
                except Exception as e:
                    opened = False
                    self._log.append(f"[Chyba] Při otevírání zařízení vyjímka: {e}")
            if not opened:
                self._log.append("[Chyba] Zařízení nelze otevřít, přepínám do demo režimu (generování šumu).")
                QMessageBox.warning(self, "Chyba", "Nelze otevřít SDR zařízení. Spouštím demo režim.")
                try:
                    self.device_mgr._active = None
                except Exception:
                    pass
            else:
                dev.set_freq_correction(self.settings.sdr.ppm_error)
                if hasattr(dev, 'set_bias_t'):
                    dev.set_bias_t(self.settings.sdr.bias_t)
                if hasattr(dev, 'set_direct_sampling'):
                    dev.set_direct_sampling(self.settings.sdr.direct_sampling)
        if not self.audio_engine.is_open:
            self.audio_engine.open()
        if self.settings.audio.notch_freq > 0:
            self.audio_engine.set_notch(self.settings.audio.notch_freq)

        self._create_demodulator()

        self._running = True
        self._btn_start.setText("■ STOP")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #5a1a1a; color: #ff4444; font-weight: bold; "
            "padding: 4px 16px; border: 1px solid #8a2a2a; border-radius: 4px; }"
        )
        self._sb_state.setText("● STREAM")
        self._sb_state.setStyleSheet("color: #00ff88; font-weight: bold;")
        dev_a = self.device_mgr.active
        if dev_a:
            self._sb_dev.setText(f"Dev: {dev_a.get_name()}")
            self._sb_sr.setText(f"SR: {dev_a.get_sample_rate()/1e6:.1f} Msps")
            dev_a.set_center_freq(self._current_freq)
        self._sdr_thread_running = True
        if self.device_mgr.active and self.device_mgr.active.is_open:
            self._log.append(f"[Info] Používám zařízení: {self.device_mgr.active.get_name()}")
        else:
            self._log.append("[Info] Demo režim: generuji šum pro waterfall a spektrum.")
        threading.Thread(target=self._sdr_loop, daemon=True).start()
        self.usb_detector.start()
        self.bridge.status_message.emit("SDR stream spuštěn")

    def _create_demodulator(self):
        dev = self.device_mgr.active
        sr = dev.get_sample_rate() if dev else 2.4e6
        self._demod = DemodulatorFactory.create(self._current_mod)
        self._demod.set_sample_rate(sr)
        self._demod.set_audio_rate(48000)
        self._demod.set_squelch(self._sld_squelch.value() / 100)
        self._demod.set_agc(self._chk_agc.isChecked())
        self._demod.set_noise_blanker(self._chk_nb.isChecked())
        self._squelched_count = 0

    def _on_squelch_change(self, value: int):
        self._lbl_squelch.setText(f"{value}%")
        if self._demod:
            self._demod.set_squelch(value / 100)

    def _on_modulation_change(self, mod: str):
        self._current_mod = mod
        self._lbl_mode.setText(mod)
        self.settings.last_modulation = mod
        if self._running:
            self._create_demodulator()

    def _stop_stream(self):
        self._sdr_thread_running = False
        self._running = False
        self.scanner.stop()
        if self.device_mgr.active:
            self.device_mgr.active.stop_stream()
            self.device_mgr.active.close()
        self.usb_detector.stop()
        self._btn_start.setText("▶ START")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #1a5a1a; color: #00ff88; font-weight: bold; "
            "padding: 4px 16px; border: 1px solid #2a8a2a; border-radius: 4px; }"
        )
        self._sb_state.setText("● STOP")
        self._sb_state.setStyleSheet("color: #ff4444; font-weight: bold;")
        self.bridge.status_message.emit("Stream zastaven")

    def _step_freq(self, direction: int):
        step_text = self._cmb_step.currentText()
        step_hz = float(step_text.split()[0]) * 1000
        self._current_freq += direction * step_hz
        self._set_frequency(self._current_freq)

    def _set_frequency(self, freq_hz: float):
        self._current_freq = freq_hz
        self._lbl_freq.setText(f"{freq_hz / 1e6:.5f}")
        self._sb_freq.setText(f"Freq: {freq_hz / 1e6:.5f} MHz")
        dev = self.device_mgr.active
        if dev and dev.is_open:
            dev.set_center_freq(freq_hz)
        self.spectrum.set_freq_range(freq_hz, dev.get_sample_rate() if dev else 2.4e6)
        self.waterfall.set_freq_range(freq_hz, dev.get_sample_rate() if dev else 2.4e6)
        self._update_band_display()
        self.bridge.status_message.emit(f"Ladím na {freq_hz/1e6:.5f} MHz")

    def _update_band_display(self):
        for key, bp in BAND_PLANS.items():
            if bp['lo'] <= self._current_freq <= bp['hi']:
                self._lbl_band_name.setText(key)
                band_bands = [(key, bp['lo'], bp['hi'], (60, 60, 100))]
                self.spectrum.set_band_data(band_bands)
                self.waterfall.set_band_data(band_bands)
                return
        self._lbl_band_name.setText("---")

    def _jump_to_band(self, key: str):
        bp = BAND_PLANS.get(key)
        if bp:
            mid = (bp['lo'] + bp['hi']) / 2
            self._set_frequency(mid)
            if bp['mod']:
                self._cmb_mod.setCurrentText(bp['mod'])

    def _jump_to_repeater(self, r: dict):
        self._set_frequency(r['freq'])
        if r.get('ctcss', 0) > 0:
            self._log.append(f"[RX] CTCSS: {r['ctcss']} Hz")

    def _on_channel_double_click(self, channel: Channel):
        self._set_frequency(channel.frequency)
        self._cmb_mod.setCurrentText(channel.modulation)
        self._current_channel = channel

    def _on_freq_changed(self, freq_hz: float):
        self._set_frequency(freq_hz)

    def _add_channel_dialog(self):
        ch = Channel(frequency=self._current_freq, modulation=self._current_mod,
                     label=f"CH {len(self.channel_table.channels) + 1}")
        banks = list(self.channel_table.banks.keys()) or ["Default"]
        dialog = FrequencyEditor(ch, self, banks)
        if dialog.exec():
            new_ch = dialog.get_channel()
            self.channel_table.add_channel(new_ch)
            self.scanner.add_channel(new_ch)
            self._log.append(f"[Kanál] Přidán: {new_ch.frequency/1e6:.5f} MHz {new_ch.label}")

    def _set_decoder(self, protocol: str):
        if protocol:
            try:
                self._decoder = DecoderFactory.create(protocol)
                self._decoder.set_debug_callback(
                    lambda m: self.bridge.decoder_metadata.emit(m))
                self._log.append(f"[Dekodér] Aktivován: {protocol}")
            except:
                self._decoder = None
        else:
            self._decoder = None
            self._log.append("[Dekodér] Vypnut")

    def _toggle_record(self, enabled):
        if enabled:
            self.recorder.start_recording()
            self._log.append("[Nahrávání] Spuštěno")
        else:
            fname = self.recorder.stop_recording()
            if fname:
                self._log.append(f"[Nahrávání] Uloženo: {fname}")

    def _start_scanner(self):
        self.scanner.set_callbacks(
            on_channel=lambda ch: self.bridge.channel_changed.emit(ch),
            on_signal=lambda ch, db: self.bridge.signal_detected.emit(ch, db),
        )
        self.scanner.set_hold_time(self.scanner_panel._hold_time.value())
        self.scanner.set_hang_time(self.scanner_panel._hang_time.value())

        channels = self.channel_table.channels
        self.scanner.load_channels(channels)
        band_count = 0

        if self.scanner_panel._chk_search.isChecked() or not channels:
            band_list = []
            for key, bp in BAND_PLANS.items():
                if bp['lo'] > 0 and bp['hi'] > bp['lo']:
                    band_list.append({
                        'name': key,
                        'lo': bp['lo'],
                        'hi': bp['hi'],
                        'step': bp.get('step', 12.5e3),
                        'mod': bp.get('mod', 'NFM'),
                    })
            self.scanner.load_bands(band_list)
            band_count = len(band_list)
            self._log.append(f"[Skener] Nahráno {band_count} amatérských pásem pro skenování")

        self.scanner.start()
        self.scanner_panel.set_running(True)
        self._log.append(f"[Skener] Spuštěn ({len(channels)} kanálů, {band_count} pásem)")
        self.bridge.status_message.emit("Skener spuštěn")

    def _stop_scanner(self):
        self.scanner.stop()
        self.scanner_panel.set_running(False)
        self._log.append("[Skener] Zastaven")

    def _on_channel_change(self, channel: Channel):
        self._current_channel = channel
        self._set_frequency(channel.frequency)
        if channel.modulation != self._current_mod:
            self._current_mod = channel.modulation
            self._cmb_mod.setCurrentText(channel.modulation)
            if self._running:
                self._create_demodulator()
        self.scanner_panel.update_status(f"{channel.frequency/1e6:.5f} MHz {channel.label}")

    def _on_signal_detected(self, channel: Channel, power_db: float):
        self.sb.showMessage(f"Signál: {channel.frequency/1e6:.5f} MHz @ {power_db:.1f} dB", 2000)

    def _on_decoder_metadata(self, meta: dict):
        proto = meta.get("protocol", "---")
        self._lbl_decoder.setText(f"Dekodér: {proto}")
        tg_info = ""
        if "nac" in meta:
            tg_info = f"NAC: {meta['nac']:#05x}"
        elif "color_code" in meta:
            tg_info = f"CC: {meta['color_code']}"
        elif "talkgroup" in meta:
            tg_info = f"TG: {meta['talkgroup']}"
        self._lbl_talkgroup.setText(tg_info)
        if "ber" in meta:
            self._sb_sig.setText(f"Sig: {meta.get('rssi', 0)} dBm  BER: {meta['ber']}%")

    def _on_ctcss(self, freq: float):
        if freq > 0:
            self._lbl_ctcss.setText(f"CTCSS: {freq:.1f} Hz")
        else:
            self._lbl_ctcss.setText("")

    def _on_dtmf(self, digit: str):
        self._lbl_dtmf.setText(f"DTMF: {digit}")
        QTimer.singleShot(1500, lambda: self._lbl_dtmf.setText(""))

    def _on_usb_event(self, event: str, info: dict):
        self._log.append(f"[USB] {event}: {info.get('name', '')}")
        if event == "attached":
            self._enumerate_devices()

    def _on_trunk_event(self, event: str, data: dict):
        self._log.append(f"[Trunk] {event}: {data.get('system', '')} @ {data.get('freq', 0)/1e6:.3f} MHz")
        if event == "voice_grant":
            self.trunk_panel.update_call_info(data.get("system", ""), data.get("freq", 0))

    def _trunk_notify(self, event: str, data: dict):
        self.bridge.trunk_event.emit(event, data)

    def _on_device_list(self, names: list):
        self._log.append(f"[SDR] Nalezena zařízení: {', '.join(names)}")

    def _sdr_loop(self):
        dev = self.device_mgr.active
        sr = dev.get_sample_rate() if dev else 2.4e6
        signal = SignalDetector()

        if not self._demod:
            self._create_demodulator()

        def iq_callback(samples):
            if not self._sdr_thread_running:
                return
            audio = self._demod.process(samples)
            if audio is not None:
                self._squelched_count = 0
                self.bridge.audio_ready.emit(audio)
                if self.scanner and self.scanner.current_channel:
                    self.scanner.signal_active(signal.analyze(samples)["dbm"])
                ctcss = self._ctcss_decoder.detect_tone(audio)
                if ctcss[0] > 0:
                    self.bridge.ctcss_detected.emit(ctcss[0])
                dtmf = self._dtmf_decoder.decode(audio)
                if dtmf:
                    self.bridge.dtmf_detected.emit(dtmf)
            else:
                self._squelched_count += 1
                if self._squelched_count > 10 and self.scanner:
                    self.scanner.signal_lost()
                    self._squelched_count = 0
            psd = 20 * np.log10(np.abs(np.fft.fftshift(np.fft.fft(samples, 1024))) + 1e-15)
            self.bridge.psd_ready.emit(psd)
            sig = signal.analyze(samples)
            self.bridge.s_meter_update.emit(sig["dbm"])
            self._sb_sig.setText(f"Sig: {sig['dbm']:.0f} dBm {sig['s_meter']}")
            if self._decoder:
                self._decoder.decode(samples, sr)

        if dev and dev.is_open:
            dev.start_stream(iq_callback)
            while self._sdr_thread_running and dev.is_open:
                time.sleep(0.5)
            dev.stop_stream()
        else:
            while self._sdr_thread_running:
                noise = np.random.randn(1024) + 1j * np.random.randn(1024)
                iq_callback(noise.astype(np.complex64))
                time.sleep(0.05)

    def _restore_state(self):
        for fe in self.settings.favorites:
            ch = Channel(
                frequency=fe.get("freq_hz", 145.500e6),
                label=fe.get("label", ""),
                modulation=fe.get("modulation", "NFM"),
                squelch=fe.get("squelch", 0.5),
                bank=fe.get("bank", "Default"),
            )
            self.channel_table.add_channel(ch)
            self.scanner.add_channel(ch)
        if self.settings.last_freq:
            self._set_frequency(self.settings.last_freq)
        if self.settings.last_modulation:
            self._cmb_mod.setCurrentText(self.settings.last_modulation)

    def closeEvent(self, event):
        self._stop_stream()
        if self.audio_engine.is_open:
            self.audio_engine.close()
        self.settings.last_freq = self._current_freq
        self.settings.last_modulation = self._current_mod
        self.settings.audio.volume = self._sld_vol.value() / 100
        favs = []
        for ch in self.channel_table.channels:
            favs.append({
                "label": ch.label, "freq_hz": ch.frequency,
                "modulation": ch.modulation, "squelch": ch.squelch,
                "bank": ch.bank,
            })
        self.settings.favorites = favs
        self.settings.save()
        event.accept()
