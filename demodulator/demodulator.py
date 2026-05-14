import numpy as np
from typing import Optional, Callable
from abc import ABC, abstractmethod
from scipy import signal as scipy_signal


class Demodulator(ABC):
    def __init__(self):
        self._callback: Optional[Callable[[np.ndarray], None]] = None
        self._squelch_threshold: float = 0.0
        self._squelch_type: str = "noise"
        self._squelch_open: bool = False
        self._sample_rate: float = 2.4e6
        self._audio_rate: float = 48000.0
        self._agc_enabled: bool = True
        self._agc_attack: float = 0.01
        self._agc_decay: float = 0.001
        self._agc_gain: float = 1.0
        self._noise_blanker: bool = False
        self._nb_threshold: float = 3.0
        self._ctcss_freq: float = 0.0
        self._ctcss_detected: float = 0.0
        self._lp_filter: Optional[np.ndarray] = None
        self._hp_filter: Optional[np.ndarray] = None

    def set_callback(self, cb: Callable[[np.ndarray], None]):
        self._callback = cb

    def set_squelch(self, threshold: float):
        self._squelch_threshold = threshold

    def set_squelch_type(self, stype: str):
        self._squelch_type = stype

    def set_sample_rate(self, sr: float):
        self._sample_rate = sr
        self._build_filters()

    def set_audio_rate(self, ar: float):
        self._audio_rate = ar
        self._build_filters()

    def set_agc(self, enabled: bool):
        self._agc_enabled = enabled

    def set_noise_blanker(self, enabled: bool, threshold: float = 3.0):
        self._noise_blanker = enabled
        self._nb_threshold = threshold

    def set_ctcss(self, freq: float):
        self._ctcss_freq = freq

    def _build_filters(self):
        if self._sample_rate <= 0:
            return
        cutoff = min(self._audio_rate * 0.45, self._sample_rate * 0.45)
        if cutoff > 0:
            self._lp_filter = scipy_signal.firwin(63, cutoff, fs=self._sample_rate)
        hp_cut = max(100, self._audio_rate * 0.005)
        if hp_cut < self._sample_rate * 0.5:
            self._hp_filter = scipy_signal.firwin(63, hp_cut, fs=self._sample_rate, pass_zero=False)

    def _apply_filters(self, audio: np.ndarray) -> np.ndarray:
        if self._lp_filter is not None and len(audio) > len(self._lp_filter):
            audio = scipy_signal.convolve(audio, self._lp_filter, mode='same')
        if self._hp_filter is not None and len(audio) > len(self._hp_filter):
            audio = scipy_signal.convolve(audio, self._hp_filter, mode='same')
        return audio

    def _apply_agc(self, audio: np.ndarray) -> np.ndarray:
        if not self._agc_enabled:
            return audio
        peak = np.max(np.abs(audio))
        if peak > 0:
            target = 0.3
            error = target - peak
            if error > 0:
                self._agc_gain += self._agc_attack * error
            else:
                self._agc_gain += self._agc_decay * error
            self._agc_gain = max(0.1, min(10.0, self._agc_gain))
            audio = audio * self._agc_gain
        return np.clip(audio, -1.0, 1.0)

    def _apply_noise_blanker(self, audio: np.ndarray) -> np.ndarray:
        if not self._noise_blanker:
            return audio
        std = np.std(audio)
        if std > 0:
            mask = np.abs(audio) < self._nb_threshold * std
            audio = audio * mask
        return audio

    def _detect_ctcss(self, audio: np.ndarray) -> float:
        if self._ctcss_freq <= 0:
            return 0.0
        fft = np.fft.rfft(audio * np.hanning(len(audio)))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self._audio_rate)
        idx = np.argmin(np.abs(freqs - self._ctcss_freq))
        power = np.abs(fft[idx])
        total = np.sum(np.abs(fft))
        ratio = power / (total + 1e-10)
        return power if ratio > 0.05 else 0.0

    def _squelch_check(self, audio: np.ndarray) -> bool:
        if len(audio) < 4:
            return False
        if self._squelch_type == "noise":
            noise = audio - scipy_signal.medfilt(audio, 5)
            noise_pwr = np.sqrt(np.mean(noise ** 2))
            audio_pwr = np.sqrt(np.mean(audio ** 2))
            ratio = audio_pwr / (noise_pwr + 1e-10)
            return ratio > self._squelch_threshold
        elif self._squelch_type == "power":
            pwr = 20 * np.log10(np.max(np.abs(audio)) + 1e-10)
            return pwr > self._squelch_threshold
        elif self._squelch_type == "ctcss":
            ctcss_pwr = self._detect_ctcss(audio)
            return ctcss_pwr > self._squelch_threshold
        return True

    def _decimate(self, audio: np.ndarray) -> np.ndarray:
        ratio = self._sample_rate / self._audio_rate
        if ratio < 1:
            return audio
        decim = max(1, int(ratio))
        if decim > 1 and len(audio) >= decim + 10:
            audio = scipy_signal.decimate(audio, decim, ftype='iir', zero_phase=True)
        return audio

    @abstractmethod
    def demodulate(self, iq_samples: np.ndarray) -> Optional[np.ndarray]: ...

    def process(self, iq_samples: np.ndarray) -> Optional[np.ndarray]:
        audio = self.demodulate(iq_samples)
        if audio is None or len(audio) < 4:
            self._squelch_open = False
            return None
        audio = self._apply_noise_blanker(audio)
        audio = self._apply_filters(audio)
        audio = self._decimate(audio)
        audio = self._apply_agc(audio)
        self._ctcss_detected = self._detect_ctcss(audio)
        self._squelch_open = self._squelch_check(audio)
        if not self._squelch_open:
            return None
        if self._callback:
            self._callback(audio)
        return audio


