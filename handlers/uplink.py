from routing.forwarder import Forwarder


class UplinkHandler:
    def __init__(self, forwarder: Forwarder):
        self.forwarder = forwarder

    def handle(self, raw_json: bytes) -> None:
        """Parse JSON envelope, deserialize, resolve, forward."""
        """1. Parse ChirpStack JSON envelope
           2. base64 decode payload
           3. protocol.parse() → Packet
           4. Register sender address if new
           5. Forwarder.on_packet_up()"""

        # ...
        self.forwarder.on_packet_up()
