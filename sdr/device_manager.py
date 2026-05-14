import numpy as np
from typing import Optional, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass


SDR_USB_IDS = {
    "0bda:2832": "RTL-SDR (Generic)",
    "0bda:2838": "RTL-SDR (R820T2)",
    "0bda:2831": "RTL-SDR (E4000)",
    "1d50:60a1": "Airspy R2",
    "1d50:60a3": "Airspy Mini",
    "1d50:60a5": "Airspy HF+",
    "1d50:60a6": "Airspy Server",
    "1d50:6089": "HackRF One",
    "1d19:1101": "HackRF (Great Scott)",
    "1b71:3002": "HackRF (2.0)",
}


def probe_usb_sdr() -> list[tuple[str, str]]:
    found = []
    try:
        import subprocess
        r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.strip().split("\n"):
            line_lower = line.lower()
            for usb_id, name in SDR_USB_IDS.items():
                if usb_id in line_lower:
                    found.append((usb_id, name))
                    break
            for kw in ["rtl2832", "rtl2838", "airspy", "hackrf"]:
                if kw in line_lower:
                    found.append((line, line.strip()))
                    break
    except:
        pass
    seen = set()
    unique = []
    for item in found:
        if item[1] not in seen:
            seen.add(item[1])
            unique.append(item)
    return unique


@dataclass
class SDRInfo:
    index: int
    name: str
    vendor: str = ""
    product: str = ""
    serial: str = ""
    tuner: str = ""
    usb_id: str = ""


class SDRDevice(ABC):
    @abstractmethod
    def open(self) -> bool: ...
    @abstractmethod
    def close(self): ...
    @abstractmethod
    def start_stream(self, callback: Callable[[np.ndarray], None]): ...
    @abstractmethod
    def stop_stream(self): ...
    @abstractmethod
    def set_center_freq(self, freq_hz: float): ...
    @abstractmethod
    def set_freq_correction(self, ppm: int): ...
    @abstractmethod
    def set_gain(self, gain: int): ...
    @abstractmethod
    def set_if_gain(self, gain: int): ...
    @abstractmethod
    def set_bb_gain(self, gain: int): ...
    @abstractmethod
    def set_bias_t(self, enabled: bool): ...
    @abstractmethod
    def set_direct_sampling(self, enabled: bool): ...
    @abstractmethod
    def get_sample_rate(self) -> float: ...
    @abstractmethod
    def get_name(self) -> str: ...
    @abstractmethod
    def get_info(self) -> SDRInfo: ...
    @property
    @abstractmethod
    def is_open(self) -> bool: ...


class RTLSDRDevice(SDRDevice):
    def __init__(self, device_index: int = 0):
        self._index = device_index
        self._dev = None
        self._running = False
        self._callback: Optional[Callable] = None
        self._sr = 2.4e6
        self._bias_t = False
        self._direct_sampling = False

    def open(self) -> bool:
        try:
            from rtlsdr import RtlSdr
            try:
                self._dev = RtlSdr(device_index=self._index)
            except Exception as e:
                # Může nastat OSError kvůli nekompatibilní knihovně (např. chybějící symboly)
                print(f"[Warning] Nelze inicializovat RtlSdr: {e}")
                self._dev = None
                return False
            try:
                self._dev.sample_rate = int(self._sr)
            except Exception:
                pass
            try:
                # some rtlsdr bindings set ERP via attribute
                self._dev.erp = True
            except Exception:
                pass
            return True
        except Exception as e:
            # chybný import nebo jiný problém
            print(f"RTL-SDR #{self._index} error: {e}")
            return False

    def close(self):
        self.stop_stream()
        if self._dev:
            try:
                self._dev.close()
            except:
                pass
            self._dev = None

    def start_stream(self, callback: Callable[[np.ndarray], None]):
        self._callback = callback
        self._running = True
        import threading
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()

    def _stream_loop(self):
        while self._running and self._dev:
            try:
                samples = self._dev.read_samples(256 * 16, timeout=1)
                print(f"[Debug] Device read {len(samples)} samples.")
                if self._callback and len(samples) > 0:
                    self._callback(samples.astype(np.complex64))
            except:
                pass

    def stop_stream(self):
        self._running = False

    def set_center_freq(self, freq_hz: float):
        if self._dev:
            try:
                self._dev.center_freq = int(freq_hz)
            except:
                pass

    def set_freq_correction(self, ppm: int):
        if self._dev:
            try:
                self._dev.freq_correction = ppm
            except:
                pass

    def set_gain(self, gain: int):
        if self._dev:
            try:
                self._dev.gain = gain
            except:
                pass

    def set_if_gain(self, gain: int):
        if self._dev:
            try:
                self._dev.set_if_gain(0, gain)
            except:
                pass

    def set_bb_gain(self, gain: int):
        pass

    def set_bias_t(self, enabled: bool):
        self._bias_t = enabled
        if self._dev:
            try:
                self._dev.set_bias_tee(enabled)
            except:
                pass

    def set_direct_sampling(self, enabled: bool):
        self._direct_sampling = enabled
        if self._dev:
            try:
                self._dev.direct_sampling = 1 if enabled else 0
            except:
                pass

    def get_sample_rate(self) -> float:
        return self._sr

    def get_name(self) -> str:
        info = self.get_info()
        return info.name

    def get_info(self) -> SDRInfo:
        name = f"RTL-SDR #{self._index}"
        tuner = ""
        if self._dev:
            try:
                name = self._dev.get_device_name()
                tuner = str(self._dev.get_tuner_type())
            except:
                pass
        return SDRInfo(index=self._index, name=name, tuner=tuner)

    @property
    def is_open(self) -> bool:
        return self._dev is not None


