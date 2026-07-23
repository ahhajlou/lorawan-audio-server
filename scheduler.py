import base64
import json
import threading

from loguru import logger

from protocol import serializer
from routing.stream_buffer import BufferManager
from transport.mqtt_client import MqttTransport


class FlushScheduler:
    def __init__(
        self,
        buffers: BufferManager,
        transport: MqttTransport,
        flush_interval_ms: int = 100,
    ):
        self.buffers = buffers
        self.transport = transport
        self.flush_interval = flush_interval_ms / 1000.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(
            "Flush scheduler started. interval_ms={interval}",
            interval=int(self.flush_interval * 1000),
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        logger.info("Flush scheduler stopped")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self.flush_interval)

            active = self.buffers.get_all_active()
            for receiver_eui, buf in active:
                result = buf.try_flush()
                if result:
                    pkt, f_port = result
                    raw_bytes = serializer.build_downlink(pkt)
                    b64 = base64.b64encode(raw_bytes).decode("utf-8")
                    envelope = json.dumps(
                        {
                            "devEui": receiver_eui,
                            "confirmed": False,
                            "fPort": f_port,
                            "data": b64,
                        }
                    )
                    self.transport.publish_downlink(receiver_eui, envelope)
