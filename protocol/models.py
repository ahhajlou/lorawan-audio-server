from enum import IntEnum
from dataclasses import dataclass


@dataclass(frozen=True)
class Address:
    addh: int
    addl: int


class MsgType(IntEnum):
    DATA = 0x1
    ACK = 0x2
    DATA_SEQ = 0x3
    ACK_SEQ = 0x4
    DATA_LAST = 0x5
    ACK_LAST = 0x6
    JOIN = 0x7


@dataclass(frozen=True)
class Packet:
    msg_type: MsgType
    sender: Address
    receiver: Address
    seq: int
    payload: bytes
    crc_valid: bool
