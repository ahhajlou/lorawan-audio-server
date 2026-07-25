import pytest

from config import Settings
from transport.mqtt_client import MqttTransport


class TestMqttTransport:
    def test_none_chirpstack_addr(self):
        settings = Settings(
            mqtt_broker_host="",
            mqtt_broker_port=0,
            mqtt_username="",
            mqtt_password="",
            txack_timeout_s=5.0,
            chirpstack_app_id=None,
            log_level="INFO",
        )
        with pytest.raises(ValueError, match="CHIRPSTACK_APP_ID is None or empty"):
            _ = MqttTransport(settings)
