"""
Native ctypes wrapper for libairspy.so.0
Compatible API with the expected pyairspy interface.
"""
import ctypes
import threading
import time
import numpy as np

# Load the shared library
_lib = None

def _get_lib():
    global _lib
    if _lib is not None:
        return _lib
    try:
        _lib = ctypes.CDLL("libairspy.so.0")
    except OSError:
        raise ImportError("libairspy.so.0 not found. Install libairspy0 system package.")

    # Define function signatures
    _lib.airspy_init.argtypes = []
    _lib.airspy_init.restype = ctypes.c_int

    _lib.airspy_exit.argtypes = []
    _lib.airspy_exit.restype = ctypes.c_int

    _lib.airspy_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    _lib.airspy_open.restype = ctypes.c_int

    _lib.airspy_open_sn.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint64]
    _lib.airspy_open_sn.restype = ctypes.c_int

    _lib.airspy_close.argtypes = [ctypes.c_void_p]
    _lib.airspy_close.restype = ctypes.c_int

    _lib.airspy_get_samplerates.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32]
    _lib.airspy_get_samplerates.restype = ctypes.c_int

    _lib.airspy_set_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _lib.airspy_set_samplerate.restype = ctypes.c_int

    _lib.airspy_set_freq.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _lib.airspy_set_freq.restype = ctypes.c_int

    _lib.airspy_set_sample_type.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _lib.airspy_set_sample_type.restype = ctypes.c_int

    _lib.airspy_set_lna_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    _lib.airspy_set_lna_gain.restype = ctypes.c_int

    _lib.airspy_set_mixer_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    _lib.airspy_set_mixer_gain.restype = ctypes.c_int

    _lib.airspy_set_vga_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    _lib.airspy_set_vga_gain.restype = ctypes.c_int

    _lib.airspy_set_linearity_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    _lib.airspy_set_linearity_gain.restype = ctypes.c_int

    _lib.airspy_set_sensitivity_gain.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    _lib.airspy_set_sensitivity_gain.restype = ctypes.c_int

    _lib.airspy_set_rf_bias.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    _lib.airspy_set_rf_bias.restype = ctypes.c_int

    _lib.airspy_start_rx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    _lib.airspy_start_rx.restype = ctypes.c_int

    _lib.airspy_stop_rx.argtypes = [ctypes.c_void_p]
    _lib.airspy_stop_rx.restype = ctypes.c_int

    _lib.airspy_is_streaming.argtypes = [ctypes.c_void_p]
    _lib.airspy_is_streaming.restype = ctypes.c_int

    _lib.airspy_list_devices.argtypes = [ctypes.POINTER(ctypes.c_uint64), ctypes.c_int]
    _lib.airspy_list_devices.restype = ctypes.c_int

    _lib.airspy_board_id_read.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)]
    _lib.airspy_board_id_read.restype = ctypes.c_int

    _lib.airspy_version_string_read.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    _lib.airspy_version_string_read.restype = ctypes.c_int

    _lib.airspy_board_partid_serialno_read.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _lib.airspy_board_partid_serialno_read.restype = ctypes.c_int

    _lib.airspy_error_name.argtypes = [ctypes.c_int]
    _lib.airspy_error_name.restype = ctypes.c_char_p

    # Initialize library
    ret = _lib.airspy_init()
    if ret != 0:
        raise RuntimeError(f"airspy_init failed: {ret}")

    return _lib


class AirspyTransfer(ctypes.Structure):
    _fields_ = [
        ("device", ctypes.c_void_p),
        ("ctx", ctypes.c_void_p),
        ("samples", ctypes.c_void_p),
        ("sample_count", ctypes.c_int),
        ("sample_type", ctypes.c_int),
    ]


_AIRSPY_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(AirspyTransfer))


