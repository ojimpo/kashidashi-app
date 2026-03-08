from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import create_engine_for_url, create_session_factory, init_database
from app.models import Item
from app.domain import ItemType


def test_sqlite_initialization_enables_wal(tmp_path) -> None:
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'journal.db'}")
    init_database(engine)

    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()

    assert journal_mode.lower() == "wal"


def test_unique_index_rejects_duplicate_materials(tmp_path) -> None:
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'unique.db'}")
    init_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        session.add(
            Item(
                type=ItemType.CD,
                title="Duplicate Target",
                artist="Artist",
                library="葛飾区立中央図書館",
                borrowed_date=date(2026, 3, 1),
                due_date=date(2026, 3, 15),
            )
        )
        session.commit()

        session.add(
            Item(
                type=ItemType.CD,
                title="duplicate target",
                artist="artist",
                library="葛飾区立中央図書館",
                borrowed_date=date(2026, 3, 1),
                due_date=date(2026, 3, 16),
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
