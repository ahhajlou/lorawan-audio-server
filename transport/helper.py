import functools
import time

from loguru import logger
from paho.mqtt.enums import MQTTErrorCode

import exceptions


def with_retry(max_retries=3, delay=1.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions.MQTTConnectionError:
                    if attempt == max_retries - 1:
                        logger.error("Giving up after {n} attempts", n=max_retries)
                        raise
                    logger.warning("Retry {attempt}/{max}...", attempt=attempt + 1, max=max_retries)
                    time.sleep(delay)

        return wrapper

    return decorator


def catch_mqtt_connection_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> MQTTErrorCode:
        try:
            error = func(*args, **kwargs)
            if error != MQTTErrorCode.MQTT_ERR_SUCCESS:
                raise exceptions.MQTTConnectionError(f"MQTT Connection Error. Error code: {error}")
            return error
        except OSError as e:
            logger.error("MQTT connection error. Error: {error}", error=e)
            raise exceptions.MQTTConnectionError(f"MQTT connection error: {e}") from e

    return wrapper