class NFMDemodulator(Demodulator):
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_samples, dtype=np.complex64)
        angle = np.unwrap(np.angle(iq))
        diff = np.diff(angle)
        deviation = self._sample_rate / (2 * np.pi * 5000)
        audio = diff * deviation
        lp = scipy_signal.firwin(63, 3000, fs=self._sample_rate)
        if len(audio) > len(lp):
            audio = scipy_signal.convolve(audio, lp, mode='same')
        deemphasis = scipy_signal.lfilter([1], [1, -0.999], audio)
        return deemphasis.astype(np.float32)


class FMDemodulator(Demodulator):
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_samples, dtype=np.complex64)
        angle = np.unwrap(np.angle(iq))
        diff = np.diff(angle)
        deviation = self._sample_rate / (2 * np.pi * 75000)
        audio = diff * deviation
        lp = scipy_signal.firwin(63, 15000, fs=self._sample_rate)
        if len(audio) > len(lp):
            audio = scipy_signal.convolve(audio, lp, mode='same')
        deemphasis = scipy_signal.lfilter([1], [1, -0.9995], audio)
        return deemphasis.astype(np.float32)


class WFMDemodulator(Demodulator):
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_samples, dtype=np.complex64)
        angle = np.unwrap(np.angle(iq))
        diff = np.diff(angle)
        deviation = self._sample_rate / (2 * np.pi * 200000)
        audio = diff * deviation
        return audio.astype(np.float32)


class AMDemodulator(Demodulator):
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_samples, dtype=np.complex64)
        env = np.abs(iq)
        env = env - np.mean(env)
        lp = scipy_signal.firwin(63, 5000, fs=self._sample_rate)
        if len(env) > len(lp):
            env = scipy_signal.convolve(env, lp, mode='same')
        return env.astype(np.float32)


class USBDemodulator(Demodulator):
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_samples, dtype=np.complex64)
        fft = np.fft.fft(iq)
        n = len(fft)
        fft[:n // 2] = 0
        iq_usb = np.fft.ifft(fft)
        audio = np.abs(iq_usb)
        audio = audio - np.mean(audio)
        lp = scipy_signal.firwin(63, 3000, fs=self._sample_rate)
        if len(audio) > len(lp):
            audio = scipy_signal.convolve(audio, lp, mode='same')
        return audio.astype(np.float32)


class LSBDemodulator(Demodulator):
    def demodulate(self, iq_samples: np.ndarray) -> np.ndarray:
        iq = np.asarray(iq_samples, dtype=np.complex64)
        fft = np.fft.fft(iq)
        n = len(fft)
        fft[n // 2:] = 0
        iq_lsb = np.fft.ifft(fft)
        audio = np.abs(iq_lsb)
        audio = audio - np.mean(audio)
        lp = scipy_signal.firwin(63, 3000, fs=self._sample_rate)
        if len(audio) > len(lp):
            audio = scipy_signal.convolve(audio, lp, mode='same')
        return audio.astype(np.float32)


class DemodulatorFactory:
    _map = {
        "NFM": NFMDemodulator,
        "FM": FMDemodulator,
        "WFM": WFMDemodulator,
        "AM": AMDemodulator,
        "USB": USBDemodulator,
        "LSB": LSBDemodulator,
    }

    @classmethod
    def create(cls, mode: str) -> Demodulator:
        klass = cls._map.get(mode.upper())
        if not klass:
            raise ValueError(f"Neznámá modulace: {mode}")
        return klass()

    @classmethod
    def modes(cls) -> list[str]:
        return list(cls._map.keys())
