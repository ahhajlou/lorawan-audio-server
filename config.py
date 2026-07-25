import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_LOG_LEVEL = "INFO"
VALID_LOG_LEVELS = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}


@dataclass
class Settings:
    mqtt_broker_host: str
    mqtt_broker_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    txack_timeout_s: float
    chirpstack_app_id: str | None
    log_level: str


def load_env_variables() -> Settings:
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    if log_level not in VALID_LOG_LEVELS:
        raise ValueError(f"Invalid LOG_LEVEL '{log_level}'. Must be one of: {VALID_LOG_LEVELS}")

    settings = Settings(
        mqtt_broker_host=os.getenv("MQTT_BROKER_HOST", "localhost"),
        mqtt_broker_port=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        mqtt_username=os.getenv("MQTT_USERNAME") or None,
        mqtt_password=os.getenv("MQTT_PASSWORD") or None,
        txack_timeout_s=float(os.getenv("TXACK_TIMEOUT_S", "5.0")),
        chirpstack_app_id=os.getenv("CHIRPSTACK_APP_ID") or None,
        log_level=log_level,
    )

    return settings
