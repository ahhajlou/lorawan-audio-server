class AppError(Exception):
    """Base for all application errors."""


class ConnectionError(AppError):
    """MQTT broker unreachable or auth failed."""


class ProtocolError(AppError):
    """Malformed packet, invalid CRC, bad struct."""


class DeviceUnknown(AppError):
    """Sender or receiver address not in registry."""
