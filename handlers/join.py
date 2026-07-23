class JoinHandler:
    def __init__(self, parser, forwarder: Forwarder): ...

    def handle(self, raw_json: bytes) -> None:
        """Join handler."""