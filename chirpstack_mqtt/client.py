import time
import datetime
import json
import base64
from dataclasses import dataclass
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

from cffi import FFI

# NODES_ADDR_TO_DEVEUI_MAP = {
#     (0x00, 0x03): "ac1f09fffe000000",
#     (0x00, 0x05): "bb1f09fffe000001"
# }
NODES_ADDR_TO_DEVEUI_MAP = dict()


@dataclass
class ChirpStackInfo:
    ip: str
    port: int
    username: str
    password: str


def calculateAndWriteCrc8(data, payload_len: int):
    crc = 0x00

    # before calculating crc, we need to set this value, because it is
    # effective at CRC8 calcualtion
    data.header.payload_and_crc_len = payload_len + 1  # minimum: 1

    crc ^= data.header.type
    crc ^= data.header.senderAddress.addh
    crc ^= data.header.senderAddress.addl
    crc ^= data.header.receiverAddress.addh
    crc ^= data.header.receiverAddress.addl
    crc ^= data.header.seq & 0xFF  # low byte of seq
    crc ^= (data.header.seq >> 8) & 0xFF  # high byte of seq
    crc ^= data.header.payload_and_crc_len

    for i in range(payload_len):
        crc ^= data.payloadAndCrc[i]

    crc8Index = payload_len
    data.payloadAndCrc[crc8Index] = crc  # last byte reserved for crc8

    return data


def verifyCrc8(data) -> bool:
    crc = 0x00

    crc ^= data.header.type
    crc ^= data.header.senderAddress.addh
    crc ^= data.header.senderAddress.addl
    crc ^= data.header.receiverAddress.addh
    crc ^= data.header.receiverAddress.addl
    crc ^= data.header.seq & 0xFF  # low byte of seq
    crc ^= (data.header.seq >> 8) & 0xFF  # high byte of seq
    crc ^= data.header.payload_and_crc_len

    for i in range(data.header.payload_and_crc_len - 1):
        crc ^= data.payloadAndCrc[i]

    crc8Index = data.header.payload_and_crc_len - 1
    recievedMessageCrc8 = data.payloadAndCrc[crc8Index]
    if crc == recievedMessageCrc8:
        return True
    else:
        return False


class DataValididty(Exception):
    def __init__(self, *args):
        super().__init__(args)


ESP32_LORA_STRUCT_CDEF = """
#define LORA_PAYLOAD_SIZE_PLUS_CRC 44

typedef struct {
    uint8_t  type; // lora_message_type_t
    struct {
        uint8_t addh;
        uint8_t addl;
    } senderAddress;
    struct {
        uint8_t addh;
        uint8_t addl;
    } receiverAddress;             
    uint16_t seq;
    uint8_t  payload_and_crc_len;
} Header;

struct LoRaData {
    Header header;
    uint8_t  payloadAndCrc [LORA_PAYLOAD_SIZE_PLUS_CRC];
};
"""


def parse_c_struct(data: bytes):
    ffi = FFI()

    ffi.cdef(ESP32_LORA_STRUCT_CDEF, pack=1)

    unpacked_data = ffi.from_buffer("struct LoRaData *", data)
    print()
    print()
    print("============")
    print(f"{unpacked_data.header.type=}")
    print(f"{unpacked_data.header.senderAddress.addh=}")
    print(f"{unpacked_data.header.senderAddress.addl=}")
    print(f"{unpacked_data.header.receiverAddress.addh=}")
    print(f"{unpacked_data.header.receiverAddress.addl=}")
    print(f"{unpacked_data.header.seq=}")
    print(f"{unpacked_data.header.payload_and_crc_len=}")

    if unpacked_data.header.payload_and_crc_len > len(unpacked_data.payloadAndCrc):
        raise DataValididty(
            "unpacked_data.header.payload_and_crc_len > len(unpacked_data.payloadAndCrc)"
        )
        # Or pass
    if unpacked_data.header.payload_and_crc_len <= 0:
        raise DataValididty("data.header.payload_and_crc_len <= 0")

    for payload in unpacked_data.payloadAndCrc:
        print(hex(payload))
        break  # temp
    print("============")
    print()
    print()

    print(f"{verifyCrc8(unpacked_data)=}")

    return unpacked_data


def garbage_parse_c_struct(data: bytes):
    ffi = FFI()

    ffi.cdef(
        """
    #define LORA_PAYLOAD_SIZE_PLUS_CRC 44

    struct LoRaData {
        struct {
            uint8_t  varA;
            uint8_t  varB;
            uint16_t varC;
            uint32_t varD;
        } header;
        uint8_t payload[44];
    };
    """,
        pack=1,
    )

    unpacked_data = ffi.from_buffer("struct LoRaData *", data)
    print()
    print()
    print("============")
    print(f"{unpacked_data.header.varA=}")
    print(f"{unpacked_data.header.varB=}")
    print(f"{unpacked_data.header.varC=}")
    print(f"{unpacked_data.header.varD=}")
    print(f"{unpacked_data.payload=}")
    for i, payload in enumerate(unpacked_data.payload):
        if i == 4:
            break
        print(hex(payload))
    print("============")
    print()
    print()


