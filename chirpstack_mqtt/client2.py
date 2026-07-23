#!/usr/bin/env python3

import asyncio
import socket
import uuid

import time
import json
import base64
from dataclasses import dataclass

# import context  # Ensures paho is in PYTHONPATH

import paho.mqtt.client as mqtt

client_id = 'paho-mqtt-python/issue72/' + str(uuid.uuid4())
topic = "application/+/device/+/event/up"

@dataclass
class ChirpStackInfo:
    ip: str
    port: int
    username: str
    password: str


class AsyncioHelper:
    def __init__(self, loop, client):
        self.loop = loop
        self.client = client
        self.client.on_socket_open = self.on_socket_open
        self.client.on_socket_close = self.on_socket_close
        self.client.on_socket_register_write = self.on_socket_register_write
        self.client.on_socket_unregister_write = self.on_socket_unregister_write

    def on_socket_open(self, client, userdata, sock):
        print("Socket opened")

        def cb():
            print("Socket is readable, calling loop_read")
            client.loop_read()

        self.loop.add_reader(sock, cb)
        self.misc = self.loop.create_task(self.misc_loop())

    def on_socket_close(self, client, userdata, sock):
        print("Socket closed")
        self.loop.remove_reader(sock)
        self.misc.cancel()

    def on_socket_register_write(self, client, userdata, sock):
        print("Watching socket for writability.")

        def cb():
            print("Socket is writable, calling loop_write")
            client.loop_write()

        self.loop.add_writer(sock, cb)

    def on_socket_unregister_write(self, client, userdata, sock):
        print("Stop watching socket for writability.")
        self.loop.remove_writer(sock)

    async def misc_loop(self):
        print("misc_loop started")
        while self.client.loop_misc() == mqtt.MQTT_ERR_SUCCESS:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
        print("misc_loop finished")


class AsyncMqttExample:
    def __init__(self, loop, chrpstack_info: ChirpStackInfo):
        self.loop = loop
        self.chrpstack_info = chrpstack_info

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print("Subscribing")
        # client.subscribe(topic)

    def on_message(self, client, userdata, msg):
        if not self.got_message:
            print("Got unexpected message: {}".format(msg.decode()))
        else:
            self.got_message.set_result(msg.payload)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.disconnected.set_result(reason_code)

    def close(self):
        self.client.disconnect()

    async def main(self):
        # self.disconnected = self.loop.create_future()
        # self.got_message = None

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        # self.client.on_connect = self.on_connect
        # self.client.on_message = self.on_message
        # self.client.on_disconnect = self.on_disconnect

        aioh = AsyncioHelper(self.loop, self.client)

        self.client.connect(self.chrpstack_info.ip, self.chrpstack_info.port, 60)
        self.client.socket().setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2048)

        while True:
            await asyncio.sleep(5)
            print("Publishing")
            # self.got_message = self.loop.create_future()

            app_id="9e416001-0bc0-4313-9baf-a1df7b7e38d7"
            dev_eui="ac1f09fffe000000"

            downlink_payload = json.dumps({
                "devEui": f"{dev_eui}",
                "confirmed": False,
                "fPort": 2,
                "data": "SGVsbG8="
            })

            self.client.publish(f"application/{app_id}/device/{dev_eui}/command/down", downlink_payload, qos=1) 
            # self.client.publish(topic, b'Hello' * 40000, qos=1)

            # msg = await self.got_message
            # print("Got response with {} bytes".format(len(msg)))
            # self.got_message = None

        # self.client.disconnect()
        # print("Disconnected: {}".format(await self.disconnected))


def main_loop(chrpstack_info: ChirpStackInfo):
    print("Starting")
    loop = asyncio.get_event_loop()
    async_mqtt = AsyncMqttExample(loop, chrpstack_info)
    try:
        loop.run_until_complete(async_mqtt.main())
    except KeyboardInterrupt:
        async_mqtt.close()
        loop.close()
        print("Finished")