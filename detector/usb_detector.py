import threading, time, numpy as np
from typing import Optional, Callable


SDR_VENDOR_IDS = {
    "0bda": "Realtek (RTL-SDR)",
    "1d50": "Airspy / HackRF",
    "1d19": "HackRF",
    "1b71": "HackRF 2.0",
    "13e3": "HackRF (Alt)",
    "10c4": "CP210x (SDR)",
    "0403": "FTDI (SDR)",
}


class USBDetector:
    def __init__(self):
        self._known: dict[str, dict] = {}
        self._listeners: list[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def add_listener(self, cb: Callable):
        self._listeners.append(cb)

    def notify(self, event: str, device_info: dict):
        for cb in self._listeners:
            try:
                cb(event, device_info)
            except:
                pass

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _monitor(self):
        while self._running:
            current = self._scan_sdr_devices()
            now_keys = set(current.keys())
            prev_keys = set(self._known.keys())
            new_keys = now_keys - prev_keys
            gone_keys = prev_keys - now_keys
            for k in new_keys:
                self.notify("attached", current[k])
            for k in gone_keys:
                self.notify("detached", self._known[k])
            self._known = current
            time.sleep(3)

    def _scan_sdr_devices(self) -> dict[str, dict]:
        devices = {}
        try:
            import subprocess
            r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.strip().split("\n"):
                line_lower = line.lower()
                is_sdr = False
                for vid, name in SDR_VENDOR_IDS.items():
                    if vid in line_lower:
                        is_sdr = True
                        break
                for kw in ["rtl2832", "rtl2838", "airspy", "hackrf", "sdr"]:
                    if kw in line_lower:
                        is_sdr = True
                        break
                if is_sdr:
                    parts = line.split()
                    bus = parts[1] if len(parts) > 1 else "?"
                    dev_num = parts[3].rstrip(":") if len(parts) > 3 else "?"
                    key = f"{bus}:{dev_num}"
                    devices[key] = {"id": key, "name": line.strip(), "raw": line}
        except:
            pass
        return devices

    def count_devices(self, device_type: str = None) -> int:
        count = 0
        try:
            import subprocess
            r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=3)
            for line in r.stdout.strip().split("\n"):
                ll = line.lower()
                if device_type == "rtlsdr":
                    if "rtl" in ll or "0bda" in ll:
                        count += 1
                elif device_type == "airspy":
                    if "airspy" in ll or "1d50:60a" in ll:
                        count += 1
                else:
                    for vid in SDR_VENDOR_IDS:
                        if vid in ll:
                            count += 1
                            break
        except:
            pass
        return max(count, 0)


class IFMeter:
    def __init__(self):
        self._noise_floor: float = -120.0
        self._noise_floor_alpha: float = 0.01
        self._calibrated: bool = False

    def update_noise_floor(self, db: float):
        if not self._calibrated:
            self._noise_floor = db
            self._calibrated = True
        else:
            self._noise_floor += self._noise_floor_alpha * (db - self._noise_floor)

    def dbm_from_iq(self, iq_samples, gain_db: float = 0) -> float:
        power = np.mean(np.abs(iq_samples) ** 2)
        db_raw = 20 * np.log10(np.sqrt(power) + 1e-15)
        return db_raw + 90 - gain_db


class SignalDetector:
    def __init__(self):
        self._noise_floor: float = -100.0
        self._threshold: float = -40.0
        self._if_meter = IFMeter()
        self._alpha = 0.05
        self._peak_power = -100.0
        self._s_meter_values = {
            'S9+40': -33, 'S9+20': -53, 'S9+10': -63,
            'S9': -73, 'S8': -79, 'S7': -85, 'S6': -91,
            'S5': -97, 'S4': -103, 'S3': -109, 'S2': -115, 'S1': -121,
        }

    def set_threshold(self, db: float):
        self._threshold = db

    def get_s_meter(self, dbm: float) -> str:
        for label, val in sorted(self._s_meter_values.items(), key=lambda x: -x[1]):
            if dbm >= val:
                return label
        return "S0"

    def analyze(self, iq_samples) -> dict:
        power = np.mean(np.abs(iq_samples) ** 2)
        power_db = 20 * np.log10(np.sqrt(power) + 1e-15)
        dbm = self._if_meter.dbm_from_iq(iq_samples)
        self._if_meter.update_noise_floor(power_db)
        noise_floor = self._if_meter._noise_floor
        snr = dbm - noise_floor if noise_floor > -200 else 0
        self._noise_floor += self._alpha * (power_db - self._noise_floor)
        self._peak_power = max(self._peak_power * 0.95, dbm)

        fft = np.fft.fftshift(np.fft.fft(iq_samples, 1024))
        psd = 20 * np.log10(np.abs(fft) + 1e-15)
        peak_idx = np.argmax(psd)
        peak_db = psd[peak_idx]
        peak_bin_frac = peak_idx / len(psd) - 0.5
        bw_bins = np.sum(psd > peak_db - 6)
        bw_est = bw_bins / len(psd)

        return {
            "power_db": round(power_db, 1),
            "dbm": round(dbm, 1),
            "s_meter": self.get_s_meter(dbm),
            "snr_db": round(snr, 1),
            "peak_db": round(peak_db, 1),
            "signal_detected": dbm > self._threshold or snr > 5,
            "bandwidth_norm": round(bw_est, 3),
            "noise_floor": round(noise_floor, 1),
            "peak_position": round(peak_bin_frac, 3),
        }