def prepare_ack_message(unpacked_data) -> bytes:
    ffi = FFI()
    ffi.cdef(ESP32_LORA_STRUCT_CDEF, pack=1)
    my_struct = ffi.new("struct LoRaData *")

    if unpacked_data.header.type == 0x1:
        my_struct.header.type = 0x2
    elif unpacked_data.header.type == 0x3:
        my_struct.header.type = 0x4
    elif unpacked_data.header.type == 0x5:
        my_struct.header.type = 0x6
    else:
        print("Invalid header type")
        return None

    # Swap sender and receiver address, to response the sender that its data received
    # Instead of waiting for final receiver to acknowledge it, we do it to reduce packet air time
    my_struct.header.senderAddress.addh = unpacked_data.header.receiverAddress.addh
    my_struct.header.senderAddress.addl = unpacked_data.header.receiverAddress.addl
    my_struct.header.receiverAddress.addh = unpacked_data.header.senderAddress.addh
    my_struct.header.receiverAddress.addl = unpacked_data.header.senderAddress.addl

    my_struct.header.seq = unpacked_data.header.seq

    data_with_crc_calculated = calculateAndWriteCrc8(my_struct, 0)

    raw_bytes = bytes(ffi.buffer(data_with_crc_calculated))

    header_size = ffi.sizeof("Header")
    payload_size = data_with_crc_calculated.header.payload_and_crc_len
    fixed_part_header = raw_bytes[:header_size]
    variable_part_payload = raw_bytes[header_size : header_size + payload_size]

    return fixed_part_header + variable_part_payload


def chirpstack_uplink_handler(client, payload):
    j = json.loads(payload.decode("utf-8"))
    d = j["data"]

    try:
        unpacked_data = parse_c_struct(data=base64.b64decode(d))
    except DataValididty as e:
        print(f"Invalid data. error={e}")
        return

    sender_dev_eui = j["deviceInfo"]["devEui"]
    print(f"{unpacked_data.header.type=}\nNODES === {NODES_ADDR_TO_DEVEUI_MAP.items()}")
    if (
        not (unpacked_data.header.senderAddress.addh, unpacked_data.header.senderAddress.addl)
        in NODES_ADDR_TO_DEVEUI_MAP
    ):
        NODES_ADDR_TO_DEVEUI_MAP[
            (unpacked_data.header.senderAddress.addh, unpacked_data.header.senderAddress.addl)
        ] = sender_dev_eui

    receiver_dev_eui = NODES_ADDR_TO_DEVEUI_MAP.get(
        (unpacked_data.header.receiverAddress.addh, unpacked_data.header.receiverAddress.addl)
    )

    if unpacked_data.header.type == 0x7:
        print("Post join message, not continue")
        return

    # TMP
    receiver_dev_eui = "ac1f09fffe0020a0"

    if not receiver_dev_eui:
        print(
            "receiver_dev_eui does not exist in memory, probably it has not joined to the network"
        )
        return

    # app_id="9e416001-0bc0-4313-9baf-a1df7b7e38d7"
    app_id = j["deviceInfo"]["applicationId"]
    f_port = int(j["fPort"])

    # Forward message to receiver
    # downlink_payload = json.dumps({
    #     "devEui": f"{receiver_dev_eui}",
    #     "confirmed": False,
    #     "fPort": f_port,
    #     # "data": j["data"]
    #     "data": "SGVsbG8="
    # })
    # client.publish(f"application/{app_id}/device/{receiver_dev_eui}/command/down", downlink_payload, qos=1)

    # Send fake ack to sender
    print("Sending ack to message")
    ack_message_hex = prepare_ack_message(unpacked_data=unpacked_data)
    print(f"Ack hex {ack_message_hex}")

    downlink_payload_ack = json.dumps(
        {
            "devEui": f"{sender_dev_eui}",
            "confirmed": False,
            "fPort": f_port,
            "data": base64.b64encode(ack_message_hex).decode("utf-8"),
        }
    )
    client.publish(
        f"application/{app_id}/device/{sender_dev_eui}/command/down", downlink_payload_ack, qos=2
    )
    print(f"Ack message={downlink_payload_ack}")


