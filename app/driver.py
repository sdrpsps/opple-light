import logging
import socket
import time
from dataclasses import dataclass
from pyoppleio import Message, const
from pyoppleio.OppleLightDevice import OppleLightDevice

log = logging.getLogger(__name__)


class DeviceUnavailable(Exception):
    pass


@dataclass
class Reading:
    power: bool
    brightness_percent: int
    color_temperature_kelvin: int


class BoundedOppleDevice(OppleLightDevice):
    """Keep the upstream protocol, bound receive loops and validate reply origin."""
    def send(self, message_type, data=None, reply=False):
        message = Message.build_message(const.MESSAGE_TYPE[message_type], data, self)
        self.socket.sendto(message.data, (self.ip, self.port))
        if not reply:
            return None
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                self.socket.settimeout(max(0.01, deadline - time.monotonic()))
                data, address = self.socket.recvfrom(1024)
                if address[0] != self.ip:
                    continue
                if len(data) < 124:
                    continue
                incoming = Message.parse_message(data, self)
                if message.get_request_sn() != incoming.get_response_sn():
                    continue
                self.is_online = True
                return incoming
            except socket.timeout:
                break
            except (ValueError, KeyError, TypeError, IndexError, OverflowError):
                continue
        self.is_online = False
        return None


class OppleDriver:
    """All methods are run on ONE dedicated executor thread per device."""
    def __init__(self, host):
        self.host = str(host)
        self.device = None

    def close(self):
        if self.device:
            self.device.socket.close()
            self.device = None

    def read(self):
        try:
            if self.device is None:
                self.device = BoundedOppleDevice(self.host)
            else:
                self.device.update()
            if not self.device.is_init or not self.device.is_online:
                raise DeviceUnavailable("灯具未响应，请检查供电、IP 地址和局域网连接")
            return Reading(bool(self.device.power_on), round(self.device.brightness * 100 / 255), self.device.color_temperature)
        except Exception as exc:
            self.close()
            if isinstance(exc, DeviceUnavailable):
                raise
            log.warning("OPPLE read failed: %s", type(exc).__name__)
            raise DeviceUnavailable("无法读取灯具状态，请检查设备连接") from exc

    def write(self, target):
        try:
            if self.device is None:
                self.read()
            # Only explicit power=true turns on a lamp; callers handle staged settings.
            if "power" in target:
                self.device.power_on = target["power"]
            if "brightness_percent" in target:
                self.device.brightness = max(1, round(target["brightness_percent"] * 255 / 100))
            if "color_temperature_kelvin" in target:
                self.device.color_temperature = target["color_temperature_kelvin"]
            observed = self.read()
            for key, expected in target.items():
                actual = getattr(observed, key)
                tolerance = 50 if key == "color_temperature_kelvin" else 1 if key == "brightness_percent" else 0
                if abs(actual - expected) > tolerance:
                    raise DeviceUnavailable("灯具未确认目标设置，已保留实际回读状态")
            return observed
        except Exception as exc:
            if isinstance(exc, DeviceUnavailable):
                raise
            self.close()
            raise DeviceUnavailable("灯具控制失败，请刷新状态后重试") from exc


class DemoDriver:
    """Isolated simulator. Never constructs a socket or touches a real device."""
    def __init__(self, config):
        self.state = Reading(True, config.default_brightness, config.default_kelvin)
        self.online = True

    def read(self):
        if not self.online:
            raise DeviceUnavailable("演示灯具离线")
        return Reading(**vars(self.state))

    def write(self, target):
        self.read()
        time.sleep(0.05)
        for key, value in target.items():
            setattr(self.state, key, value)
        return self.read()

    def close(self):
        pass
