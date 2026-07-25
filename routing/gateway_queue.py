import threading
from collections import deque

from loguru import logger

from routing.models import DownlinkItem


class GatewayQueue:
    """Thread-safe FIFO for one gateway_id."""

    def __init__(self):
        self._pending: deque[DownlinkItem] = deque()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def enqueue(self, item: DownlinkItem) -> None:
        with self._lock:
            self._pending.append(item)
            logger.debug(
                "Enqueued {kind} for {target} on gateway {gw} (depth={depth})",
                kind=item.kind,
                target=item.target_eui,
                gw=item.gateway_id,
                depth=len(self._pending),
            )
            self._condition.notify()

    def pop_next(self, timeout: float | None = None) -> DownlinkItem | None:
        """Blocks until an item is available or timeout expires."""
        with self._condition:
            while not self._pending:
                if not self._condition.wait(timeout=timeout):
                    return None
            return self._pending.popleft()

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._pending) == 0


class GatewayDispatchQueue:
    """Thread-safe dict of per-gateway GatewayQueues."""

    def __init__(self):
        self._queues: dict[str, GatewayQueue] = {}
        self._lock = threading.Lock()

    def get_or_create(self, gateway_id: str) -> GatewayQueue:
        with self._lock:
            if gateway_id not in self._queues:
                self._queues[gateway_id] = GatewayQueue()
                logger.info("Created dispatch queue for gateway {gw}", gw=gateway_id)
            return self._queues[gateway_id]
