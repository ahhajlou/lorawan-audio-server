from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from protocol.models import Address
from registry.models import Base, DeviceRow


class DeviceRegistry:
    def __init__(self, db_url: str = "sqlite:///database.sql"):
        self._engine = create_engine(db_url)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)

    def register(self, addr: Address, dev_eui: str) -> None:
        with self._session_factory() as session:
            exists = session.get(DeviceRow, (addr.addh, addr.addl))
            if not exists:
                session.add(DeviceRow(addh=addr.addh, addl=addr.addl, dev_eui=dev_eui))
                session.commit()

    def lookup(self, addr: Address) -> str | None:
        with self._session_factory() as session:
            row = session.get(DeviceRow, (addr.addh, addr.addl))
            return row.dev_eui if row else None
