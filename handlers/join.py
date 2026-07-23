from routing.forwarder import Forwarder


class JoinHandler:
    # def __init__(self, parser, forwarder: Forwarder): ...
    def __init__(self, forwarder: Forwarder):
        self.forwarder = forwarder

    def handle(self, raw_json: bytes) -> None:
        """Join handler."""
