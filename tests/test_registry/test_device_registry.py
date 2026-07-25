from protocol.models import Address
from registry.device_registry import DeviceRegistry


class TestDeviceRegistry:
    def test_lookup(self):
        addr = Address(1, 4)
        dev_eui = "test_dev_eui"
        gateway_id = "gw_001"

        device_registry = DeviceRegistry(db_url="sqlite:///:memory:")
        device_registry.register(addr, dev_eui, gateway_id)

        lookup_dev_eui = device_registry.lookup_eui(addr)

        assert lookup_dev_eui == dev_eui

    def test_lookup_not_inserted(self):
        addr = Address(1, 4)
        addr_2 = Address(20, 30)
        dev_eui = "test_dev_eui"
        gateway_id = "gw_001"

        device_registry = DeviceRegistry(db_url="sqlite:///:memory:")
        device_registry.register(addr, dev_eui, gateway_id)

        lookup_dev_eui = device_registry.lookup_eui(addr_2)

        assert lookup_dev_eui is None

    def test_lookup_gateway(self):
        addr = Address(1, 4)
        dev_eui = "test_dev_eui"
        gateway_id = "gw_001"

        device_registry = DeviceRegistry(db_url="sqlite:///:memory:")
        device_registry.register(addr, dev_eui, gateway_id)

        assert device_registry.lookup_gateway(dev_eui) == gateway_id

    def test_lookup_gateway_unknown(self):
        device_registry = DeviceRegistry(db_url="sqlite:///:memory:")
        assert device_registry.lookup_gateway("nonexistent") is None
