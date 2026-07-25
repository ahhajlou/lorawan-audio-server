import threading

from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from protocol.models import Address


class Base(DeclarativeBase):
    pass


class DeviceRow(Base):
    __tablename__ = "devices"

    addh: Mapped[int] = mapped_column(primary_key=True)
    addl: Mapped[int] = mapped_column(primary_key=True)
    dev_eui: Mapped[str] = mapped_column(String(16))


class DeviceRegistry:
    def __init__(self, db_url: str = "sqlite:///database.sql"):
        self._engine = create_engine(db_url)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)
        self._eui_to_gateway: dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, addr: Address, dev_eui: str, gateway_id: str) -> None:
        """Map LoRa address -> DevEUI, and DevEUI -> gateway_id.

        gateway_id is taken from the strongest-RSSI entry in the uplink's
        rxInfo list. Thread-safe.
        """
        with self._session_factory() as session:
            exists = session.get(DeviceRow, (addr.addh, addr.addl))
            if not exists:
                session.add(DeviceRow(addh=addr.addh, addl=addr.addl, dev_eui=dev_eui))
                session.commit()
        with self._lock:
            self._eui_to_gateway[dev_eui] = gateway_id

    def lookup_eui(self, addr: Address) -> str | None:
        with self._session_factory() as session:
            row = session.get(DeviceRow, (addr.addh, addr.addl))
            return row.dev_eui if row else None

    def lookup_gateway(self, dev_eui: str) -> str | None:
        """Which gateway_id to target when sending this device a downlink."""
        with self._lock:
            return self._eui_to_gateway.get(dev_eui)
