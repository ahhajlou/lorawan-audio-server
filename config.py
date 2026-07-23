import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Settings:
    mqtt_broker_host: str
    mqtt_broker_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    flush_interval_ms: int  # default 100
    chirpstack_app_id: str


def load_env_variables() -> Settings:
    load_dotenv()  # reads .env and populates os.environ

    settings = Settings(
        mqtt_broker_host=os.getenv("MQTT_BROKER_HOST", "localhost"),
        mqtt_broker_port=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        mqtt_username=os.getenv("MQTT_USERNAME") or None,
        mqtt_password=os.getenv("MQTT_PASSWORD") or None,
        flush_interval_ms=int(os.getenv("FLUSH_INTERVAL_MS", "100")),
        chirpstack_app_id=os.getenv("CHIRPSTACK_APP_ID") or None,
    )

    return settings
