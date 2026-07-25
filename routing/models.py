from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DownlinkItem:
    target_eui: str
    gateway_id: str
    payload: bytes
    kind: Literal["ack", "data"]
    f_port: int
