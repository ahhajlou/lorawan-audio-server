from threading import Lock

from protocol.models import Packet


class StreamBuffer:
    def __init__(self):
        self._pending: list[tuple[Packet, int]] = []
        self._lock: Lock = Lock()

    def enqueue(self, packet: Packet, f_port: int) -> None:
        with self._lock:
            self._pending.append((packet, f_port))

    def try_flush(self) -> tuple[Packet, int] | None:
        with self._lock:
            if self._pending:
                return self._pending.pop(0)
            return None

    def has_pending(self) -> bool:
        with self._lock:
            return len(self._pending) > 0


class BufferManager:
    def __init__(self):
        self._buffers: dict[str, StreamBuffer] = {}
        self._lock: Lock = Lock()

    def get_or_create(self, receiver_eui: str) -> StreamBuffer:
        with self._lock:
            if receiver_eui not in self._buffers:
                self._buffers[receiver_eui] = StreamBuffer()
            return self._buffers[receiver_eui]

    def get_all_active(self) -> list[tuple[str, StreamBuffer]]:
        with self._lock:
            return [(k, v) for k, v in self._buffers.items() if v.has_pending()]
