import sys, threading, time, numpy as np
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QSlider, QCheckBox, QStatusBar, QSplitter, QTextEdit, QMenuBar,
    QGridLayout, QFrame, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QAction

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

from scipy.fft import fft, fftshift


BAND_ORDER = ["160m","80m","40m","30m","20m","17m","15m","12m","10m","6m","2m","70cm","23cm"]
MODES = ["NFM","FM","AM","USB","LSB","WFM"]

FREQ_STEPS = [
    ("1 kHz", 1e3), ("5 kHz", 5e3), ("8.33 kHz", 8.33e3),
    ("10 kHz", 10e3), ("12.5 kHz", 12.5e3), ("25 kHz", 25e3),
    ("50 kHz", 50e3), ("100 kHz", 100e3),
]


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
        self._vfo_a: float = self.settings.last_freq or 145.500e6
        self._vfo_b: float = 145.500e6
        self._vfo_active: str = "A"
        self._current_freq: float = self._vfo_a
        self._current_mod: str = self.settings.last_modulation or "NFM"
        self._current_channel: Optional[Channel] = None
        self._init_ui()
        self._connect_signals()
        self._sdr_thread_running = False
        self._ctcss_decoder = CTCSSDecoder()
        self._dtmf_decoder = DTMFDecoder()
        self._demod = None
        self._squelched_count = 0
        self._last_band = ""
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
        self.setWindowTitle("RadioAmater Station")
        self.setMinimumSize(1320, 900)
        self._setup_menus()
        central = QWidget()
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setSpacing(2)
        ml.setContentsMargins(4, 2, 4, 2)

        self._build_top_bar(ml)
        self._build_vfo_section(ml)
        self._build_band_mod_bar(ml)
        self._build_controls_bar(ml)

        splitter = QSplitter(Qt.Orientation.Vertical)
        top_split = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(1)

        self.spectrum = SpectrumWidget()
        self.spectrum.setMinimumHeight(120)
        self.waterfall = WaterfallWidget()
        self.waterfall.setMinimumHeight(150)

        # S-meter inline next to spectrum
        smeter_row = QHBoxLayout()
        smeter_row.setSpacing(2)
        self._s_meter = SMeterWidget()
        smeter_row.addWidget(self._s_meter, 1)
        left_layout.addLayout(smeter_row)

        left_layout.addWidget(self.spectrum, 2)
        left_layout.addWidget(self.waterfall, 3)
        top_split.addWidget(left_widget)

        self._tabs = QTabWidget()
        self.channel_table = ChannelTableWidget()
        self.scanner_panel = ScannerPanel()
        self.trunk_panel = TrunkPanel()
        self._tabs.addTab(self.channel_table, "Kan\u00e1ly")
        self._tabs.addTab(self.scanner_panel, "Skener")
        self._tabs.addTab(self.trunk_panel, "Trunking")
        self._build_info_tab()
        top_split.addWidget(self._tabs)
        top_split.setSizes([650, 550])

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(80)
        self._log.setFont(QFont("Courier", 9))
        self._log.setStyleSheet(
            "QTextEdit { background-color: #0a0a12; color: #00cc88; border: 1px solid #1a3a2a; }"
        )

        splitter.addWidget(top_split)
        splitter.addWidget(self._log)
        splitter.setSizes([550, 60])
        ml.addWidget(splitter, 1)

        self._build_status_bar()

    def _setup_menus(self):
        mb = self.menuBar()
        fm = mb.addMenu("Soubor")
        fm.addAction("Import CSV", lambda: self.channel_table._import_csv())
        fm.addAction("Export CSV", lambda: self.channel_table._export_csv())
        fm.addSeparator()
        fm.addAction("Konec", self.close)
        rm = mb.addMenu("Prijimac")
        rm.addAction("Ztlumit", lambda: self.audio_engine.set_muted(True))
        rm.addAction("Odmlcet", lambda: self.audio_engine.set_muted(False))
        rm.addSeparator()
        rm.addAction("Nahravat", lambda: self._toggle_record(True))
        rm.addAction("Zastavit nahravani", lambda: self._toggle_record(False))
        bm = mb.addMenu("Pasma")
        for key in BAND_ORDER:
            if key in BAND_PLANS:
                b = BAND_PLANS[key]
                bm.addAction(f"{key} ({b['name']})", lambda k=key: self._jump_to_band(k))
        tm = mb.addMenu("Nastroje")
        tm.addAction("DMR dekoder", lambda: self._set_decoder("DMR"))
        tm.addAction("P25 dekoder", lambda: self._set_decoder("P25"))
        tm.addAction("APRS dekoder", lambda: self._set_decoder("APRS"))
        tm.addAction("Vypnout dekoder", lambda: self._set_decoder(""))
        rpt = mb.addMenu("Retranslatory")
        for r in CZ_REPEATERS:
            rpt.addAction(f"{r['name']} ({r['freq']/1e6:.3f} - {r['city']})",
                          lambda r=r: self._jump_to_repeater(r))
        spx = mb.addMenu("Simplex")
        for s in SIMPAX:
            spx.addAction(f"{s['name']} ({s['freq']/1e6:.3f})",
                          lambda s=s: self._set_frequency(s['freq']))

    def _build_top_bar(self, parent):
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._lbl_device = QLabel("SDR:")
        self._cmb_device = QComboBox()
        self._cmb_device.setMinimumWidth(150)
        self._btn_refresh = QPushButton("Obnovit")
        self._btn_refresh.clicked.connect(self._enumerate_devices)
        self._btn_start = QPushButton("RX")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #1a5a1a; color: #00ff88; font-weight: bold; "
            "padding: 4px 20px; border: 1px solid #2a8a2a; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background: #2a7a2a; }"
        )
        self._btn_start.clicked.connect(self._toggle_stream)
        bar.addWidget(self._lbl_device)
        bar.addWidget(self._cmb_device)
        bar.addWidget(self._btn_refresh)
        bar.addWidget(self._btn_start)

        bar.addStretch()
        rx_led = QLabel()
        rx_led.setFixedSize(12, 12)
        rx_led.setStyleSheet(
            "background: #00ff88; border-radius: 6px;"
        )
        bar.addWidget(rx_led)
        bar.addWidget(QLabel("RX"))
        self._lbl_rx_freq = QLabel("---")
        self._lbl_rx_freq.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 12px;")
        bar.addWidget(self._lbl_rx_freq)
        bar.addWidget(QLabel("  MODE:"))
        self._lbl_rx_mode = QLabel("NFM")
        self._lbl_rx_mode.setStyleSheet(
            "color: #88ccff; font-weight: bold; font-size: 12px; "
            "background: #0a0a20; padding: 1px 8px; border: 1px solid #2a4a6a; border-radius: 3px;"
        )
        bar.addWidget(self._lbl_rx_mode)
        parent.addLayout(bar)

    def _build_vfo_section(self, parent):
        vfo_frame = QFrame()
        vfo_frame.setStyleSheet(
            "QFrame { background: #0a0a14; border: 1px solid #1a2a3a; border-radius: 4px; }"
        )
        vfo = QHBoxLayout(vfo_frame)
        vfo.setSpacing(3)
        vfo.setContentsMargins(6, 3, 6, 3)

        # VFO A/B buttons
        self._btn_vfo_a = QPushButton("VFO A")
        self._btn_vfo_a.setCheckable(True)
        self._btn_vfo_a.setChecked(True)
        self._btn_vfo_a.setStyleSheet(self._vfo_btn_style(True))
        self._btn_vfo_a.clicked.connect(lambda: self._select_vfo("A"))
        self._btn_vfo_b = QPushButton("VFO B")
        self._btn_vfo_b.setCheckable(True)
        self._btn_vfo_b.setStyleSheet(self._vfo_btn_style(False))
        self._btn_vfo_b.clicked.connect(lambda: self._select_vfo("B"))
        self._btn_swap = QPushButton("\u21c4")
        self._btn_swap.setToolTip("Prohodit VFO A a B")
        self._btn_swap.setFixedWidth(32)
        self._btn_swap.clicked.connect(self._swap_vfo)
        vfo.addWidget(self._btn_vfo_a)
        vfo.addWidget(self._btn_vfo_b)
        vfo.addWidget(self._btn_swap)

        # Big frequency display
        self._lbl_freq = QLabel(f"{self._current_freq / 1e6:.5f}")
        self._lbl_freq.setStyleSheet(
            "font-size: 40px; font-weight: bold; color: #00ff88; "
            "font-family: 'Courier New', monospace; padding: 2px 14px; "
            "background: #050510; border: 2px solid #1a3a2a; border-radius: 6px;"
            "min-width: 280px;"
        )
        vfo.addWidget(self._lbl_freq)
        vfo.addWidget(QLabel("MHz"))

        # Step selector
        vfo.addWidget(QLabel("  Krok:"))
        self._cmb_step = QComboBox()
        for label, _ in FREQ_STEPS:
            self._cmb_step.addItem(label)
        self._cmb_step.setCurrentText("12.5 kHz")
        vfo.addWidget(self._cmb_step)

        # Tuning controls
        self._btn_freq_down = QPushButton("\u25c0")
        self._btn_freq_down.setFixedWidth(30)
        self._btn_freq_down.clicked.connect(lambda: self._step_freq(-1))
        self._btn_freq_up = QPushButton("\u25b6")
        self._btn_freq_up.setFixedWidth(30)
        self._btn_freq_up.clicked.connect(lambda: self._step_freq(1))
        vfo.addWidget(self._btn_freq_down)
        vfo.addWidget(self._btn_freq_up)

        # Quick tune buttons (MHz jump)
        vfo.addStretch()
        self._btn_m1 = QPushButton("M1")
        self._btn_m1.setFixedWidth(32)
        self._btn_m1.setToolTip("Ulozit/M1")
        self._btn_m1.clicked.connect(lambda: self._recall_mem(1))
        self._btn_m2 = QPushButton("M2")
        self._btn_m2.setFixedWidth(32)
        self._btn_m2.clicked.connect(lambda: self._recall_mem(2))
        self._btn_m3 = QPushButton("M3")
        self._btn_m3.setFixedWidth(32)
        self._btn_m3.clicked.connect(lambda: self._recall_mem(3))
        self._mem_slots = {1: 145.500e6, 2: 439.000e6, 3: 145.600e6}
        vfo.addWidget(self._btn_m1)
        vfo.addWidget(self._btn_m2)
        vfo.addWidget(self._btn_m3)
        parent.addWidget(vfo_frame)

    def _vfo_btn_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton { background: #1a3a5a; color: #88ddff; font-weight: bold; "
                "padding: 2px 10px; border: 2px solid #3a8acc; border-radius: 3px; }"
            )
        return (
            "QPushButton { background: #12122a; color: #888; "
            "padding: 2px 10px; border: 1px solid #2a2a4e; border-radius: 3px; }"
        )

    def _build_band_mod_bar(self, parent):
        bar = QHBoxLayout()
        bar.setSpacing(2)

        # Band buttons
        for key in BAND_ORDER:
            if key not in BAND_PLANS:
                continue
            bp = BAND_PLANS[key]
            btn = QPushButton(key)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton { background: #12122a; color: #88aacc; border: 1px solid #2a3a5a; "
                "border-radius: 3px; padding: 0 8px; font-size: 10px; }"
                "QPushButton:hover { background: #1a2a4a; border-color: #4a8acc; }"
            )
            btn.clicked.connect(lambda checked, k=key: self._jump_to_band(k))
            bar.addWidget(btn)

        bar.addStretch()

        # Mode buttons
        for mode in MODES:
            btn = QPushButton(mode)
            btn.setFixedHeight(26)
            btn.setCheckable(True)
            btn.setChecked(mode == self._current_mod)
            btn.setStyleSheet(
                "QPushButton { background: #12122a; color: #88aacc; border: 1px solid #2a3a5a; "
                "border-radius: 3px; padding: 0 8px; font-size: 10px; }"
                "QPushButton:hover { background: #1a2a4a; }"
                "QPushButton:checked { background: #1a4a8a; color: #ffffff; border-color: #4a8acc; }"
            )
            btn.clicked.connect(lambda checked, m=mode: self._on_mode_click(m))
            bar.addWidget(btn)
        parent.addLayout(bar)

    def _build_controls_bar(self, parent):
        bar = QHBoxLayout()
        bar.setSpacing(8)

        # Squelch
        bar.addWidget(QLabel("SQL:"))
        self._sld_squelch = QSlider(Qt.Orientation.Horizontal)
        self._sld_squelch.setRange(0, 100)
        self._sld_squelch.setValue(50)
        self._sld_squelch.setFixedWidth(80)
        self._sld_squelch.valueChanged.connect(self._on_squelch_change)
        bar.addWidget(self._sld_squelch)
        self._lbl_squelch = QLabel("50")
        self._lbl_squelch.setFixedWidth(24)
        bar.addWidget(self._lbl_squelch)

        # Volume
        bar.addWidget(QLabel("VOL:"))
        self._sld_vol = QSlider(Qt.Orientation.Horizontal)
        self._sld_vol.setRange(0, 100)
        self._sld_vol.setValue(int(self.settings.audio.volume * 100))
        self._sld_vol.setFixedWidth(80)
        self._sld_vol.valueChanged.connect(lambda v: self.audio_engine.set_volume(v / 100))
        bar.addWidget(self._sld_vol)
        self._lbl_vol = QLabel(f"{int(self.settings.audio.volume * 100)}%")
        self._lbl_vol.setFixedWidth(28)
        bar.addWidget(self._lbl_vol)

        self._btn_mute = QPushButton("Mute")
        self._btn_mute.setCheckable(True)
        self._btn_mute.toggled.connect(self.audio_engine.set_muted)
        bar.addWidget(self._btn_mute)

        # AGC / NB / Record
        self._chk_agc = QCheckBox("AGC")
        self._chk_agc.setChecked(True)
        bar.addWidget(self._chk_agc)
        self._chk_nb = QCheckBox("NB")
        self._chk_nb.setToolTip("Noise blanker")
        bar.addWidget(self._chk_nb)
        self._chk_record = QCheckBox("REC")
        self._chk_record.toggled.connect(self._toggle_record)
        bar.addWidget(self._chk_record)

        # Gain controls (Airspy)
        bar.addWidget(QLabel(" LNA:"))
        self._sld_lna = QSlider(Qt.Orientation.Horizontal)
        self._sld_lna.setRange(0, 15)
        self._sld_lna.setValue(8)
        self._sld_lna.setFixedWidth(60)
        self._sld_lna.valueChanged.connect(self._on_gain_change)
        bar.addWidget(self._sld_lna)
        bar.addWidget(QLabel("Mix:"))
        self._sld_mixer = QSlider(Qt.Orientation.Horizontal)
        self._sld_mixer.setRange(0, 15)
        self._sld_mixer.setValue(8)
        self._sld_mixer.setFixedWidth(60)
        self._sld_mixer.valueChanged.connect(self._on_gain_change)
        bar.addWidget(self._sld_mixer)
        bar.addWidget(QLabel("VGA:"))
        self._sld_vga = QSlider(Qt.Orientation.Horizontal)
        self._sld_vga.setRange(0, 15)
        self._sld_vga.setValue(8)
        self._sld_vga.setFixedWidth(60)
        self._sld_vga.valueChanged.connect(self._on_gain_change)
        bar.addWidget(self._sld_vga)

        bar.addStretch()

        # Scan / Add channel buttons
        self._btn_scan_start = QPushButton("Scan")
        self._btn_scan_start.clicked.connect(self._start_scanner)
        bar.addWidget(self._btn_scan_start)
        self._btn_add_ch = QPushButton("+CH")
        self._btn_add_ch.clicked.connect(self._add_channel_dialog)
        bar.addWidget(self._btn_add_ch)
        parent.addLayout(bar)

    def _build_info_tab(self):
        info = QWidget()
        il = QVBoxLayout(info)
        self._info_text = QTextEdit()
        self._info_text.setReadOnly(True)
        self._info_text.setStyleSheet("QTextEdit { background: #0a0a14; color: #ccc; font-family: Courier; }")
        il.addWidget(QLabel("Informace o signalu:"))
        il.addWidget(self._info_text)
        self._tabs.addTab(info, "Info")

    def _build_status_bar(self):
        self.sb = QStatusBar()
        self.setStatusBar(self.sb)
        self._sb_freq = QLabel("Freq: ---")
        self._sb_dev = QLabel("Dev: ---")
        self._sb_sr = QLabel("SR: ---")
        self._sb_state = QLabel("STOP")
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
        self.bridge.status_message.emit("Vyhledavam SDR zarizeni...")
        results = self.device_mgr.enumerate()
        self._cmb_device.clear()
        if results:
            for idx, name in results:
                self._cmb_device.addItem(name, idx)
            self.bridge.device_list.emit([n for _, n in results])
            self.bridge.status_message.emit(f"Nalezeno {len(results)} zarizeni")
        else:
            self._cmb_device.addItem("Zadne SDR zarizeni", -1)
            self.bridge.status_message.emit("Nenalezeno SDR - pouze demo rezim")

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
                    self._log.append(f"[Chyba] Pri otevirani zarizeni: {e}")
            if not opened:
                self._log.append("[Chyba] Zarizeni nelze otevrit, prepinam do demo rezimu.")
                QMessageBox.warning(self, "Chyba", "Nelze otevrit SDR zarizeni. Spoustim demo rezim.")
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
        self._apply_gains()

        self._running = True
        self._btn_start.setText("RX ON")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #5a1a1a; color: #ff4444; font-weight: bold; "
            "padding: 4px 20px; border: 1px solid #8a2a2a; border-radius: 4px; font-size: 13px; }"
        )
        self._sb_state.setText("RX")
        self._sb_state.setStyleSheet("color: #00ff88; font-weight: bold;")
        dev_a = self.device_mgr.active
        if dev_a:
            self._sb_dev.setText(f"Dev: {dev_a.get_name()}")
            self._sb_sr.setText(f"SR: {dev_a.get_sample_rate()/1e6:.1f} Msps")
            dev_a.set_center_freq(self._current_freq)
        self._sdr_thread_running = True
        if self.device_mgr.active and self.device_mgr.active.is_open:
            self._log.append(f"[Info] Pouzivam: {self.device_mgr.active.get_name()}")
        else:
            self._log.append("[Info] Demo rezim.")
        threading.Thread(target=self._sdr_loop, daemon=True).start()
        self.usb_detector.start()
        self.bridge.status_message.emit("Prijimac spusten")

    def _create_demodulator(self):
        dev = self.device_mgr.active
        sr = dev.get_sample_rate() if dev else 2.4e6
        self._demod = DemodulatorFactory.create(self._current_mod)
        self._demod.set_sample_rate(sr)
        self._demod.set_audio_rate(48000)
        self._demod.set_squelch(self._sld_squelch.value() / 100)
        self._squelched_count = 0

    def _on_squelch_change(self, value: int):
        self._lbl_squelch.setText(f"{value}")
        if self._demod:
            self._demod.set_squelch(value / 100)

    def _on_mode_click(self, mode: str):
        self._current_mod = mode
        self._lbl_rx_mode.setText(mode)
        for btn in self.findChildren(QPushButton):
            if btn.text() in MODES:
                btn.setChecked(btn.text() == mode)
        self.settings.last_modulation = mode
        if self._running:
            self._create_demodulator()

    def _on_gain_change(self):
        self._apply_gains()

    def _apply_gains(self):
        dev = self.device_mgr.active
        if not dev or not dev.is_open:
            return
        try:
            dev.set_lna_gain(self._sld_lna.value())
        except AttributeError:
            pass
        try:
            dev.set_mixer_gain(self._sld_mixer.value())
        except AttributeError:
            pass
        try:
            dev.set_vga_gain(self._sld_vga.value())
        except AttributeError:
            pass

    def _select_vfo(self, vfo: str):
        if vfo == self._vfo_active:
            return
        # Save current freq
        if self._vfo_active == "A":
            self._vfo_a = self._current_freq
        else:
            self._vfo_b = self._current_freq
        self._vfo_active = vfo
        self._current_freq = self._vfo_a if vfo == "A" else self._vfo_b
        self._btn_vfo_a.setStyleSheet(self._vfo_btn_style(vfo == "A"))
        self._btn_vfo_b.setStyleSheet(self._vfo_btn_style(vfo == "B"))
        self._set_frequency(self._current_freq)

    def _swap_vfo(self):
        self._vfo_a, self._vfo_b = self._vfo_b, self._vfo_a
        if self._vfo_active == "A":
            self._current_freq = self._vfo_a
        else:
            self._current_freq = self._vfo_b
        self._set_frequency(self._current_freq)
        self._log.append(f"[VFO] Prohozeno: A={self._vfo_a/1e6:.5f} B={self._vfo_b/1e6:.5f} MHz")

    def _recall_mem(self, slot: int):
        self._set_frequency(self._mem_slots.get(slot, 145.500e6))
        # Long press would save - simple implementation: click to recall, double-click not easily supported
        # So we just recall. To save: hold shift+click
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self._mem_slots[slot] = self._current_freq
            self._log.append(f"[MEM] M{slot} ulozeno: {self._current_freq/1e6:.5f} MHz")

    def _stop_stream(self):
        self._sdr_thread_running = False
        self._running = False
        self.scanner.stop()
        if self.device_mgr.active:
            self.device_mgr.active.stop_stream()
            self.device_mgr.active.close()
        self.usb_detector.stop()
        self._btn_start.setText("RX")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #1a5a1a; color: #00ff88; font-weight: bold; "
            "padding: 4px 20px; border: 1px solid #2a8a2a; border-radius: 4px; font-size: 13px; }"
        )
        self._sb_state.setText("STOP")
        self._sb_state.setStyleSheet("color: #ff4444; font-weight: bold;")
        self.bridge.status_message.emit("Prijimac zastaven")

    def _step_freq(self, direction: int):
        step_text = self._cmb_step.currentText()
        step_hz = float(step_text.split()[0]) * 1000
        self._current_freq += direction * step_hz
        # Keep in band
        for key, bp in BAND_PLANS.items():
            if bp['lo'] <= self._current_freq <= bp['hi'] or (
                self._current_freq >= bp['lo'] - step_hz and self._current_freq <= bp['hi'] + step_hz
            ):
                self._current_freq = max(bp['lo'], min(bp['hi'], self._current_freq))
                break
        self._set_frequency(self._current_freq)

    def _set_frequency(self, freq_hz: float):
        self._current_freq = freq_hz
        self._lbl_freq.setText(f"{freq_hz / 1e6:.5f}")
        self._lbl_rx_freq.setText(f"{freq_hz / 1e6:.5f}")
        self._sb_freq.setText(f"Freq: {freq_hz / 1e6:.5f} MHz")
        dev = self.device_mgr.active
        if dev and dev.is_open:
            dev.set_center_freq(freq_hz)
        sr = dev.get_sample_rate() if dev else 2.4e6
        self.spectrum.set_freq_range(freq_hz, sr)
        self.waterfall.set_freq_range(freq_hz, sr)
        self._update_band_display()

    def _update_band_display(self):
        for key, bp in BAND_PLANS.items():
            if bp['lo'] <= self._current_freq <= bp['hi']:
                if key != self._last_band:
                    self._last_band = key
                    # Auto-select modulation for band
                    if bp.get('mod') and self._current_mod != bp['mod'] and not self._running:
                        self._on_mode_click(bp['mod'])
                return

    def _jump_to_band(self, key: str):
        bp = BAND_PLANS.get(key)
        if bp:
            mid = (bp['lo'] + bp['hi']) / 2
            self._set_frequency(mid)
            if bp['mod']:
                self._on_mode_click(bp['mod'])

    def _jump_to_repeater(self, r: dict):
        self._set_frequency(r['freq'])
        if r.get('ctcss', 0) > 0:
            self._log.append(f"[RX] CTCSS: {r['ctcss']} Hz")

    def _on_channel_double_click(self, channel: Channel):
        self._set_frequency(channel.frequency)
        self._on_mode_click(channel.modulation)
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
            self._log.append(f"[Kanal] Pridan: {new_ch.frequency/1e6:.5f} {new_ch.label}")

    def _set_decoder(self, protocol: str):
        if protocol:
            try:
                self._decoder = DecoderFactory.create(protocol)
                self._decoder.set_debug_callback(
                    lambda m: self.bridge.decoder_metadata.emit(m))
                self._log.append(f"[Dekoder] Aktivovan: {protocol}")
            except:
                self._decoder = None
        else:
            self._decoder = None
            self._log.append("[Dekoder] Vypnut")

    def _toggle_record(self, enabled):
        if enabled:
            self.recorder.start_recording(freq_hz=self._current_freq, mode=self._current_mod)
            self._log.append(f"[REC] Spusteno: {self._current_freq/1e6:.3f} MHz {self._current_mod}")
        else:
            fname = self.recorder.stop_recording()
            if fname:
                self._log.append(f"[REC] Ulozeno: {fname}")

    def _start_scanner(self):
        self.scanner.set_callbacks(
            on_channel=lambda ch: self.bridge.channel_changed.emit(ch),
            on_signal=lambda ch, db: self.bridge.signal_detected.emit(ch, db),
            on_hold=self._on_scanner_hold,
        )
        self.scanner.set_hold_time(self.scanner_panel._hold_time.value())
        self.scanner.set_hang_time(self.scanner_panel._hang_time.value())

        auto_capture = self.scanner_panel._chk_autocap.isChecked()
        self.scanner.set_auto_capture(auto_capture, "Scan Bank")

        channels = self.channel_table.channels
        self.scanner.load_channels(channels)
        band_count = 0

        if self.scanner_panel._chk_search.isChecked() or not channels:
            band_list = []
            for key, bp in BAND_PLANS.items():
                if bp['lo'] > 0 and bp['hi'] > bp['lo']:
                    band_list.append({
                        'name': key, 'lo': bp['lo'], 'hi': bp['hi'],
                        'step': bp.get('step', 12.5e3), 'mod': bp.get('mod', 'NFM'),
                    })
            self.scanner.load_bands(band_list)
            band_count = len(band_list)
            self._log.append(f"[Skener] {band_count} pasem nacteno")

        self.scanner.start()
        self.scanner_panel.set_running(True)
        self._log.append(f"[Skener] Spusten ({len(channels)} kanalu, {band_count} pasem)")
        self.bridge.status_message.emit("Skener spusten")

    def _on_scanner_hold(self, channel: Channel, power_db: float):
        freq = channel.frequency
        mod = channel.modulation
        label = f"Scan {freq/1e6:.3f}"
        # check if already in channel table
        for ch in self.channel_table.channels:
            if abs(ch.frequency - freq) < 100:
                return
        new_ch = Channel(
            frequency=freq, modulation=mod, label=label,
            bank="Scan Bank", squelch=0.4,
        )
        self.channel_table.add_channel(new_ch)
        self.scanner.add_channel(new_ch)
        self._log.append(f"[ScanBank] Pridano: {freq/1e6:.5f} MHz {mod}")

    def _stop_scanner(self):
        self.scanner.stop()
        self.scanner_panel.set_running(False)
        self._log.append("[Skener] Zastaven")

    def _on_channel_change(self, channel: Channel):
        self._current_channel = channel
        self._set_frequency(channel.frequency)
        if channel.modulation != self._current_mod:
            self._on_mode_click(channel.modulation)
        self.scanner_panel.update_status(f"{channel.frequency/1e6:.5f} {channel.label}")

    def _on_signal_detected(self, channel: Channel, power_db: float):
        self.sb.showMessage(f"Signal: {channel.frequency/1e6:.5f} MHz @ {power_db:.1f} dB", 2000)

    def _on_decoder_metadata(self, meta: dict):
        proto = meta.get("protocol", "---")
        tg_info = ""
        if "nac" in meta:
            tg_info = f"NAC: {meta['nac']:#05x}"
        elif "color_code" in meta:
            tg_info = f"CC: {meta['color_code']}"
        elif "talkgroup" in meta:
            tg_info = f"TG: {meta['talkgroup']}"
        if "ber" in meta:
            self._sb_sig.setText(f"Sig: {meta.get('rssi', 0)} dBm  BER: {meta['ber']}%")

    def _on_ctcss(self, freq: float):
        pass

    def _on_dtmf(self, digit: str):
        pass

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
        self._log.append(f"[SDR] Nalezena: {', '.join(names)}")

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
                if self.scanner.current_channel:
                    self.scanner.signal_active(signal.analyze(samples)["dbm"])
                ctcss = self._ctcss_decoder.detect_tone(audio)
                if ctcss[0] > 0:
                    self.bridge.ctcss_detected.emit(ctcss[0])
                dtmf = self._dtmf_decoder.decode(audio)
                if dtmf:
                    self.bridge.dtmf_detected.emit(dtmf)
            else:
                self._squelched_count += 1
                if self._squelched_count > 10:
                    self.scanner.signal_lost()
                    self._squelched_count = 0
            psd = 20 * np.log10(np.abs(fftshift(fft(samples, 1024))) + 1e-15)
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
            self._on_mode_click(self.settings.last_modulation)

    def closeEvent(self, event):
        self._stop_stream()
        if self.audio_engine.is_open:
            self.audio_engine.close()
        if self._vfo_active == "A":
            self.settings.last_freq = self._vfo_a
        else:
            self.settings.last_freq = self._vfo_b
        self.settings.last_modulation = self._current_mod
        self.settings.audio.volume = self._sld_vol.value() / 100
        favs = []
        for ch in self.channel_table.channels:
            favs.append({
                "label": ch.label, "freq_hz": ch.frequency,
                "modulation": ch.modulation, "squelch": ch.squelch, "bank": ch.bank,
            })
        self.settings.favorites = favs
        self.settings.save()
        event.accept()
