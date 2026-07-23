import os
from dotenv import load_dotenv
from dataclasses import dataclass


@dataclass
class Settings:
    mqtt_broker_host: str
    mqtt_broker_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    flush_interval_ms: int  # default 100
    chirpstack_app_id: str


def load_env_variables():
    pass
