from dataclasses import dataclass


@dataclass(frozen=True)
class PublishRequest:
    target_eui: str
    payload: bytes
