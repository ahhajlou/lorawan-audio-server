class AppError(Exception):
    """Base for all application errors."""


class ConnectionError(AppError):
    """MQTT broker unreachable or auth failed."""


class ProtocolError(AppError):
    """Malformed packet, invalid CRC, bad struct."""


class DeviceUnknown(AppError):
    """Sender or receiver address not in registry."""


class ParseError(AppError):
    # Raised when parsing input data fails.
    def __init__(self, message, *, name: str | None = None):
        super().__init__(message)
        self.name = name
