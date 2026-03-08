from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from .domain import DEFAULT_LIBRARY, ItemSort, ItemType, ensure_utc

TEXT_FIELDS = (
    "title",
    "artist",
    "author",
    "library",
    "image_url",
    "musicbrainz_release_id",
    "isbn",
    "tmdb_id",
    "metadata_artist",
    "metadata_album",
    "notes",
)


class ItemPayloadBase(BaseModel):
    type: ItemType | None = None
    title: str | None = None
    artist: str | None = None
    author: str | None = None
    library: str | None = None
    borrowed_date: date | None = None
    due_date: date | None = None
    returned_at: datetime | None = None
    ripped_at: datetime | None = None
    image_url: str | None = None
    musicbrainz_release_id: str | None = None
    isbn: str | None = None
    tmdb_id: str | None = None
    metadata_artist: str | None = None
    metadata_album: str | None = None
    notes: str | None = None

    @field_validator(*TEXT_FIELDS, mode="before")
    @classmethod
    def normalize_text(cls, value: object, info: object) -> object:
        del cls
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if info.field_name == "title" and not stripped:
            raise ValueError("title must not be empty")
        return stripped or None

    @model_validator(mode="after")
    def normalize_datetimes(self) -> "ItemPayloadBase":
        self.returned_at = ensure_utc(self.returned_at)
        self.ripped_at = ensure_utc(self.ripped_at)
        return self


class ItemCreate(ItemPayloadBase):
    type: ItemType
    title: str
    borrowed_date: date
    due_date: date
    library: str | None = DEFAULT_LIBRARY

    @model_validator(mode="after")
    def apply_library_default(self) -> "ItemCreate":
        if self.library is None:
            self.library = DEFAULT_LIBRARY
        return self


class ItemUpdate(ItemPayloadBase):
    pass


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ItemType
    title: str
    artist: str | None
    author: str | None
    library: str
    borrowed_date: date
    due_date: date
    returned_at: datetime | None
    ripped_at: datetime | None
    image_url: str | None
    musicbrainz_release_id: str | None
    isbn: str | None
    tmdb_id: str | None
    metadata_artist: str | None
    metadata_album: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("returned_at", "ripped_at", "created_at", "updated_at", when_used="json")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return ensure_utc(value).isoformat().replace("+00:00", "Z")


class ItemListQuery(BaseModel):
    type: ItemType | None = None
    status: str | None = None
    library: str | None = None
    artist: str | None = None
    author: str | None = None
    sort: ItemSort = ItemSort.BORROWED_DATE_DESC

