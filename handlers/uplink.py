class UplinkHandler:
    def __init__(self, parser, forwarder: Forwarder): ...

    def handle(self, raw_json: bytes) -> None:
        """Parse JSON envelope, deserialize, resolve, forward."""
