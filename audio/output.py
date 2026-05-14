import numpy as np
import threading
from typing import Optional
from collections import deque
from scipy import signal as scipy_signal


class AudioFilter:
    def __init__(self, rate: float = 48000.0):
        self._rate = rate
        self._notch_freq = 0.0
        self._notch_b = None
        self._notch_a = None
        self._zi = None

    def set_notch(self, freq_hz: float, q: float = 30.0):
        self._notch_freq = freq_hz
        if freq_hz > 0 and freq_hz < self._rate / 2:
            w0 = freq_hz / (self._rate / 2)
            self._notch_b, self._notch_a = scipy_signal.iirnotch(w0, q)
            self._zi = scipy_signal.lfilter_zi(self._notch_b, self._notch_a) * 0
        else:
            self._notch_b = None

    def apply(self, audio: np.ndarray) -> np.ndarray:
        if self._notch_b is not None and len(audio) > 3:
            if self._zi is not None:
                out, self._zi = scipy_signal.lfilter(self._notch_b, self._notch_a, audio, zi=self._zi)
                return out
            else:
                return scipy_signal.lfilter(self._notch_b, self._notch_a, audio)
        return audio


class AudioAGC:
    def __init__(self, rate: float = 48000.0):
        self._rate = rate
        self._gain = 0.5
        self._attack = 0.02
        self._decay = 0.002
        self._target_rms = 0.12
        self._max_gain = 50.0
        self._min_gain = 0.01
        self._smooth = 0.7

    def process(self, audio: np.ndarray) -> np.ndarray:
        if len(audio) < 4:
            return audio
        rms = np.sqrt(np.mean(audio ** 2)) + 1e-10
        target = self._target_rms / rms
        if target > self._gain:
            self._gain += self._attack * (target - self._gain)
        else:
            self._gain += self._decay * (target - self._gain)
        self._gain = np.clip(self._gain, self._min_gain, self._max_gain)
        return np.clip(audio * self._gain, -1.0, 1.0)


class AudioEngine:
    def __init__(self, sample_rate: float = 48000.0):
        self._sr = sample_rate
        self._stream: Optional = None
        self._volume: float = 0.8
        self._muted: bool = False
        self._buffer: deque = deque(maxlen=60)
        self._lock = threading.Lock()
        self._running = False
        self._filter = AudioFilter(sample_rate)
        self._agc = AudioAGC(sample_rate)
        self._last_level: float = 0.0

    def open(self) -> bool:
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=int(self._sr),
                channels=1,
                callback=self._callback,
                blocksize=512,
                latency='low',
            )
            self._stream.start()
            self._running = True
            return True
        except Exception as e:
            print(f"Audio open error: {e}")
            return False

    def close(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except:
                pass
            self._stream = None
        with self._lock:
            self._buffer.clear()

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if self._muted or not self._buffer:
                outdata[:] = 0
                return
            try:
                data = self._buffer.popleft()
                needed = len(outdata)
                if len(data) < needed:
                    outdata[:len(data)] = data.reshape(-1, 1) * self._volume
                    outdata[len(data):] = 0
                else:
                    outdata[:] = data[:needed].reshape(-1, 1) * self._volume
                    if len(data) > needed:
                        self._buffer.appendleft(data[needed:])
            except IndexError:
                outdata[:] = 0

    def push_audio(self, samples: np.ndarray):
        with self._lock:
            if self._running:
                processed = self._filter.apply(samples)
                processed = self._agc.process(processed)
                self._buffer.append(processed)
                self._last_level = float(np.sqrt(np.mean(processed ** 2)))

    @property
    def audio_level(self) -> float:
        return self._last_level

    def set_notch(self, freq_hz: float):
        self._filter.set_notch(freq_hz)

    def set_volume(self, vol: float):
        self._volume = max(0.0, min(1.0, vol))

    def set_muted(self, muted: bool):
        self._muted = muted

    def set_agc(self, enabled: bool):
        pass

    @property
    def is_open(self) -> bool:
        return self._stream is not None and self._running


class AudioRecorder:
    def __init__(self, output_dir: str = "recordings"):
        self._dir = output_dir
        self._recording = False
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._rec_start_time = 0.0
        self._max_duration = 3600
        self._freq_hz: float = 0.0
        self._mode: str = ""
        import os as _os
        _os.makedirs(self._dir, exist_ok=True)

    def start_recording(self, freq_hz: float = 0.0, mode: str = ""):
        with self._lock:
            self._buffer.clear()
            self._recording = True
            self._rec_start_time = __import__('time').time()
            self._freq_hz = freq_hz
            self._mode = mode

    def stop_recording(self) -> Optional[str]:
        import os, time, wave
        with self._lock:
            if not self._recording or not self._buffer:
                self._recording = False
                return None
            self._recording = False
            data = np.concatenate(self._buffer)
            self._buffer.clear()
        freq_str = f"{self._freq_hz / 1e6:.3f}MHz" if self._freq_hz else "unknown"
        mod_str = f"_{self._mode}" if self._mode else ""
        ts = int(time.time())
        fname = os.path.join(self._dir, f"rec_{ts}_{freq_str}{mod_str}.wav")
        data = np.clip(data * 32767, -32768, 32767).astype(np.int16)
        try:
            with wave.open(fname, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(data.tobytes())
            return fname
        except:
            return None

    def push_audio(self, samples: np.ndarray):
        with self._lock:
            if self._recording:
                self._buffer.append(samples.copy())
                if len(self._buffer) > self._max_duration * 50:
                    self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def get_duration(self) -> float:
        with self._lock:
            return len(self._buffer) * 0.02
