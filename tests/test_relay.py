import socket
import threading
from types import SimpleNamespace
import pytest
from pyoppleio import Message, const
from app.driver import OppleDriver
from app.relay_protocol import encode, decode
from udp_relay import serve


def test_relay_hmac_rejects_tampering():
    token = "test-token-at-least-twenty-characters"
    encoded = encode({"target":"127.0.0.1","port":55001}, token)
    assert decode(encoded, token)["port"] == 55001
    with pytest.raises(ValueError):
        decode(encoded.replace(b"55001", b"55002"), token)
    with pytest.raises(ValueError):
        decode(encoded, "different-token")


def test_real_protocol_reads_and_writes_through_authenticated_relay(monkeypatch):
    """Exercise actual OPPLE encryption and driver setters against a UDP lamp emulator."""
    token = "test-token-at-least-twenty-characters"
    stop = threading.Event()
    lamp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lamp_socket.bind(("127.0.0.1",0))
    lamp_socket.settimeout(.1)
    lamp_port = lamp_socket.getsockname()[1]
    monkeypatch.setattr(const, "BROADCAST_PORT", lamp_port)
    state = dict(power=True, brightness=128, kelvin=4500)
    commands = []
    device = SimpleNamespace(is_init=True, mac_raw=bytes.fromhex("80a0360249ec"), id=1234, server_port=lamp_port)

    def emulator():
        while not stop.is_set():
            try:
                raw, peer = lamp_socket.recvfrom(1024)
            except socket.timeout:
                continue
            kind = int.from_bytes(raw[0x74:0x78], "big")
            request = Message.parse_message(raw, None if kind == const.MESSAGE_TYPE["SEARCH"] else device)
            commands.append(kind)
            if kind == const.MESSAGE_TYPE["SEARCH"]:
                body = bytearray(53)
                body[9:15] = device.mac_raw
                body[19:23] = device.id.to_bytes(4,"big")
                body[27:31] = (2831).to_bytes(4,"big")
                body[31:35] = socket.inet_aton("127.0.0.1")
                body[35:37] = lamp_port.to_bytes(2,"big")
                body[37:51] = b"emulator".ljust(14,b"\x00")
                response = Message.build_message(kind, body)
            elif kind == const.MESSAGE_TYPE["QUERY"]:
                body = bytearray(9)
                body[1] = int(state["power"])
                body[2] = state["brightness"]
                body[7:9] = state["kelvin"].to_bytes(2,"big")
                response = Message.build_message(kind, body, device)
            else:
                value = request.get(0, 2 if kind == const.MESSAGE_TYPE["COLOR_TEMP"] else 1, int)
                if kind == const.MESSAGE_TYPE["POWER_ON"]: state["power"] = bool(value)
                elif kind == const.MESSAGE_TYPE["BRIGHTNESS"]: state["brightness"] = value
                elif kind == const.MESSAGE_TYPE["COLOR_TEMP"]: state["kelvin"] = value
                continue
            response.set(int.from_bytes(request.get_request_sn(),"big"), const.MESSAGE_OFFSET["RES_SERIAL_NUM"], header=True)
            # The driver only checks protocol serial, just as the physical device API.
            encoded_port = int.from_bytes(raw[0x0C:0x10],"big")
            lamp_socket.sendto(response.data,(peer[0],encoded_port or peer[1]))

    lamp_thread = threading.Thread(target=emulator, daemon=True)
    lamp_thread.start()
    relay_ready = threading.Event()
    relay_ports = []
    def ready(port):
        relay_ports.append(port); relay_ready.set()
    relay_thread = threading.Thread(target=serve,args=("127.0.0.1",0,token,{"127.0.0.1"},stop,ready),daemon=True)
    relay_thread.start()
    assert relay_ready.wait(2)
    monkeypatch.setenv("OPPLE_UDP_RELAY",f"127.0.0.1:{relay_ports[0]}")
    monkeypatch.setenv("OPPLE_RELAY_TOKEN",token)
    driver = OppleDriver("127.0.0.1")
    try:
        reading = driver.read()
        assert reading.power and reading.brightness_percent == 50 and reading.color_temperature_kelvin == 4500
        reading = driver.write({"power":False,"color_temperature_kelvin":3200,"brightness_percent":23})
        assert not reading.power and reading.color_temperature_kelvin == 3200 and reading.brightness_percent == 23
        assert const.MESSAGE_TYPE["POWER_ON"] in commands
        assert const.MESSAGE_TYPE["COLOR_TEMP"] in commands
        assert const.MESSAGE_TYPE["BRIGHTNESS"] in commands
    finally:
        driver.close(); stop.set(); relay_thread.join(2); lamp_thread.join(2); lamp_socket.close()
