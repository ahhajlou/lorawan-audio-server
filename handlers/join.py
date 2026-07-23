from loguru import logger

from routing.forwarder import Forwarder


class JoinHandler:
    def __init__(self, forwarder: Forwarder):
        self.forwarder = forwarder

    def handle(self, raw_json: bytes) -> None:
        logger.debug("Join event received (handled by forwarder on next uplink)")
