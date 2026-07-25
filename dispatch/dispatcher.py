import base64
import json
import threading
from collections.abc import Callable

from loguru import logger

from routing.gateway_queue import GatewayDispatchQueue, GatewayQueue


class Dispatcher:
    """One instance per gateway_id. Runs in its own thread.

    Pops items from the queue, publishes them, waits for txack (or timeout),
    then advances to the next item.
    """

    def __init__(
        self,
        gateway_id: str,
        queue: GatewayQueue,
        publish_downlink: Callable[[str, str], None],
        txack_timeout: float = 5.0,
    ):
        self.gateway_id = gateway_id
        self.queue = queue
        self.publish_downlink = publish_downlink
        self.txack_timeout = txack_timeout
        self._stop = threading.Event()
        self._txack_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=f"dispatcher-{self.gateway_id}"
        )
        self._thread.start()
        logger.info(
            "Dispatcher started for gateway {gw} (txack_timeout={t}s)",
            gw=self.gateway_id,
            t=self.txack_timeout,
        )

    def stop(self) -> None:
        self._stop.set()
        self._txack_event.set()
        if self._thread:
            self._thread.join()
        logger.info("Dispatcher stopped for gateway {gw}", gw=self.gateway_id)

    def notify_txack(self) -> None:
        """Called by the txack listener when a txack arrives for this gateway."""
        self._txack_event.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            item = self.queue.pop_next(timeout=1.0)
            if item is None:
                continue

            logger.info(
                "Dispatching {kind} to {target} via gateway {gw}",
                kind=item.kind,
                target=item.target_eui,
                gw=self.gateway_id,
            )

            try:
                b64 = base64.b64encode(item.payload).decode("utf-8")
                envelope = json.dumps(
                    {
                        "devEui": item.target_eui,
                        "confirmed": False,
                        "fPort": item.f_port,
                        "data": b64,
                    }
                )
            except Exception as e:
                logger.warning("Failed to build envelope: {error}", error=e)
                continue

            self.publish_downlink(item.target_eui, envelope)

            self._txack_event.clear()
            received = self._txack_event.wait(timeout=self.txack_timeout)
            if not received:
                logger.warning(
                    "txack timeout for {kind} to {target} on gateway {gw}",
                    kind=item.kind,
                    target=item.target_eui,
                    gw=self.gateway_id,
                )
            else:
                logger.debug(
                    "txack received for gateway {gw}", gw=self.gateway_id
                )


class DispatcherManager:
    """Manages one Dispatcher per gateway_id. Thread-safe."""

    def __init__(
        self,
        dispatch_queue: "GatewayDispatchQueue",
        publish_downlink: Callable[[str, str], None],
        txack_timeout: float = 5.0,
    ):
        self._dispatch_queue = dispatch_queue
        self._dispatchers: dict[str, Dispatcher] = {}
        self._lock = threading.Lock()
        self._publish_downlink = publish_downlink
        self._txack_timeout = txack_timeout

    def ensure_dispatcher(self, gateway_id: str) -> None:
        with self._lock:
            if gateway_id not in self._dispatchers:
                queue = self._dispatch_queue.get_or_create(gateway_id)
                dispatcher = Dispatcher(
                    gateway_id=gateway_id,
                    queue=queue,
                    publish_downlink=self._publish_downlink,
                    txack_timeout=self._txack_timeout,
                )
                dispatcher.start()
                self._dispatchers[gateway_id] = dispatcher

    def notify_txack(self, gateway_id: str) -> None:
        with self._lock:
            dispatcher = self._dispatchers.get(gateway_id)
        if dispatcher:
            dispatcher.notify_txack()
        else:
            logger.debug("txack for unknown gateway {gw}", gw=gateway_id)

    def stop_all(self) -> None:
        with self._lock:
            dispatchers = list(self._dispatchers.values())
        for d in dispatchers:
            d.stop()
