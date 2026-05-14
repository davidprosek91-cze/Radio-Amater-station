import threading, time
from typing import Optional, Callable
from dataclasses import dataclass, field


@dataclass
class Channel:
    frequency: float
    label: str = ""
    modulation: str = "NFM"
    squelch: float = 0.5
    squelch_type: str = "noise"
    step_khz: float = 12.5
    priority: int = 0
    enabled: bool = True
    bank: str = "Default"
    trunk_system: str = ""
    color_code: int = 0
    nac: int = 0
    bandwidth: float = 12500.0
    ctcss: float = 0.0
    dcs: int = 0
    tone_squelch: bool = False
    agc: bool = True
    noise_blanker: bool = False


class ScannerEngine:
    SCAN, HOLD, SEARCH, STOPPED = range(4)

    def __init__(self):
        self._state = self.STOPPED
        self._channels: list[Channel] = []
        self._index = 0
        self._lock = threading.Lock()
        self._on_channel_change: Optional[Callable[[Channel], None]] = None
        self._on_signal: Optional[Callable[[Channel, float], None]] = None
        self._on_hold: Optional[Callable[[Channel, float], None]] = None
        self._hold_time_ms = 3000
        self._hang_time_ms = 2000
        self._hold_channel: Optional[Channel] = None
        self._hang_until = 0.0
        self._priority_channels: list[Channel] = []
        self._priority_interval = 3
        self._priority_counter = 0
        self._search_range: list[tuple] = []
        self._search_band_index = 0
        self._search_current = 144.0e6
        self._search_band = (144.0e6, 148.0e6, 12.5e3, "NFM")
        self._thread: Optional[threading.Thread] = None
        self._signal_present = False
        self._captured: set[float] = set()
        self._auto_capture: bool = False
        self._capture_bank: str = "Scan Bank"

    def set_callbacks(self, on_channel=None, on_signal=None, on_hold=None):
        self._on_channel_change = on_channel
        self._on_signal = on_signal
        self._on_hold = on_hold

    def set_hold_time(self, ms: int):
        self._hold_time_ms = ms

    def set_hang_time(self, ms: int):
        self._hang_time_ms = ms

    def set_auto_capture(self, enabled: bool, bank: str = "Scan Bank"):
        self._auto_capture = enabled
        self._capture_bank = bank

    def get_captured_freqs(self) -> list[float]:
        with self._lock:
            return sorted(self._captured)

    def clear_captured(self):
        with self._lock:
            self._captured.clear()

    def load_channels(self, channels: list[Channel]):
        with self._lock:
            self._channels = channels
            self._priority_channels = [c for c in channels if c.priority > 0]
            self._index = 0

    def add_channel(self, ch: Channel):
        with self._lock:
            self._channels.append(ch)
            if ch.priority > 0:
                self._priority_channels.append(ch)

    def remove_channel(self, freq: float):
        with self._lock:
            self._channels = [c for c in self._channels if c.frequency != freq]
            self._priority_channels = [c for c in self._channels if c.priority > 0]

    def set_search_range(self, lo: float, hi: float):
        pass

    def set_search_step(self, step: float):
        pass

    def load_bands(self, bands: list[dict]):
        with self._lock:
            self._search_range = []
            for b in bands:
                lo = b['lo']
                hi = b['hi']
                step = b.get('step', 12.5e3)
                mod = b.get('mod', 'NFM')
                if hi > lo:
                    self._search_range.append((lo, hi, step, mod, b.get('name', '')))
            self._search_band_index = 0
            if self._search_range:
                self._search_band = self._search_range[0]
                self._search_current = self._search_band[0]

    @property
    def current_channel(self) -> Optional[Channel]:
        with self._lock:
            if self._state == self.HOLD and self._hold_channel:
                return self._hold_channel
            if self._state == self.SEARCH:
                return Channel(
                    frequency=self._search_current,
                    label="SCAN",
                    modulation=self._search_band[3],
                )
            if 0 <= self._index < len(self._channels):
                return self._channels[self._index]
            return None

    @property
    def current_modulation(self) -> str:
        with self._lock:
            if self._state == self.SEARCH:
                return self._search_band[3] if self._search_band else "NFM"
            if self._state == self.HOLD and self._hold_channel:
                return self._hold_channel.modulation
            if self._state == self.SCAN and 0 <= self._index < len(self._channels):
                return self._channels[self._index].modulation
            return "NFM"

    @property
    def is_searching(self) -> bool:
        return self._state == self.SEARCH

    @property
    def band_label(self) -> str:
        with self._lock:
            if self._search_range and self._search_band_index < len(self._search_range):
                b = self._search_range[self._search_band_index]
                return f"{b[0]/1e6:.0f}-{b[1]/1e6:.0f} MHz {b[4]}"
            return ""

    def start(self):
        with self._lock:
            if self._state == self.STOPPED:
                if self._search_range and not self._channels:
                    self._state = self.SEARCH
                else:
                    self._state = self.SCAN
                self._index = 0
                self._signal_present = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        with self._lock:
            self._state = self.STOPPED
            self._signal_present = False

    def hold(self):
        with self._lock:
            if self.current_channel:
                self._hold_channel = self.current_channel
                self._state = self.HOLD

    def resume(self):
        with self._lock:
            self._state = self.SCAN if self._channels else self.SEARCH
            self._hold_channel = None
            self._signal_present = False

    def signal_detected(self, channel: Channel, power_db: float):
        with self._lock:
            was_searching = self._state == self.SEARCH
            self._hold_channel = channel
            self._hang_until = time.time() + self._hang_time_ms / 1000.0
            self._state = self.HOLD
            self._signal_present = True
        if self._on_signal:
            self._on_signal(channel, power_db)
        if was_searching and self._auto_capture and channel and channel.frequency not in self._captured:
            self._captured.add(channel.frequency)
            if self._on_hold:
                self._on_hold(channel, power_db)

    def signal_active(self, power_db: float):
        with self._lock:
            if self._state == self.HOLD:
                self._hang_until = time.time() + self._hang_time_ms / 1000.0
                self._signal_present = True

    def signal_lost(self):
        with self._lock:
            self._signal_present = False

    def _run(self):
        while True:
            with self._lock:
                state = self._state
                if state == self.STOPPED:
                    return
            if state == self.SCAN:
                self._tick_scan()
            elif state == self.HOLD:
                self._tick_hold()
            elif state == self.SEARCH:
                self._tick_search()
            else:
                time.sleep(0.1)

    def _tick_scan(self):
        self._priority_counter += 1
        with self._lock:
            if self._priority_channels and self._priority_counter >= self._priority_interval:
                self._priority_counter = 0
                ch = self._priority_channels[0]
            else:
                if not self._channels:
                    self._state = self.SEARCH if self._search_range else self.STOPPED
                    return
                self._index = (self._index + 1) % len(self._channels)
                ch = self._channels[self._index]
        if self._on_channel_change:
            self._on_channel_change(ch)
        time.sleep(0.05)

    def _tick_hold(self):
        now = time.time()
        with self._lock:
            if self._signal_present:
                self._hang_until = now + self._hang_time_ms / 1000.0
            if not self._signal_present and now > self._hang_until:
                self._state = self.SCAN if self._channels else self.SEARCH
                self._hold_channel = None
        time.sleep(0.05)

    def _tick_search(self):
        with self._lock:
            if not self._search_range:
                self._state = self.STOPPED
                return
            lo, hi, step, mod, name = self._search_band
            self._search_current += step
            if self._search_current > hi:
                self._search_band_index = (self._search_band_index + 1) % len(self._search_range)
                self._search_band = self._search_range[self._search_band_index]
                lo, hi, step, mod, name = self._search_band
                self._search_current = lo
            ch = Channel(
                frequency=self._search_current,
                label=name,
                modulation=mod,
            )
        if self._on_channel_change:
            self._on_channel_change(ch)
        time.sleep(0.02)