class AirspyDevice(SDRDevice):
    def __init__(self, device_index: int = 0):
        self._index = device_index
        self._dev = None
        self._running = False
        self._callback = None
        self._sr = 10e6

    def open(self) -> bool:
        try:
            from sdr import airspy_native as airspy
            self._dev = airspy.Airspy(self._index)
            self._dev.sample_rate = self._sr
            return True
        except ImportError as e:
            print(f"Airspy library not available: {e}")
            return False
        except Exception as e:
            print(f"Airspy #{self._index} error: {e}")
            return False

    def close(self):
        self.stop_stream()
        if self._dev:
            try:
                self._dev.close()
            except:
                pass
            self._dev = None

    def start_stream(self, callback: Callable[[np.ndarray], None]):
        self._callback = callback
        self._running = True
        import threading
        threading.Thread(target=self._stream_loop, daemon=True).start()

    def _stream_loop(self):
        while self._running and self._dev:
            try:
                samples = self._dev.read_samples(1024 * 16)
                print(f"[Debug] Device read {len(samples)} samples.")
                if self._callback:
                    self._callback(samples.astype(np.complex64))
            except:
                pass

    def stop_stream(self):
        self._running = False
        if self._dev:
            try:
                self._dev.stop_rx()
            except:
                pass

    def set_center_freq(self, freq_hz: float):
        if self._dev:
            try:
                self._dev.frequency = int(freq_hz)
            except:
                pass

    def set_freq_correction(self, ppm: int):
        pass

    def set_gain(self, gain: int):
        if self._dev:
            try:
                self._dev.lna_gain = gain
            except:
                pass

    def set_if_gain(self, gain: int):
        if self._dev:
            try:
                self._dev.mixer_gain = gain
            except:
                pass

    def set_bb_gain(self, gain: int):
        if self._dev:
            try:
                self._dev.vga_gain = gain
            except:
                pass

    def set_bias_t(self, enabled: bool):
        pass

    def set_direct_sampling(self, enabled: bool):
        pass

    def get_sample_rate(self) -> float:
        return self._sr

    def get_name(self) -> str:
        return f"Airspy #{self._index}"

    def get_info(self) -> SDRInfo:
        return SDRInfo(index=self._index, name=self.get_name())

    @property
    def is_open(self) -> bool:
        return self._dev is not None


