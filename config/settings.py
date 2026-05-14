import json, os
from dataclasses import dataclass, field, asdict

CONFIG_PATH = os.path.expanduser("~/.sdrtrunk_config.json")

BAND_PLANS = {
    "LW":  {"name": "Longwave",        "lo": 0.030e6, "hi": 0.300e6, "step": 9e3,    "mod": "AM"},
    "MW":  {"name": "Mediumwave",      "lo": 0.530e6, "hi": 1.710e6, "step": 10e3,   "mod": "AM"},
    "SW":  {"name": "Shortwave",       "lo": 1.800e6, "hi": 30.000e6,"step": 5e3,    "mod": "AM"},
    "160m":{"name": "160m",            "lo": 1.800e6, "hi": 2.000e6, "step": 1e3,    "mod": "LSB"},
    "80m": {"name": "80m",             "lo": 3.500e6, "hi": 4.000e6, "step": 1e3,    "mod": "LSB"},
    "40m": {"name": "40m",             "lo": 7.000e6, "hi": 7.300e6, "step": 1e3,    "mod": "LSB"},
    "30m": {"name": "30m",             "lo": 10.100e6,"hi": 10.150e6,"step": 1e3,    "mod": "USB"},
    "20m": {"name": "20m",             "lo": 14.000e6,"hi": 14.350e6,"step": 1e3,    "mod": "USB"},
    "17m": {"name": "17m",             "lo": 18.068e6,"hi": 18.168e6,"step": 1e3,    "mod": "USB"},
    "15m": {"name": "15m",             "lo": 21.000e6,"hi": 21.450e6,"step": 1e3,    "mod": "USB"},
    "12m": {"name": "12m",             "lo": 24.890e6,"hi": 24.990e6,"step": 1e3,    "mod": "USB"},
    "10m": {"name": "10m",             "lo": 28.000e6,"hi": 29.700e6,"step": 1e3,    "mod": "USB"},
    "6m":  {"name": "6m",              "lo": 50.000e6,"hi": 54.000e6, "step": 5e3,    "mod": "NFM"},
    "2m":  {"name": "2m",              "lo": 144.000e6,"hi": 148.000e6,"step": 12.5e3,"mod": "NFM"},
    "1.25m":{"name": "1.25m",          "lo": 222.000e6,"hi": 225.000e6,"step": 12.5e3,"mod": "NFM"},
    "70cm":{"name": "70cm",            "lo": 420.000e6,"hi": 450.000e6,"step": 25e3,   "mod": "NFM"},
    "33cm":{"name": "33cm",            "lo": 902.000e6,"hi": 928.000e6,"step": 25e3,   "mod": "NFM"},
    "23cm":{"name": "23cm",            "lo": 1240.000e6,"hi": 1300.000e6,"step": 25e3,  "mod": "NFM"},
}

CTCSS_TONES = [67.0, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5, 94.8,
               97.4, 100.0, 103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3,
               131.8, 136.5, 141.3, 146.2, 151.4, 156.7, 162.2, 167.9, 173.8,
               179.9, 186.2, 192.8, 199.5, 206.5, 218.1, 225.7, 233.6, 241.8, 250.3]

CZ_REPEATERS = [
    {"name": "OK0B",  "freq": 145.600e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Praha"},
    {"name": "OK0K",  "freq": 145.650e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Brno"},
    {"name": "OK0P",  "freq": 145.700e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Plzeň"},
    {"name": "OK0BD", "freq": 439.000e6, "offset": -7.6e6, "ctcss": 88.5, "city": "Praha"},
    {"name": "OK0BS", "freq": 439.200e6, "offset": -7.6e6, "ctcss": 88.5, "city": "Brno"},
    {"name": "OK0O",  "freq": 439.350e6, "offset": -7.6e6, "ctcss": 88.5, "city": "Ostrava"},
    {"name": "OK0AE", "freq": 145.625e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Č.Budějovice"},
    {"name": "OK0H",  "freq": 145.675e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Hradec Králové"},
    {"name": "OK0U",  "freq": 145.725e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Ústí n.L."},
    {"name": "OK0J",  "freq": 439.100e6, "offset": -7.6e6, "ctcss": 88.5, "city": "Jihlava"},
    {"name": "OK0G",  "freq": 439.250e6, "offset": -7.6e6, "ctcss": 88.5, "city": "Liberec"},
    {"name": "OK0Z",  "freq": 439.400e6, "offset": -7.6e6, "ctcss": 88.5, "city": "Zlín"},
    {"name": "OK0V",  "freq": 145.750e6, "offset": -0.6e6, "ctcss": 88.5, "city": "Vysočina"},
]

SIMPAX = [
    {"name": "Praha Ch1",   "freq": 145.575e6, "ctcss": 88.5, "desc": "OK1KHL"},
    {"name": "Brno Ch1",    "freq": 145.700e6, "ctcss": 88.5, "desc": "OK2KOJ"},
    {"name": "Plzeň Ch1",   "freq": 145.600e6, "ctcss": 88.5, "desc": "OK1PKL"},
    {"name": "UHF Praha",   "freq": 438.625e6, "ctcss": 88.5, "desc": "OK1KHL"},
    {"name": "UHF Brno",    "freq": 438.750e6, "ctcss": 88.5, "desc": "OK2KOJ"},
    {"name": "UHF Ostrava", "freq": 438.800e6, "ctcss": 88.5, "desc": "OK2KLD"},
]


@dataclass
class SDRConfig:
    device_type: str = "rtlsdr"
    sample_rate: float = 2.4e6
    center_freq: float = 145.500e6
    gain: int = 30
    if_gain: int = 20
    bb_gain: int = 20
    ppm_error: int = 0
    bias_t: bool = False
    direct_sampling: bool = False

@dataclass
class AudioConfig:
    device_index: int = -1
    sample_rate: float = 48000.0
    volume: float = 0.8
    notch_freq: float = 0.0
    agc_enabled: bool = True

@dataclass
class ScannerConfig:
    hold_time_ms: int = 3000
    hang_time_ms: int = 2000
    threshold_db: float = -40.0
    priority_interval: int = 3
    search_mode: bool = False

@dataclass  
class DisplayConfig:
    theme: str = "dark"
    spectrum_min_db: int = -80
    spectrum_max_db: int = 0
    waterfall_history: int = 512
    show_grid: bool = True
    show_band_plan: bool = True

@dataclass
class Settings:
    sdr: SDRConfig = field(default_factory=SDRConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    favorites: list = field(default_factory=list)
    trunk_systems: list = field(default_factory=list)
    banks: dict = field(default_factory=lambda: {"Default": []})
    last_freq: float = 145.500e6
    last_band: str = "2m"
    last_modulation: str = "NFM"
    window_geometry: list = field(default_factory=lambda: [100, 100, 1200, 800])

    def save(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)

    @classmethod
    def load(cls):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                s = cls()
                for k, v in data.items():
                    if hasattr(s, k):
                        existing = getattr(s, k)
                        if isinstance(existing, (SDRConfig, AudioConfig, ScannerConfig, DisplayConfig)):
                            for sk, sv in v.items():
                                if hasattr(existing, sk):
                                    setattr(existing, sk, sv)
                        else:
                            setattr(s, k, v)
                return s
            except:
                pass
        return cls()
