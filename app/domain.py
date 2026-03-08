from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

DEFAULT_LIBRARY = "葛飾区立中央図書館"
JST_TIMEZONE = "Asia/Tokyo"


class ItemType(StrEnum):
    CD = "cd"
    BOOK = "book"
    DVD = "dvd"
    OTHER = "other"


class ItemStatus(StrEnum):
    NOT_RIPPED = "not_ripped"
    NOT_RETURNED = "not_returned"
    RIPPED = "ripped"
    RETURNED = "returned"


class ItemSort(StrEnum):
    BORROWED_DATE_DESC = "borrowed_date_desc"
    BORROWED_DATE_ASC = "borrowed_date_asc"
    DUE_DATE_ASC = "due_date_asc"
    DUE_DATE_DESC = "due_date_desc"
    UPDATED_AT_DESC = "updated_at_desc"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

