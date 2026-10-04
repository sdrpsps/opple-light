#!/usr/bin/env python3
"""Optional macOS LAN relay. Python stdlib only. No UI, scenes or scheduling.

Run on the physical LAN host when its VM NAT cannot receive OPPLE UDP replies.
All forwarded requests are HMAC authenticated and restricted to allowed IPs.
"""
import argparse
import ipaddress
import logging
import socket
import time
from pathlib import Path
from app.relay_protocol import decode, encode, packet_decode, packet_encode

log = logging.getLogger("opple-relay")
MESSAGE_TYPES = {0x2010000, 0x30f0000, 0x3110000, 0x3130000, 0x31b0000}


def serve(bind, port, token, allowed, stop=None, ready=None):
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind((bind, port))
    listener.settimeout(.5)
    nonces = {}
    if ready:
        ready(listener.getsockname()[1])
    log.info("本地 UDP 转发已启动，监听 %s:%s；允许的灯具：%s", bind, port, ", ".join(sorted(allowed)))
    try:
        while stop is None or not stop.is_set():
            try:
                data, client = listener.recvfrom(4097)
            except socket.timeout:
                continue
            try:
                request = decode(data, token)
                target = str(ipaddress.IPv4Address(request["target"]))
                destination_port = int(request["port"])
                nonce = request["nonce"]
                if target not in allowed or not 1024 <= destination_port <= 65535:
                    raise ValueError("target not allowed")
                if not isinstance(nonce, str) or len(nonce) != 32 or nonce in nonces:
                    raise ValueError("invalid or replayed nonce")
                if request.get("reply") not in (True, False):
                    raise ValueError("invalid reply flag")
                packet = bytearray(packet_decode(request["packet"]))
                if not 124 <= len(packet) <= 256 or int.from_bytes(packet[0x74:0x78], "big") not in MESSAGE_TYPES:
                    raise ValueError("invalid OPPLE packet")
                now = time.monotonic()
                nonces = {key: at for key, at in nonces.items() if now-at < 60}
                if len(nonces) >= 2000:
                    raise ValueError("relay request limit")
                nonces[nonce] = now
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as lan:
                    lan.bind(("0.0.0.0", 0))
                    # OPPLE carries the receiving client's port in DEST_PORT.
                    # This field is outside the encrypted body and message CRC.
                    packet[0x0C:0x10] = lan.getsockname()[1].to_bytes(4, "big")
                    lan.sendto(packet, (target, destination_port))
                    if request["reply"]:
                        deadline = time.monotonic() + 1.5
                        while time.monotonic() < deadline:
                            lan.settimeout(max(.01, deadline-time.monotonic()))
                            try:
                                reply, source = lan.recvfrom(1024)
                            except socket.timeout:
                                break
                            if source[0] != target or len(reply) < 124 or reply[0x68:0x6C] != packet[0x64:0x68]:
                                continue
                            response = {"nonce":nonce,"packet":packet_encode(reply)}
                            listener.sendto(encode(response,token),client)
                            break
            except (ValueError, KeyError, TypeError, OSError) as exc:
                log.debug("忽略无效转发请求：%s", type(exc).__name__)
    finally:
        listener.close()


def main():
    parser = argparse.ArgumentParser(description="欧普灯 macOS 本地 UDP 兼容转发")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=55090)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--allow", action="append", required=True, help="允许控制的灯具 IPv4；可重复")
    args = parser.parse_args()
    token = Path(args.token_file).read_text().strip()
    if len(token) < 20:
        parser.error("转发口令至少需要 20 个字符")
    allowed = {str(ipaddress.IPv4Address(value)) for value in args.allow}
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    serve(args.bind, args.port, token, allowed)


if __name__ == "__main__":
    main()
