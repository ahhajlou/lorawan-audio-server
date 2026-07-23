from loguru import logger

from protocol import serializer
from protocol.models import MsgType, Packet
from registry import DeviceRegistry
from routing.stream_buffer import BufferManager
from routing.model import PublishRequest


class Forwarder:
    def __init__(self, registry: DeviceRegistry, buffers: BufferManager):
        self.registry = registry
        self.buffers = buffers

    def on_packet_up(
        self, packet: Packet, sender_eui: str, f_port: int
    ) -> PublishRequest | None:
        self.registry.register(packet.sender, sender_eui)

        if packet.msg_type == MsgType.JOIN:
            logger.info(
                "New device registered. DevEUI={dev_eui}, TX Address={tx_address}",
                dev_eui=sender_eui,
                tx_address=packet.sender,
            )
            return None

        receiver_eui = self.registry.lookup(packet.receiver)
        if not receiver_eui:
            logger.debug(
                "Receiver unknown, dropping packet. receiver={receiver}",
                receiver=packet.receiver,
            )
            return None

        ack_bytes = serializer.build_ack(packet)

        buf = self.buffers.get_or_create(receiver_eui)
        buf.enqueue(packet, f_port)

        return PublishRequest(target_eui=sender_eui, payload=ack_bytes)
