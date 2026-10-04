"""Authenticated envelopes for the optional macOS UDP compatibility relay."""
import base64
import hashlib
import hmac
import json


def encode(value, token):
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(token.encode(), content, hashlib.sha256).hexdigest()
    return json.dumps({"payload": value, "signature": signature}, separators=(",", ":")).encode()


def decode(data, token):
    if len(data) > 4096:
        raise ValueError("relay envelope too large")
    envelope = json.loads(data)
    payload = envelope["payload"]
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(token.encode(), content, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), str(envelope["signature"]).encode()):
        raise ValueError("relay signature invalid")
    return payload


def packet_encode(packet):
    return base64.b64encode(packet).decode("ascii")


def packet_decode(packet):
    return base64.b64decode(packet, validate=True)