class DeviceManager:
    def __init__(self):
        self._devices: list[SDRDevice] = []
        self._active: Optional[SDRDevice] = None
        self._last_scan: list[tuple[int, str]] = []

    def enumerate(self) -> list[tuple[int, str]]:
        self._devices = []
        results = []

        usb_devices = probe_usb_sdr()
        has_rtl_usb = any("RTL" in n or "rtl" in n.lower() for _, n in usb_devices)
        has_airspy_usb = any("Airspy" in n or "airspy" in n.lower() for _, n in usb_devices)

        rtl_lib_ok = False
        try:
            from rtlsdr import RtlSdr
            rtl_lib_ok = True
        except:
            pass

        airspy_lib_ok = False
        try:
            from sdr import airspy_native as airspy
            airspy_lib_ok = True
        except Exception as e:
            print(f"[Info] Airspy native wrapper not available: {e}")
            pass

        if rtl_lib_ok:
            try:
                from rtlsdr.rtlsdr import librtlsdr
                try:
                    dev_count = librtlsdr.rtlsdr_get_device_count()
                except Exception as e:
                    # knihovna může být nekompatibilní -> zalogujeme a použijeme fallback
                    print(f"[Warning] Chyba při dotazu na librtlsdr: {e}")
                    dev_count = 0
                for i in range(dev_count):
                    try:
                        name = librtlsdr.rtlsdr_get_device_name(i)
                        if isinstance(name, bytes):
                            name = name.decode('utf-8', errors='replace')
                    except:
                        name = f"RTL-SDR #{i}"
                    self._devices.append(RTLSDRDevice(i))
                    results.append((len(results), name))
                # pokud knihovna existuje, ale žádná zařízení nenalezena, zkusíme otevřít běžné indexy
                if dev_count == 0 and has_rtl_usb:
                    for i in range(2):
                        d = RTLSDRDevice(i)
                        if d.open():
                            d.close()
                            self._devices.append(RTLSDRDevice(i))
                            results.append((len(results), f"RTL-SDR #{len(results)}"))
            except Exception as e:
                # Pokud import nebo volání librtlsdr úplně selže, pokračujeme bez přerušení
                print(f"[Warning] Nelze použít librtlsdr: {e}")
                if has_rtl_usb:
                    for i in range(2):
                        d = RTLSDRDevice(i)
                        # zkusíme otevřít, pokud se otevře, přidáme ho
                        try:
                            if d.open():
                                d.close()
                                self._devices.append(RTLSDRDevice(i))
                                results.append((len(results), f"RTL-SDR #{len(results)}"))
                        except Exception:
                            pass
        elif has_rtl_usb:
            for i in range(2):
                self._devices.append(RTLSDRDevice(i))
                results.append((len(results), f"RTL-SDR #{i} (detected via USB)"))

        if airspy_lib_ok:
            try:
                from sdr import airspy_native as airspy
                if hasattr(airspy, 'list_devices'):
                    try:
                        dev_list = airspy.list_devices()
                        for i in range(len(dev_list)):
                            self._devices.append(AirspyDevice(i))
                            results.append((len(results), f"Airspy #{i}"))
                    except Exception as e:
                        print(f"[Warning] airspy.list_devices failed: {e}")
                        pass
                # If no Airspy devices found yet, try opening by index
                if not any("Airspy" in n for _, n in results):
                    for i in range(2):
                        try:
                            test = airspy.Airspy(i)
                            test.close()
                            self._devices.append(AirspyDevice(i))
                            results.append((len(results), f"Airspy #{i}"))
                            break
                        except Exception as e:
                            print(f"[Debug] Cannot open Airspy #{i}: {e}")
                            pass
            except Exception as e:
                print(f"[Warning] Airspy detection error: {e}")
                if has_airspy_usb:
                    self._devices.append(AirspyDevice(0))
                    results.append((len(results), "Airspy (detected via USB)"))

        if not results:
            if rtl_lib_ok:
                self._devices.append(RTLSDRDevice(0))
                results.append((0, "RTL-SDR (demo)"))
            elif airspy_lib_ok:
                self._devices.append(AirspyDevice(0))
                results.append((0, "Airspy (demo)"))

        self._last_scan = results
        return results

    def _probe_airspy_index(self, index: int) -> bool:
        try:
            from sdr import airspy_native as airspy
            d = airspy.Airspy(index)
            d.close()
            return True
        except:
            return False

    def select_device(self, index: int) -> Optional[SDRDevice]:
        if 0 <= index < len(self._devices):
            self._active = self._devices[index]
            return self._active
        return None

    @property
    def active(self) -> Optional[SDRDevice]:
        return self._active


def serial_from_lsusb(vendor_id: str) -> str:
    try:
        import subprocess
        r = subprocess.run(["lsusb", "-v"], capture_output=True, text=True, timeout=3, stderr=subprocess.DEVNULL)
        for line in r.stdout.split("\n"):
            if "iSerial" in line and vendor_id in r.stdout.lower():
                parts = line.strip().split()
                if len(parts) >= 3:
                    return parts[-1]
    except:
        pass
    return ""
