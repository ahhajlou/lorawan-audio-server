import struct

import exceptions
from protocol.crc import verify_crc8
from protocol.models import Address, MsgType, Packet

_HEADER_FMT = "<BBB BB H B"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


def parse(decoded_payload: bytes) -> Packet:
    if len(decoded_payload) < _HEADER_SIZE:
        raise exceptions.ProtocolError(
            f"Payload too short: {len(decoded_payload)} bytes < {_HEADER_SIZE} header"
        )

    (
        msg_type_val,
        sender_addh,
        sender_addl,
        receiver_addh,
        receiver_addl,
        seq,
        payload_and_crc_len,
    ) = struct.unpack(_HEADER_FMT, decoded_payload[:_HEADER_SIZE])

    try:
        msg_type = MsgType(msg_type_val)
    except ValueError as err:
        raise exceptions.ProtocolError(f"Unknown message type: 0x{msg_type_val:02x}") from err

    if payload_and_crc_len <= 0:
        raise exceptions.ProtocolError("payload_and_crc_len <= 0")

    payload_end = _HEADER_SIZE + payload_and_crc_len
    if payload_end > len(decoded_payload):
        raise exceptions.ProtocolError(
            f"Payload too short for declared length: need {payload_end}, got {len(decoded_payload)}"
        )

    payload_and_crc = decoded_payload[_HEADER_SIZE:payload_end]
    header_bytes = decoded_payload[:_HEADER_SIZE]
    crc_valid = verify_crc8(header_bytes, payload_and_crc)

    payload = payload_and_crc[:-1] if payload_and_crc_len > 0 else b""

    return Packet(
        msg_type=msg_type,
        sender=Address(addh=sender_addh, addl=sender_addl),
        receiver=Address(addh=receiver_addh, addl=receiver_addl),
        seq=seq,
        payload=payload,
        crc_valid=crc_valid,
    )
