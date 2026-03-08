from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Enum, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, UTCDateTime
from .domain import DEFAULT_LIBRARY, ItemType, utc_now


ITEM_TYPE_ENUM = Enum(
    ItemType,
    name="item_type",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[ItemType] = mapped_column(ITEM_TYPE_ENUM, index=True)
    title: Mapped[str] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    library: Mapped[str] = mapped_column(Text, nullable=False, default=DEFAULT_LIBRARY, index=True)
    borrowed_date: Mapped[date] = mapped_column(index=True)
    due_date: Mapped[date] = mapped_column(index=True)
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    ripped_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    musicbrainz_release_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    isbn: Mapped[str | None] = mapped_column(Text, nullable=True)
    tmdb_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_artist: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_album: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    __table_args__ = (
        Index(
            "uq_items_dedup",
            func.lower(title),
            borrowed_date,
            func.lower(func.coalesce(artist, author, "")),
            unique=True,
        ),
    )
