import threading, time
from typing import Optional, Callable
from dataclasses import dataclass, field


P25_BAND_PLANS = [
    {"base": 851006250, "offset": 440, "step": 12500, "spacing": 12500},
    {"base": 762006250, "offset": 0, "step": 12500, "spacing": 12500},
    {"base": 1365000000, "offset": 0, "step": 12500, "spacing": 12500},
]


@dataclass
class TrunkChannel:
    frequency: float
    label: str = ""
    usage: str = "control"
    color_code: int = 0
    nac: int = 0

@dataclass
class TrunkCall:
    freq: float
    talkgroup: int = 0
    source: int = 0
    time: float = 0.0
    duration: float = 0.0
    encrypted: bool = False
    emergency: bool = False

@dataclass
class TrunkSystem:
    name: str
    system_type: str
    control_channels: list = field(default_factory=list)
    voice_channels: list = field(default_factory=list)
    band_plan: int = 0
    current_voice: Optional[float] = None
    active_calls: list[TrunkCall] = field(default_factory=list)
    wacn: int = 0
    sys_id: int = 0
    rfss: int = 0
    site_id: int = 0


class TrunkManager:
    def __init__(self):
        self._systems: dict[str, TrunkSystem] = {}
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []

    def add_system(self, system: TrunkSystem):
        with self._lock:
            self._systems[system.name] = system

    def remove_system(self, name: str):
        with self._lock:
            self._systems.pop(name, None)

    def add_listener(self, cb: Callable):
        self._listeners.append(cb)

    def notify(self, event: str, data: dict):
        for cb in self._listeners:
            try:
                cb(event, data)
            except:
                pass

    def process_control_data(self, system_name: str, metadata: dict):
        with self._lock:
            sys = self._systems.get(system_name)
            if not sys:
                return
            if "voice_channel" in metadata:
                freq = metadata["voice_channel"]
                sys.current_voice = freq
                call = TrunkCall(
                    freq=freq,
                    talkgroup=metadata.get("talkgroup", 0),
                    source=metadata.get("source", 0),
                    time=time.time(),
                )
                sys.active_calls.append(call)
                self.notify("voice_grant", {"system": system_name, "freq": freq, **metadata})

    def get_system(self, name: str) -> Optional[TrunkSystem]:
        with self._lock:
            return self._systems.get(name)

    @property
    def systems(self) -> dict:
        with self._lock:
            return dict(self._systems)


class TrunkProtocolDecoder:
    def __init__(self, system: TrunkSystem):
        self.system = system

    def p25_freq_from_channel(self, ch_id: int) -> float:
        plan = P25_BAND_PLANS[self.system.band_plan] if self.system.band_plan < len(P25_BAND_PLANS) else P25_BAND_PLANS[0]
        return plan["base"] + (ch_id - plan["offset"]) * plan["step"]

    def parse_p25_osw(self, data: bytes) -> Optional[dict]:
        if len(data) < 8:
            return None
        nac = ((data[0] << 4) | (data[1] >> 4)) & 0xFFF
        duid = data[2] >> 4
        result = {"nac": nac, "duid": duid, "raw": data.hex()}
        if duid == 0:
            result["type"] = "idle"
        elif duid == 3:
            ch1 = ((data[3] & 0x3F) << 16) | (data[4] << 8) | data[5]
            ch2 = ((data[6] & 0x3F) << 16) | (data[7] << 8) | data[8] if len(data) > 8 else 0
            freq = self.p25_freq_from_channel(ch1) if ch1 else 0
            result["type"] = "voice_channel"
            result["voice_channel"] = freq
            result["channel_id"] = ch1
        elif duid == 7:
            result["type"] = "data"
        elif duid == 12:
            result["type"] = "trunk_signal"
            result["talkgroup"] = ((data[3] & 0x3F) << 8) | data[4]
            result["source"] = (data[5] << 8) | data[6]
        return result

    def parse_dmr_bs(self, data: bytes) -> Optional[dict]:
        if len(data) < 3:
            return None
        cc = data[0] & 0x0F
        result = {"color_code": cc, "type": "dmr_bs"}
        if len(data) > 4:
            result["site"] = data[4]
        if len(data) > 8:
            result["payload"] = data.hex()
        return result
