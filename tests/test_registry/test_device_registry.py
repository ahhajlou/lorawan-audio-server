from protocol.models import Address
from registry.device_registry import DeviceRegistry


class TestDeviceRegistry:
    def test_lookup(self):
        addr = Address(1, 4)
        dev_eui = "test_dev_eui"

        device_registry = DeviceRegistry()
        device_registry.register(addr, dev_eui)

        lookup_dev_eui = device_registry.lookup(addr)

        assert lookup_dev_eui == dev_eui

    def test_lookup_not_inserted(self):
        addr = Address(1, 4)
        addr_2 = Address(20, 30)
        dev_eui = "test_dev_eui"

        device_registry = DeviceRegistry()
        device_registry.register(addr, dev_eui)

        lookup_dev_eui = device_registry.lookup(addr_2)

        assert lookup_dev_eui is None
