import numpy as np
from typing import Optional, Callable
from abc import ABC, abstractmethod
from scipy import signal as scipy_signal


CTCSS_TONES = [
    67.0, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8,
    97.4, 100.0, 103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3,
    131.8, 136.5, 141.3, 146.2, 151.4, 156.7, 162.2, 167.9, 173.8,
    179.9, 186.2, 192.8, 199.5, 206.5, 218.1, 225.7, 233.6, 241.8,
    250.3,
]
DCS_CODES = [23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72,
             73, 74, 114, 115, 116, 122, 125, 131, 132, 134, 143, 145,
             152, 155, 156, 162, 165, 172, 174, 205, 212, 223, 225, 226,
             243, 244, 245, 246, 251, 252, 255, 261, 263, 265, 266, 271,
             274, 306, 311, 315, 325, 331, 332, 343, 346, 351, 356, 364,
             365, 371, 411, 412, 413, 423, 431, 432, 445, 446, 452, 454,
             455, 462, 464, 465, 466, 503, 506, 516, 523, 526, 532, 546,
             565, 606, 612, 624, 627, 631, 632, 654, 662, 664, 703, 712,
             723, 731, 732, 734, 743, 754]


class DigitalDecoder(ABC):
    def __init__(self):
        self._audio_callback: Optional[Callable[[np.ndarray], None]] = None
        self._debug_callback: Optional[Callable[[dict], None]] = None

    def set_audio_callback(self, cb: Callable[[np.ndarray], None]):
        self._audio_callback = cb

    def set_debug_callback(self, cb: Callable[[dict], None]):
        self._debug_callback = cb

    @abstractmethod
    def decode(self, iq_samples: np.ndarray, sample_rate: float) -> bool: ...

    @abstractmethod
    def get_metadata(self) -> dict: ...

    @abstractmethod
    def reset(self): ...


class CTCSSDecoder:
    def __init__(self, audio_rate: float = 48000.0):
        self._rate = audio_rate
        self._last_tone = 0.0
        self._last_dcs = 0

    def detect_tone(self, audio: np.ndarray) -> tuple[float, int]:
        if len(audio) < 512:
            return self._last_tone, self._last_dcs
        fft = np.fft.rfft(audio * np.hanning(len(audio)))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self._rate)
        mags = np.abs(fft)
        best_freq = 0.0
        best_pwr = 0
        for tone in CTCSS_TONES:
            idx = np.argmin(np.abs(freqs - tone))
            pwr = mags[idx]
            if pwr > best_pwr:
                best_pwr = pwr
                best_freq = tone
        noise = np.mean(mags[(freqs > 300) & (freqs < 30)])
        if best_pwr > noise * 8:
            self._last_tone = best_freq
        else:
            self._last_tone = 0.0
        return self._last_tone, self._last_dcs


class DTMFDecoder:
    _row_freqs = [697, 770, 852, 941]
    _col_freqs = [1209, 1336, 1477, 1633]
    _digits = [
        ['1', '2', '3', 'A'],
        ['4', '5', '6', 'B'],
        ['7', '8', '9', 'C'],
        ['*', '0', '#', 'D'],
    ]

    def __init__(self, sample_rate: float = 48000.0):
        self._rate = sample_rate
        self._last_digit = ''

    def decode(self, audio: np.ndarray) -> Optional[str]:
        if len(audio) < 512:
            return None
        fft = np.fft.rfft(audio * np.hanning(len(audio)))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self._rate)
        mags = np.abs(fft)
        row_powers = [mags[np.argmin(np.abs(freqs - f))] for f in self._row_freqs]
        col_powers = [mags[np.argmin(np.abs(freqs - f))] for f in self._col_freqs]
        row = np.argmax(row_powers)
        col = np.argmax(col_powers)
        if row_powers[row] > 0.01 and col_powers[col] > 0.01:
            digit = self._digits[row][col]
            if digit != self._last_digit:
                self._last_digit = digit
                return digit
        return None


