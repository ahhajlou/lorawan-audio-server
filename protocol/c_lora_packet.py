from cffi import FFI

"""
Chirpstack error
level:"ERROR"
code:"DOWNLINK_PAYLOAD_SIZE"
description:"Device queue-item discarded because it exceeds the max. payload size"
max_payload_size:"51"
item_size:"52"
"""
ESP32_LORA_STRUCT_CDEF = """
#define LORA_PAYLOAD_SIZE_PLUS_CRC 43

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


def get_ffi() -> FFI:
    ffi = FFI()
    ffi.cdef(ESP32_LORA_STRUCT_CDEF, pack=1)
    return ffi
