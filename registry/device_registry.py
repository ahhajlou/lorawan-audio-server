from threading import Lock

from protocol.models import Address


class DeviceRegistry:
    def __init__(self):
        self.storage: dict[Address, str] = dict()
        self.lock = Lock()

    def register(self, addr: Address, dev_eui: str) -> None:
        with self.lock:
            if addr not in self.storage:
                self.storage[addr] = dev_eui

    def lookup(self, addr: Address) -> str | None:
        with self.lock:
            return self.storage.get(addr)
