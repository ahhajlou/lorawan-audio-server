import base64
import json

import pydantic
from loguru import logger

import exceptions
from protocol import parser
from routing.forwarder import Forwarder
from transport import mqtt_client
from transport.chirpstack_event_types.uplink import UplinkEvent


class UplinkHandler:
    def __init__(self, forwarder: Forwarder, publish_downlink: mqtt_client.PublishDownlinkType):
        self.forwarder = forwarder
        self.publish_downlink: mqtt_client.PublishDownlinkType = publish_downlink

    def handle(self, raw_json: bytes) -> None:
        try:
            event_data = UplinkEvent.model_validate_json(raw_json)
        except pydantic.ValidationError:
            logger.warning("Pydantic parse error {raw_json}", raw_json=raw_json)
            # raise exceptions.ParseError(f"Pydantic parse error {raw_json}") from e
            return None

        try:
            decoded_payload = base64.b64decode(event_data.data)
        except Exception:
            logger.warning("Base64 decode error. Data: {data}", data=event_data.data)
            # raise exceptions.ParseError(f"Base64 decode error. Data: {event_data.data}") from e
            return None

        try:
            packet = parser.parse(decoded_payload)
        except exceptions.ProtocolError as e:
            logger.warning("Protocol parse error. Error: {error}", error=e)
            return None

        logger.debug("Parsed packet = {packet}", packet=packet)

        sender_eui = event_data.device_info.dev_eui
        f_port = event_data.f_port

        try:
            result = self.forwarder.on_packet_up(packet, sender_eui, f_port)
        except ValueError as e:
            logger.warning("Forwarder ValueError. Error: {error}", error=e)
            return None

        if result:
            try:
                b64 = base64.b64encode(result.payload).decode("utf-8")
            except Exception as e:
                logger.warning("Base64 encode error. Error: {error}", error=e)
                return None

            try:
                envelope = json.dumps(
                    {
                        "devEui": result.target_eui,
                        "confirmed": False,
                        "fPort": f_port,
                        "data": b64,
                    }
                )
            except ValueError as e:
                logger.warning("JSON dumps ValueError. Error: {error}", error=e)

            self.publish_downlink(
                result.target_eui,
                envelope,
            )
