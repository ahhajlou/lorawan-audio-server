def calculate_crc8(header_bytes: bytes, payload: bytes) -> int:
    crc = 0x00
    for byte in header_bytes:
        crc ^= byte
    for byte in payload:
        crc ^= byte
    return crc


def verify_crc8(header_bytes: bytes, payload_with_crc: bytes) -> bool:
    if not payload_with_crc:
        return False
    crc = 0x00
    for byte in header_bytes:
        crc ^= byte
    for byte in payload_with_crc[:-1]:
        crc ^= byte
    return crc == payload_with_crc[-1]
