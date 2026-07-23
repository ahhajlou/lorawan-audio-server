from cffi import FFI

import exceptions
from protocol.crc import verify_crc8
from protocol.models import Address, MsgType, Packet

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


def parse(decoded_payload: bytes) -> Packet:
    ffi = FFI()
    ffi.cdef(ESP32_LORA_STRUCT_CDEF, pack=1)

    header_size = ffi.sizeof("Header")
    if len(decoded_payload) < header_size:
        raise exceptions.ProtocolError(
            f"Payload too short: {len(decoded_payload)} bytes < {header_size} header"
        )

    unpacked_data = ffi.from_buffer("struct LoRaData *", decoded_payload)

    try:
        msg_type = MsgType(unpacked_data.header.type)
    except ValueError as err:
        raise exceptions.ProtocolError(
            f"Unknown message type: 0x{unpacked_data.header.type:02x}"
        ) from err

    if unpacked_data.header.payload_and_crc_len <= 0:
        raise exceptions.ProtocolError("header.payload_and_crc_len <= 0")

    payload_end = header_size + unpacked_data.header.payload_and_crc_len
    if payload_end > len(decoded_payload):
        raise exceptions.ProtocolError(
            f"Payload too short for declared length: need {payload_end}, got {len(decoded_payload)}"
        )

    header_bytes = decoded_payload[:header_size]
    payload_and_crc = decoded_payload[header_size:payload_end]
    crc_valid = verify_crc8(header_bytes, payload_and_crc)

    payload = payload_and_crc[:-1] if unpacked_data.header.payload_and_crc_len > 0 else b""

    return Packet(
        msg_type=msg_type,
        sender=Address(
            addh=unpacked_data.header.senderAddress.addh,
            addl=unpacked_data.header.senderAddress.addl,
        ),
        receiver=Address(
            addh=unpacked_data.header.receiverAddress.addh,
            addl=unpacked_data.header.receiverAddress.addh,
        ),
        seq=unpacked_data.header.seq,
        payload=payload,
        crc_valid=crc_valid,
    )
