from collections.abc import Callable
from typing import Protocol

import paho.mqtt.client as mqtt
from loguru import logger
from paho.mqtt.client import PayloadType
from paho.mqtt.enums import MQTTErrorCode
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

import exceptions
from config import Settings
from transport.chirpstack_endpoints import ChirpStackMqttEndpoint
from transport.helper import catch_mqtt_connection_error

_PAHO_TO_LOGURU = {
    mqtt.LogLevel.MQTT_LOG_DEBUG: "DEBUG",
    mqtt.LogLevel.MQTT_LOG_INFO: "INFO",
    mqtt.LogLevel.MQTT_LOG_NOTICE: "INFO",  # loguru has no NOTICE
    mqtt.LogLevel.MQTT_LOG_WARNING: "WARNING",
    mqtt.LogLevel.MQTT_LOG_ERR: "ERROR",
}


class PublishDownlinkType(Protocol):
    # self, dev_eui: str, payload: PayloadType, qos=1
    def __call__(self, dev_eui: str, payload: PayloadType, qos: int = 1) -> None: ...


class MqttTransport:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="forwarder-app")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_log = self.on_log
        self.client.on_disconnect = self.on_disconnect

        self.chirpstack_mqtt_endpoint = ChirpStackMqttEndpoint()

        self.uplink_handler: Callable[[bytes], None] | None = None
        self.join_handler: Callable[[bytes], None] | None = None

        if self.settings.chirpstack_app_id is None or self.settings.chirpstack_app_id == "":
            raise ValueError("CHIRPSTACK_APP_ID is None or empty")

    def set_uplink_handler(self, handler: Callable) -> None:
        """Register the callback for uplink events."""
        self.uplink_handler = handler

    def set_join_handler(self, handler: Callable) -> None:
        """Register the callback for join events."""
        self.join_handler = handler

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(exceptions.MQTTConnectionError),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    @catch_mqtt_connection_error
    def start(self) -> MQTTErrorCode:
        return self.client.connect(self.settings.mqtt_broker_host, self.settings.mqtt_broker_port)

    @catch_mqtt_connection_error
    def stop(self) -> MQTTErrorCode:
        return self.client.disconnect()

    @catch_mqtt_connection_error
    def loop_forever(self) -> MQTTErrorCode:
        return self.client.loop_forever()

    def publish_downlink(self, dev_eui: str, payload: PayloadType, qos=1) -> None:
        logger.info("Publishing a downlink message to DevEUI: {dev_eui}", dev_eui=dev_eui)
        logger.debug(
            "Payload type: {payload_type}. Payload: {payload}",
            payload_type=type(payload),
            payload=payload,
        )
        endpoint = self.chirpstack_mqtt_endpoint.get_device_downlink(
            self.settings.chirpstack_app_id,
            dev_eui,
        )
        self.client.publish(endpoint, payload, qos=qos)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        logger.info("Connected with result code {reason_code}", reason_code=reason_code)

        # Subscribe inside on_connect to re-subscribe on auto-reconnects
        self.client.subscribe(self.chirpstack_mqtt_endpoint.get_event_up(), qos=1)
        self.client.subscribe(self.chirpstack_mqtt_endpoint.get_event_join(), qos=1)

    def on_message(self, client, userdata, msg):
        logger.debug(
            "Incoming message.  Topic: {message_topic}, Payload: {payload}",
            message_topic=msg.topic,
            payload=msg.payload,
        )

        event_type = msg.topic.rsplit("/", 1)[1]
        if event_type == "up":
            logger.info("New uplink event")
            if self.uplink_handler:
                self.uplink_handler(msg.payload)
        elif event_type == "join":
            logger.info("New join event")
            if self.join_handler:
                self.join_handler(msg.payload)
        else:
            logger.info("Other topics")

    def on_log(self, client, userdata, paho_log_level, messages):
        loguru_level = _PAHO_TO_LOGURU.get(paho_log_level, "DEBUG")
        logger.log(loguru_level, "MQTT: {message}", message=messages)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.info("Client has disconnected. reason_code: {reason_code}", reason_code=reason_code)
        # self.client.disconnected.set_result(reason_code)
