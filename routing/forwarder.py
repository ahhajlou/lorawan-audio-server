import base64
import json

from loguru import logger

from protocol import serializer
from protocol.models import MsgType, Packet
from registry import DeviceRegistry
from routing import BufferManager
from transport.chirpstack_even_types.uplink import UplinkEvent


class Forwarder:
    def __init__(self, registry: DeviceRegistry, buffers: BufferManager):
        self.registry = registry
        self.buffers = buffers

    def on_packet_up(self, packet: Packet, event_data: UplinkEvent) -> None:
        """Decide what to do: ACK sender, enqueue for receiver, drop.
        Also register device in DeviceRegistry"""

        if packet.msg_type == MsgType.JOIN:
            logger.info(
                "New device has been registerred. DevEUI={dev_eui}, TX Address={tx_address}",
                dev_eui=event_data.device_info.dev_eui,
                tx_address=packet.sender,
            )
            self.registry.register(packet.sender, event_data.device_info.dev_eui)
            return

        ack_bytes = serializer.build_ack(packet)
        ack_b64 = base64.b64encode(ack_bytes).decode("utf-8")

        ack_payload = json.dumps(
            {
                "devEui": event_data.device_info.dev_eui,
                "confirmed": False,
                "fPort": event_data.f_port,
                "data": ack_b64,
            }
        )

        logger.debug(ack_payload)