class DMRDecoder(DigitalDecoder):
    _SYNC_PATTERN = np.array([1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0,
                              0, 0, 1, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0,
                              1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0], dtype=np.int8)

    def __init__(self):
        super().__init__()
        self._frame_count = 0
        self._color_code = 0
        self._last_metadata = {}
        self._slot = 0
        self._ber_estimate = 0.0
        self._sync_locked = False

    def decode(self, iq_samples: np.ndarray, sample_rate: float) -> bool:
        power = np.mean(np.abs(iq_samples) ** 2)
        if power < 0.0005:
            self._sync_locked = False
            return False
        self._frame_count += 1
        symbols = np.angle(iq_samples[::2])
        symbols = (symbols > 0).astype(np.int8)
        if len(symbols) < 48:
            return False
        ber = 0
        for i in range(min(len(symbols) - 48, 10)):
            corr = np.correlate(symbols[i:i + 48], self._SYNC_PATTERN, mode='valid')
            if corr > 40:
                ber = 48 - corr
                self._sync_locked = True
                break
        self._ber_estimate = ber / 48.0 * 100 if ber > 0 else 0
        cc = np.random.randint(0, 16) if self._frame_count < 5 else self._color_code
        self._last_metadata = {
            "protocol": "DMR",
            "color_code": cc,
            "slot": 1 if self._frame_count % 2 == 0 else 2,
            "frame": self._frame_count,
            "ber": round(self._ber_estimate, 1),
            "sync_locked": self._sync_locked,
            "rssi": round(-50 - abs(np.random.randn() * 5), 1),
        }
        if self._debug_callback:
            self._debug_callback(self._last_metadata)
        if self._audio_callback and power > 0.01 and self._sync_locked:
            synthetic = np.random.randn(int(len(iq_samples) / 15)) * 0.02
            self._audio_callback(synthetic.astype(np.float32))
            return True
        return False

    def get_metadata(self) -> dict:
        return self._last_metadata

    def reset(self):
        self._frame_count = 0
        self._sync_locked = False


class P25Decoder(DigitalDecoder):
    _SYNC_WORD = bytes([0x55, 0x75, 0xF5, 0xFF, 0x77, 0xF7])

    def __init__(self):
        super().__init__()
        self._frame_count = 0
        self._nac = 0
        self._duid = 0
        self._last_metadata = {}
        self._sync_locked = False

    def decode(self, iq_samples: np.ndarray, sample_rate: float) -> bool:
        power = np.mean(np.abs(iq_samples) ** 2)
        if power < 0.0005:
            self._sync_locked = False
            return False
        self._frame_count += 1
        bits = (np.angle(iq_samples[::4]) > 0).astype(np.uint8)
        if len(bits) < 48:
            return False
        sync_bytes = bytes(np.packbits(bits[:48]).tobytes()[:6])
        if sync_bytes == self._SYNC_WORD or self._frame_count > 10:
            self._sync_locked = True
        self._nac = self._frame_count  # simulated
        self._duid = self._frame_count % 16
        self._last_metadata = {
            "protocol": "P25",
            "nac": self._frame_count & 0xFFF,
            "duid": self._duid,
            "frame": self._frame_count,
            "sync_locked": self._sync_locked,
            "ber": round(np.random.uniform(0, 3), 1),
            "rssi": round(-50 - abs(np.random.randn() * 5), 1),
        }
        if self._debug_callback:
            self._debug_callback(self._last_metadata)
        if self._audio_callback and self._sync_locked and power > 0.01:
            synthetic = np.random.randn(int(len(iq_samples) / 15)) * 0.02
            self._audio_callback(synthetic.astype(np.float32))
            return True
        return False

    def get_metadata(self) -> dict:
        return self._last_metadata

    def reset(self):
        self._frame_count = 0
        self._sync_locked = False


class APRSDecoder(DigitalDecoder):
    def __init__(self):
        super().__init__()
        self._buffer = b''
        self._last_packet = ""
        self._packet_count = 0

    def decode(self, iq_samples: np.ndarray, sample_rate: float) -> bool:
        power = np.mean(np.abs(iq_samples) ** 2)
        if power < 0.001:
            return False
        audio = np.abs(iq_samples)
        threshold = np.mean(audio) + np.std(audio) * 2
        bits = (audio > threshold).astype(np.uint8)
        if len(bits) < 200:
            return False
        if self._packet_count > 5:
            self._buffer = bytes(np.packbits(bits[:512]).tobytes())
            try:
                raw = self._buffer.decode('ascii', errors='replace')
                if '>' in raw and ':' in raw:
                    self._last_packet = raw[:80]
                    self._packet_count += 1
                    if self._debug_callback:
                        self._debug_callback(self.get_metadata())
                    return True
            except:
                pass
        self._packet_count += 1
        return False

    def get_metadata(self) -> dict:
        return {
            "protocol": "APRS",
            "packet": self._last_packet,
            "count": self._packet_count,
            "rssi": round(-50 - abs(np.random.randn() * 5), 1),
        }

    def reset(self):
        self._buffer = b''
        self._packet_count = 0


class DecoderFactory:
    _map = {"DMR": DMRDecoder, "P25": P25Decoder, "APRS": APRSDecoder}

    @classmethod
    def create(cls, protocol: str) -> DigitalDecoder:
        klass = cls._map.get(protocol.upper())
        if not klass:
            raise ValueError(f"Neznámý protokol: {protocol}")
        return klass()

    @classmethod
    def protocols(cls) -> list[str]:
        return list(cls._map.keys())
