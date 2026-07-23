import sys

from loguru import logger

import exceptions
from config import load_env_variables
from handlers import JoinHandler, UplinkHandler
from registry import DeviceRegistry
from routing import BufferManager, Forwarder
from scheduler import FlushScheduler
from transport.mqtt_client import MqttTransport

logger.remove()
logger.add(sys.stderr, level="INFO")
# logger.add("logs/server.log", rotation="10 MB", retention="7 days", level="DEBUG")


def main():
    logger.info("Hello from lorawan-audio-server!")
    settings = load_env_variables()
    mqtt_transport = MqttTransport(settings=settings)

    registry = DeviceRegistry()
    buffers = BufferManager()
    forwarder = Forwarder(registry, buffers)
    uplink_handler = UplinkHandler(forwarder)
    _join_handler = JoinHandler(forwarder)
    scheduler = FlushScheduler(buffers, mqtt_transport, settings.flush_interval_ms)

    mqtt_transport.set_uplink_handler(uplink_handler.handle)

    scheduler.start()

    try:
        mqtt_transport.start()
    except exceptions.ConnectionError:
        logger.error("Exiting — MQTT broker unreachable")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt, exiting")
        sys.exit(2)

    try:
        mqtt_transport.loop_forever()
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt, exiting")
        mqtt_transport.stop()
        sys.exit(2)


if __name__ == "__main__":
    main()
