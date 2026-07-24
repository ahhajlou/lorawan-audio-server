import pytest

from protocol.models import Address
from registry.device_registry import DeviceRegistry


@pytest.fixture
def registry():
    reg = DeviceRegistry()
    yield reg


@pytest.fixture
def known_devices(registry):
    devices = {
        Address(0x00, 0x03): "ac1f09fffe000000",
        Address(0x00, 0x05): "bb1f09fffe000001",
    }
    for addr, eui in devices.items():
        registry.register(addr, eui)
    return devices


class TestDeviceRegistryWithFixtures:
    def test_lookup_known(self, known_devices, registry):
        addr = Address(0x00, 0x03)
        assert registry.lookup(addr) == "ac1f09fffe000000"

    def test_lookup_unknown(self, known_devices, registry):
        addr = Address(0xFF, 0xFF)
        assert registry.lookup(addr) is None

    def test_register_new(self, registry):
        addr = Address(0x01, 0x02)
        registry.register(addr, "new_device")
        assert registry.lookup(addr) == "new_device"

    def test_register_does_not_overwrite(self, known_devices, registry):
        addr = Address(0x00, 0x03)
        registry.register(addr, "overwrite_attempt")
        assert registry.lookup(addr) == "ac1f09fffe000000"

    def test_multiple_lookups(self, known_devices, registry):
        for addr, expected_eui in known_devices.items():
            assert registry.lookup(addr) == expected_eui
