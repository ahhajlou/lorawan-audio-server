import struct

from protocol.crc import calculate_crc8
from protocol.models import MsgType, Packet

_HEADER_FMT = "<BBB BB H B"

_ACK_TYPE_MAP = {
    MsgType.DATA: MsgType.ACK,
    MsgType.DATA_SEQ: MsgType.ACK_SEQ,
    MsgType.DATA_LAST: MsgType.ACK_LAST,
}


def _pack_header(msg_type, sender, receiver, seq, payload_and_crc_len):
    return struct.pack(
        _HEADER_FMT,
        msg_type,
        sender.addh,
        sender.addl,
        receiver.addh,
        receiver.addl,
        seq,
        payload_and_crc_len,
    )


def build_ack(packet: Packet) -> bytes:
    ack_type = _ACK_TYPE_MAP.get(packet.msg_type)
    if ack_type is None:
        raise ValueError(f"Cannot build ACK for message type: {packet.msg_type}")

    header = _pack_header(
        ack_type,
        packet.receiver,
        packet.sender,
        packet.seq,
        1,
    )
    crc = calculate_crc8(header, b"")
    return header + struct.pack("B", crc)


def build_downlink(packet: Packet) -> bytes:
    payload_len = len(packet.payload)
    header = _pack_header(
        packet.msg_type,
        packet.sender,
        packet.receiver,
        packet.seq,
        payload_len + 1,
    )
    crc = calculate_crc8(header, packet.payload)
    return header + packet.payload + struct.pack("B", crc)
