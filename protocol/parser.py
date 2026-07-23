from .models import Packet


def parse(decoded_payload: bytes) -> Packet:
    """Pure function. bytes → Packet. Raises on invalid data."""
