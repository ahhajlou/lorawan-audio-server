from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ChirpStackModel(BaseModel):
    """
    Base model that automatically maps python snake_case fields
    to incoming JSON camelCase fields.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # Allows initialization using either snake_case or camelCase
    )


class DeviceInfo(ChirpStackModel):
    tenant_id: str
    tenant_name: str
    application_id: str
    application_name: str
    device_profile_id: str
    device_profile_name: str
    device_name: str
    dev_eui: str
    tags: dict[str, Any] | None = None


class RxInfo(ChirpStackModel):
    gateway_id: str
    uplink_id: int
    rssi: int
    snr: float
    context: str | None = None
    metadata: dict[str, str] | None = None


class LoraModulation(ChirpStackModel):
    bandwidth: int
    spreading_factor: int
    code_rate: str


class Modulation(ChirpStackModel):
    lora: LoraModulation | None = None


class TxInfo(ChirpStackModel):
    frequency: int
    modulation: Modulation


class UplinkEvent(ChirpStackModel):
    deduplication_id: str
    time: datetime
    device_info: DeviceInfo
    dev_addr: str
    dr: int
    f_port: int
    data: str
    rx_info: list[RxInfo]
    tx_info: TxInfo
