from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ChirpStackModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class TxAckEvent(ChirpStackModel):
    downlink_id: int
    gateway_id: str
    dev_eui: str | None = None
    f_cnt_down: int | None = None
    device_info: dict | None = None
    queue_item_id: str | None = None
    tx_info: dict | None = None