# 1. Define what happens when a message is received
def on_message(client, userdata, msg):
    # print(f"Received message on {msg.topic}: {msg.payload.decode('utf-8')}")
    print(f"Received message on {msg.topic}")

    event_type = msg.topic.rsplit("/", 1)[1]
    if event_type == "up":
        chirpstack_uplink_handler(client, msg.payload)
    elif event_type == "join":
        print("Join topic")
    else:
        print("Other topics")

    return
    j = json.loads(msg.payload.decode("utf-8"))
    d = j["data"]
    # print(f"Data: {base64.b64decode(d).hex()}")

    try:
        unpacked_data = parse_c_struct(data=base64.b64decode(d))
    except DataValididty as e:
        print(f"Invalid data. error={e}")
        return

    sender_dev_eui = j["deviceInfo"]["devEui"]
    print(f"NODES === {NODES_ADDR_TO_DEVEUI_MAP.items()}")
    if (
        not (unpacked_data.header.senderAddress.addh, unpacked_data.header.senderAddress.addl)
        in NODES_ADDR_TO_DEVEUI_MAP
    ):
        NODES_ADDR_TO_DEVEUI_MAP[
            (unpacked_data.header.senderAddress.addh, unpacked_data.header.senderAddress.addl)
        ] = sender_dev_eui

    # print(f"{type(client)=} {client=}")
    # print(f"{type(userdata)=} {userdata=}")
    # print(f"{type(msg)=} {msg=}")
    # print(j)
    # print(f"{j["deviceInfo"]["devEui"]=}")

    # garbage_parse_c_struct(data=base64.b64decode(d))

    receiver_dev_eui = NODES_ADDR_TO_DEVEUI_MAP.get(
        (unpacked_data.header.receiverAddress.addh, unpacked_data.header.receiverAddress.addl)
    )
    if not receiver_dev_eui:
        print(
            "receiver_dev_eui does not exist in memory, probably it has not joined to the network"
        )
        return

    # app_id="9e416001-0bc0-4313-9baf-a1df7b7e38d7"
    # dev_eui="ac1f09fffe000000"

    # downlink_payload = json.dumps({
    #     "devEui": f"{dev_eui}",
    #     "confirmed": False,
    #     "fPort": 2,
    #     "data": "SGVsbG8="
    # })

    # time.sleep(4)
    # client.publish(f"application/{app_id}/device/{dev_eui}/command/down", downlink_payload, qos=1)


# 2. Define what happens when the connection is established
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")
    # Subscribe inside on_connect to re-subscribe on auto-reconnects
    client.subscribe("application/+/device/+/event/up", qos=1)
    # client.subscribe("application/+/device/+/event/join", qos=1)


def on_log(client, userdata, paho_log_level, messages):
    if paho_log_level == mqtt.LogLevel.MQTT_LOG_ERR:
        print(messages)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="forwarder-app")
client.on_connect = on_connect
client.on_message = on_message
client.on_log = on_log

counter = 0
# def send_periodic_downlink(app_id, dev_eui, interval_sec=2):
#     downlink_payload = json.dumps({
#         "devEui": dev_eui,
#         "confirmed": False,
#         "fPort": 2,
#         "data": "SGVsbG8="
#     })
#     topic = f"application/{app_id}/device/{dev_eui}/command/down"

#     while True:
#         print(f"Publishing to {topic}")
#         client.publish(topic, downlink_payload, qos=1)
#         print(f"Published")
#         time.sleep(interval_sec)


def send_periodic_downlink(app_id, dev_eui, interval_sec=2):
    topic = f"application/{app_id}/device/{dev_eui}/command/down"

    counter = 0  # Initialize the counter

    while True:
        # print(f"Publishing to {topic}")

        # 1. Convert counter to a string, then to bytes
        data_bytes = str(counter).encode("utf-8")

        # 2. Encode to Base64, then DECODE to a standard string to remove the b''
        b64_string = base64.b64encode(data_bytes).decode("utf-8")

        # 3. Build the payload
        downlink_payload = json.dumps(
            {"devEui": dev_eui, "confirmed": False, "fPort": 2, "data": b64_string}
        )

        # 4. Publish
        client.publish(topic, downlink_payload, qos=1)
        # now = time.strftime("%H:%M:%S.\%f", time.localtime())
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")
        print(f"{now}: Published counter value: {counter} (Base64: {b64_string})")

        counter += 1  # Increment the counter
        time.sleep(interval_sec)


def main_loop(chrpstack_info: ChirpStackInfo):
    client.connect(chrpstack_info.ip, chrpstack_info.port)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()

    # client.loop_start()  # background thread for MQTT I/O

    # app_id="9e416001-0bc0-4313-9baf-a1df7b7e38d7"
    # dev_eui="ac1f09fffe000000"

    # try:
    #     send_periodic_downlink(app_id, dev_eui, interval_sec=1)
    # except KeyboardInterrupt:
    #     client.loop_stop()
    #     client.disconnect()
