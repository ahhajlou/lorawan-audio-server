# from chirpstack_mqtt.client2 import main_loop, ChirpStackInfo
import os

from dotenv import load_dotenv

from chirpstack_mqtt.client import ChirpStackInfo, main_loop

load_dotenv()  # reads .env and populates os.environ

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None

chrpstack_info = ChirpStackInfo(
    ip=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT, username=MQTT_USERNAME, password=MQTT_PASSWORD
)


def main():
    print("Hello from lorawan-audio-server!")
    main_loop(chrpstack_info)


if __name__ == "__main__":
    main()
