import pydantic
from loguru import logger

from dispatch.dispatcher import DispatcherManager
from transport.chirpstack_event_types.txack import TxAckEvent


class TxAckHandler:
    def __init__(self, dispatcher_manager: DispatcherManager):
        self.dispatcher_manager = dispatcher_manager

    def handle(self, raw_json: bytes) -> None:
        try:
            event = TxAckEvent.model_validate_json(raw_json)
        except pydantic.ValidationError:
            logger.warning("TxAck pydantic parse error: {raw}", raw=raw_json)
            return

        gateway_id = event.gateway_id
        if not gateway_id:
            logger.warning("TxAck event missing gateway_id")
            return

        self.dispatcher_manager.notify_txack(gateway_id)
