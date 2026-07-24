from protocol.crc import calculate_crc8, verify_crc8


class TestCalculateCrc8:
    def test_empty(self):
        assert calculate_crc8(b"", b"") == 0

    def test_single_header_byte(self):
        assert calculate_crc8(b"\x01", b"") == 0x01

    def test_single_payload_byte(self):
        assert calculate_crc8(b"", b"\x01") == 0x01

    def test_known_value(self):
        header = b"\x01\x00\x03\x00\x05\x01\x00\x03"
        payload = b"\x41\x42\x43"
        crc = calculate_crc8(header, payload)
        expected = 0
        for b in header:
            expected ^= b
        for b in payload:
            expected ^= b
        assert crc == expected

    def test_all_zeros(self):
        header = b"\x00\x00\x00\x00\x00\x00\x00\x00"
        payload = b"\x00\x00\x00"
        assert calculate_crc8(header, payload) == 0

    def test_all_ff_even_count(self):
        header = b"\xff" * 4
        payload = b"\xff" * 4
        assert calculate_crc8(header, payload) == 0

    def test_all_ff_odd_count(self):
        header = b"\xff" * 4
        payload = b"\xff" * 3
        assert calculate_crc8(header, payload) == 0xFF


class TestVerifyCrc8:
    def test_empty_payload_returns_false(self):
        assert verify_crc8(b"\x01", b"") is False

    def test_valid_crc(self):
        header = b"\x01\x00\x03\x00\x05\x01\x00\x03"
        payload = b"\x41\x42\x43"
        crc = calculate_crc8(header, payload)
        assert verify_crc8(header, payload + bytes([crc])) is True

    def test_invalid_crc(self):
        header = b"\x01\x00\x03\x00\x05\x01\x00\x03"
        payload = b"\x41\x42\x43"
        assert verify_crc8(header, payload + bytes([0x00])) is False

    def test_single_byte_just_crc(self):
        header = b"\x01"
        crc = calculate_crc8(header, b"")
        assert verify_crc8(header, bytes([crc])) is True

    def test_roundtrip_various_lengths(self):
        for plen in range(0, 20):
            header = bytes(range(8))
            payload = bytes(range(plen))
            crc = calculate_crc8(header, payload)
            assert verify_crc8(header, payload + bytes([crc])) is True
