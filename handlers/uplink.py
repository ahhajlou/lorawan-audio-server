import base64
import json

import pydantic

import exceptions
from protocol import parser
from routing.forwarder import Forwarder
from transport.chirpstack_event_types.uplink import UplinkEvent


class UplinkHandler:
    def __init__(self, forwarder: Forwarder, publish_downlink):
        self.forwarder = forwarder
        self.publish_downlink = publish_downlink

    def handle(self, raw_json: bytes) -> None:
        try:
            event_data = UplinkEvent.model_validate_json(raw_json)
        except pydantic.ValidationError as e:
            raise exceptions.ParseError(f"Pydantic parse error {raw_json}") from e

        try:
            decoded_payload = base64.b64decode(event_data.data)
        except Exception as e:
            raise exceptions.ParseError(f"Base64 decode error. Data: {event_data.data}") from e

        packet = parser.parse(decoded_payload)

        sender_eui = event_data.device_info.dev_eui
        f_port = event_data.f_port

        result = self.forwarder.on_packet_up(packet, sender_eui, f_port)

        if result:
            b64 = base64.b64encode(result.payload).decode("utf-8")
            envelope = json.dumps(
                {
                    "devEui": result.target_eui,
                    "confirmed": False,
                    "fPort": f_port,
                    "data": b64,
                }
            )
            self.publish_downlink(result.target_eui, envelope)
