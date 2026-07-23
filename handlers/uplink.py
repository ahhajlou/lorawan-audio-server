import base64

import pydantic

import exceptions
from protocol import parser
from routing.forwarder import Forwarder
from transport.chirpstack_even_types.uplink import UplinkEvent


class UplinkHandler:
    def __init__(self, forwarder: Forwarder):
        self.forwarder = forwarder

    def handle(self, raw_json: bytes) -> None:
        """Parse JSON envelope, deserialize, resolve, forward."""
        """1. Parse ChirpStack JSON envelope
           2. base64 decode payload
           3. protocol.parse() → Packet
           4. Forwarder.on_packet_up()"""

        try:
            event_data = UplinkEvent.model_validate_json(raw_json)
        except pydantic.ValidationError as e:
            raise exceptions.ParseError(f"Pydantic parse error {raw_json}") from e

        try:
            decoded_paylod = base64.b64decode(event_data.data)
        except Exception as e:
            raise exceptions.ParseError(f"Base64 decode error. Data: {event_data.data}") from e

        packet = parser.parse(decoded_paylod)

        self.forwarder.on_packet_up(packet, event_data=event_data)
