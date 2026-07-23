class Forwarder:
    def __init__(self, registry: DeviceRegistry, buffers: BufferManager): ...

    def on_packet_up(self, packet: Packet, sender_eui: str) -> None:
        """Decide what to do: ACK sender, enqueue for receiver, drop."""
