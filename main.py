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


def main():
    settings = load_env_variables()

    logger.add(sys.stderr, level=settings.log_level)
    logger.info("Hello from lorawan-audio-server!")

    mqtt_transport = MqttTransport(settings=settings)

    registry = DeviceRegistry()
    buffers = BufferManager()
    forwarder = Forwarder(registry, buffers)
    uplink_handler = UplinkHandler(forwarder, mqtt_transport.publish_downlink)
    join_handler = JoinHandler(forwarder)
    scheduler = FlushScheduler(buffers, mqtt_transport, settings.flush_interval_ms)

    mqtt_transport.set_uplink_handler(uplink_handler.handle)
    mqtt_transport.set_join_handler(join_handler.handle)

    scheduler.start()

    try:
        mqtt_transport.start()
    except exceptions.MQTTConnectionError:
        logger.error("Exiting — MQTT connection error")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt, exiting")
        sys.exit(2)

    try:
        mqtt_transport.loop_forever()
    except exceptions.MQTTConnectionError:
        logger.error("Exiting — MQTT connection error")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt, exiting")
        try:
            mqtt_transport.stop()
        except exceptions.MQTTConnectionError:
            logger.error("Exiting — MQTT connection error")
        scheduler.stop()
        sys.exit(2)


if __name__ == "__main__":
    main()
