import functools
from collections.abc import Callable
from typing import Any

from loguru import logger
from paho.mqtt.enums import MQTTErrorCode

import exceptions


def catch_mqtt_connection_error(func: Callable[[Any], MQTTErrorCode]):
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> MQTTErrorCode:
        try:
            error: MQTTErrorCode = func(*args, **kwargs)
            if error != MQTTErrorCode.MQTT_ERR_SUCCESS:
                raise exceptions.MQTTConnectionError(f"MQTT Connection Error. Error code: {error}")
            return error
        except OSError as e:
            logger.error("MQTT connection error. Error: {error}", error=e)
            raise exceptions.MQTTConnectionError(f"MQTT connection error: {e}") from e

    return wrapper
