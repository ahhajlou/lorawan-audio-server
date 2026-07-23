from threading import Lock

from protocol.models import Address


class DeviceRegistry:
    def __init__(self):
        self._map: dict[Address, str] = {}
        self._lock: Lock = Lock()

    def register(self, addr: Address, dev_eui: str) -> None:
        with self._lock:
            if addr not in self._map:
                self._map[addr] = dev_eui

    def lookup(self, addr: Address) -> str | None:
        with self._lock:
            return self._map.get(addr)
