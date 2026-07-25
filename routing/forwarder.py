from loguru import logger

from protocol import serializer
from protocol.models import MsgType, Packet
from registry import DeviceRegistry
from routing.models import DownlinkItem


class Forwarder:
    def __init__(self, registry: DeviceRegistry):
        self.registry = registry

    def on_packet_up(
        self, packet: Packet, sender_eui: str, gateway_id: str, f_port: int
    ) -> list[DownlinkItem]:
        self.registry.register(packet.sender, sender_eui, gateway_id)

        if packet.msg_type == MsgType.JOIN:
            logger.info(
                "New device registered. DevEUI={dev_eui}, TX Address={tx_address}",
                dev_eui=sender_eui,
                tx_address=packet.sender,
            )
            return []

        receiver_eui = self.registry.lookup_eui(packet.receiver)
        if not receiver_eui:
            logger.debug(
                "Receiver unknown, dropping packet. receiver={receiver}",
                receiver=packet.receiver,
            )
            return []

        ack_bytes = serializer.build_ack(packet)
        data_bytes = serializer.build_downlink(packet)

        items = [
            DownlinkItem(
                target_eui=sender_eui,
                gateway_id=gateway_id,
                payload=ack_bytes,
                kind="ack",
                f_port=f_port,
            ),
            DownlinkItem(
                target_eui=receiver_eui,
                gateway_id=gateway_id,
                payload=data_bytes,
                kind="data",
                f_port=f_port,
            ),
        ]

        logger.debug(
            "Built {count} downlink items for gateway {gw}",
            count=len(items),
            gw=gateway_id,
        )
        return items