class Airspy:
    """Wrapper around a single Airspy device using ctypes."""

    SAMPLE_TYPE_FLOAT32_IQ = 0
    SAMPLE_TYPE_INT16_IQ = 1

    def __init__(self, device_index: int = 0):
        self._lib = _get_lib()
        self._dev = ctypes.c_void_p()
        self._index = device_index
        self._sample_rate = 10_000_000
        self._frequency = 100_000_000
        self._lna_gain = 0
        self._mixer_gain = 0
        self._vga_gain = 0
        self._running = False
        self._buffer = []
        self._lock = threading.Lock()
        self._cb_ref = None
        self._cb_thread = None

        devices = list_devices()
        if device_index >= len(devices):
            raise RuntimeError(f"Airspy device index {device_index} not found. Detected: {devices}")

        serial = devices[device_index]
        ret = self._lib.airspy_open_sn(ctypes.byref(self._dev), serial)
        if ret != 0:
            raise RuntimeError(f"airspy_open_sn failed: {ret} ({self._err(ret)})")

        # Set default sample type and rate
        self._set_sample_type(self.SAMPLE_TYPE_FLOAT32_IQ)
        self._set_sample_rate(self._sample_rate)

    def _err(self, code):
        return self._lib.airspy_error_name(code).decode("utf-8", errors="replace")

    def _set_sample_rate(self, rate):
        ret = self._lib.airspy_set_samplerate(self._dev, int(rate))
        if ret != 0:
            raise RuntimeError(f"airspy_set_samplerate failed: {ret} ({self._err(ret)})")

    def _set_sample_type(self, stype):
        ret = self._lib.airspy_set_sample_type(self._dev, stype)
        if ret != 0:
            raise RuntimeError(f"airspy_set_sample_type failed: {ret} ({self._err(ret)})")

    def close(self):
        self.stop_rx()
        if self._dev:
            self._lib.airspy_close(self._dev)
            self._dev = None

    def __del__(self):
        try:
            self.close()
        except:
            pass

    def _callback(self, transfer):
        t = transfer.contents
        count = t.sample_count
        if count <= 0:
            return 0
        # Float32 IQ: interleaved I/Q samples
        ptr = ctypes.cast(t.samples, ctypes.POINTER(ctypes.c_float))
        arr = np.ctypeslib.as_array(ptr, shape=(count,)).copy()
        iq = np.empty(count // 2, dtype=np.complex64)
        iq.real = arr[0::2]
        iq.imag = arr[1::2]
        with self._lock:
            self._buffer.append(iq)
        return 0

    def start_rx(self):
        if self._running:
            return
        self._buffer = []
        self._cb_ref = _AIRSPY_CALLBACK(self._callback)
        ret = self._lib.airspy_start_rx(self._dev, self._cb_ref, None)
        if ret != 0:
            raise RuntimeError(f"airspy_start_rx failed: {ret} ({self._err(ret)})")
        self._running = True

    def stop_rx(self):
        if self._running and self._dev:
            self._lib.airspy_stop_rx(self._dev)
            self._running = False
            self._cb_ref = None

    def read_samples(self, num_samples):
        """Collect num_samples complex samples from the streaming buffer."""
        if not self._running:
            self.start_rx()

        result = np.empty(0, dtype=np.complex64)
        timeout = time.time() + 3.0
        while len(result) < num_samples and time.time() < timeout:
            with self._lock:
                while self._buffer and len(result) < num_samples:
                    chunk = self._buffer.pop(0)
                    needed = num_samples - len(result)
                    if len(chunk) <= needed:
                        result = np.concatenate((result, chunk))
                    else:
                        result = np.concatenate((result, chunk[:needed]))
                        self._buffer.insert(0, chunk[needed:])
            if len(result) < num_samples:
                time.sleep(0.005)
        return result[:num_samples]

    # -- Properties compatible with device_manager expectations --

    @property
    def sample_rate(self):
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, value):
        self._sample_rate = int(value)
        if self._dev:
            self._set_sample_rate(self._sample_rate)

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, value):
        self._frequency = int(value)
        if self._dev:
            ret = self._lib.airspy_set_freq(self._dev, self._frequency)
            if ret != 0:
                print(f"[Airspy] set_freq failed: {ret}")

    @property
    def lna_gain(self):
        return self._lna_gain

    @lna_gain.setter
    def lna_gain(self, value):
        self._lna_gain = int(value)
        if self._dev:
            self._lib.airspy_set_lna_gain(self._dev, self._lna_gain)

    @property
    def mixer_gain(self):
        return self._mixer_gain

    @mixer_gain.setter
    def mixer_gain(self, value):
        self._mixer_gain = int(value)
        if self._dev:
            self._lib.airspy_set_mixer_gain(self._dev, self._mixer_gain)

    @property
    def vga_gain(self):
        return self._vga_gain

    @vga_gain.setter
    def vga_gain(self, value):
        self._vga_gain = int(value)
        if self._dev:
            self._lib.airspy_set_vga_gain(self._dev, self._vga_gain)

    def set_gain(self, gain):
        """Set overall linearity gain (0-21)."""
        if self._dev:
            self._lib.airspy_set_linearity_gain(self._dev, int(gain))

    def set_rf_bias(self, enabled):
        if self._dev:
            self._lib.airspy_set_rf_bias(self._dev, 1 if enabled else 0)

    def get_board_id(self):
        if not self._dev:
            return None
        bid = ctypes.c_uint8()
        ret = self._lib.airspy_board_id_read(self._dev, ctypes.byref(bid))
        if ret == 0:
            return bid.value
        return None

    def get_version_string(self):
        if not self._dev:
            return ""
        buf = ctypes.create_string_buffer(128)
        ret = self._lib.airspy_version_string_read(self._dev, buf, 128)
        if ret == 0:
            return buf.value.decode("utf-8", errors="replace")
        return ""

    def get_serial_number(self):
        if not self._dev:
            return 0
        part_id = (ctypes.c_uint32 * 2)()
        serial_msb = ctypes.c_uint32()
        serial_lsb = ctypes.c_uint32()
        ret = self._lib.airspy_board_partid_serialno_read(
            self._dev,
            part_id,
            ctypes.byref(serial_msb),
            ctypes.byref(serial_lsb),
        )
        if ret == 0:
            return (serial_msb.value << 32) | serial_lsb.value
        return 0


def list_devices():
    """Return a list of serial numbers for detected Airspy devices."""
    lib = _get_lib()
    count = lib.airspy_list_devices(None, 0)
    if count <= 0:
        return []
    serials = (ctypes.c_uint64 * count)()
    lib.airspy_list_devices(serials, count)
    return list(serials)
