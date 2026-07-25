import base64

import pydantic
from loguru import logger

import exceptions
from dispatch.dispatcher import DispatcherManager
from protocol import parser
from routing.forwarder import Forwarder
from routing.gateway_queue import GatewayDispatchQueue
from transport.chirpstack_event_types.uplink import UplinkEvent


class UplinkHandler:
    def __init__(
        self,
        forwarder: Forwarder,
        dispatch_queue: GatewayDispatchQueue,
        dispatcher_manager: DispatcherManager,
    ):
        self.forwarder = forwarder
        self.dispatch_queue = dispatch_queue
        self.dispatcher_manager = dispatcher_manager

    def handle(self, raw_json: bytes) -> None:
        try:
            event_data = UplinkEvent.model_validate_json(raw_json)
        except pydantic.ValidationError:
            logger.warning("Pydantic parse error {raw_json}", raw_json=raw_json)
            return None

        try:
            decoded_payload = base64.b64decode(event_data.data)
        except Exception:
            logger.warning("Base64 decode error. Data: {data}", data=event_data.data)
            return None

        try:
            packet = parser.parse(decoded_payload)
        except exceptions.ProtocolError as e:
            logger.warning("Protocol parse error. Error: {error}", error=e)
            return None

        logger.debug("Parsed packet = {packet}", packet=packet)

        sender_eui = event_data.device_info.dev_eui
        f_port = event_data.f_port

        gateway_id = self._extract_gateway_id(event_data)
        if gateway_id is None:
            logger.warning("No rxInfo in uplink event, dropping")
            return None

        try:
            items = self.forwarder.on_packet_up(
                packet, sender_eui, gateway_id, f_port
            )
        except ValueError as e:
            logger.warning("Forwarder ValueError. Error: {error}", error=e)
            return None

        if not items:
            return None

        queue = self.dispatch_queue.get_or_create(gateway_id)
        self.dispatcher_manager.ensure_dispatcher(gateway_id)
        for item in items:
            queue.enqueue(item)

    def _extract_gateway_id(self, event_data: UplinkEvent) -> str | None:
        if not event_data.rx_info:
            return None
        strongest = max(event_data.rx_info, key=lambda rx: rx.rssi)
        return strongest.gateway_id
