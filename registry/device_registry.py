from threading import Lock

from protocol.models import Address


class DeviceRegistry:
    def __init__(self):
        self._map: dict[Address, str] = {}
        self._lock: Lock = Lock()

    def register(self, addr: Address, dev_eui: str) -> None:
        # TODO: Consier if the addr (Application level address) exists
        # but dev_ui (LoRaWAN addressing) has changed
        with self._lock:
            if addr not in self._map:
                self._map[addr] = dev_eui

    def lookup(self, addr: Address) -> str | None:
        with self._lock:
            return self._map.get(addr)
