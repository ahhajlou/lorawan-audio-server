from protocol.models import Packet
from registry import DeviceRegistry
from routing import BufferManager


class Forwarder:
    def __init__(self, registry: DeviceRegistry, buffers: BufferManager):
        pass

    def on_packet_up(self, packet: Packet, sender_eui: str) -> None:
        """Decide what to do: ACK sender, enqueue for receiver, drop."""
