import struct

import pytest

import exceptions
from protocol.parser import parse

_HEADER_FMT = "<BBB BB H B"


def _make_packet(msg_type, sender, receiver, seq, payload=b""):
    payload_and_crc_len = len(payload) + 1
    header = struct.pack(
        _HEADER_FMT,
        msg_type,
        sender[0],
        sender[1],
        receiver[0],
        receiver[1],
        seq,
        payload_and_crc_len,
    )
    from protocol.crc import calculate_crc8

    crc = calculate_crc8(header, payload)
    return header + payload + bytes([crc])


class TestParseRaises:
    def test_payload_too_short(self):
        with pytest.raises(exceptions.ProtocolError, match="too short"):
            parse(b"\x01\x02")

    def test_unknown_message_type(self):
        raw = _make_packet(0xFF, (0, 1), (0, 2), 1)
        with pytest.raises(exceptions.ProtocolError, match="Unknown message type"):
            parse(raw)

    def test_payload_too_short_for_declared_length(self):
        header = struct.pack(_HEADER_FMT, 0x1, 0, 1, 0, 2, 1, 10)
        with pytest.raises(exceptions.ProtocolError, match="too short for declared length"):
            parse(header + b"\x00")
