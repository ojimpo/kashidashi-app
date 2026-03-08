from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .domain import DEFAULT_LIBRARY, ItemSort, ItemStatus, ItemType
from .models import Item
from .schemas import ItemCreate, ItemUpdate

WRITABLE_FIELDS = (
    "type",
    "title",
    "artist",
    "author",
    "library",
    "borrowed_date",
    "due_date",
    "returned_at",
    "ripped_at",
    "image_url",
    "musicbrainz_release_id",
    "isbn",
    "tmdb_id",
    "metadata_artist",
    "metadata_album",
    "notes",
)
CD_ONLY_FIELDS = ("ripped_at", "musicbrainz_release_id", "metadata_artist", "metadata_album")
BOOK_ONLY_FIELDS = ("isbn",)
DVD_ONLY_FIELDS = ("tmdb_id",)
TOKYO = ZoneInfo("Asia/Tokyo")


def list_items(
    session: Session,
    *,
    item_type: ItemType | None = None,
    status_filter: ItemStatus | None = None,
    library: str | None = None,
    artist: str | None = None,
    author: str | None = None,
    sort: ItemSort = ItemSort.BORROWED_DATE_DESC,
) -> list[Item]:
    stmt: Select[tuple[Item]] = select(Item)

    if item_type is not None:
        stmt = stmt.where(Item.type == item_type)

    if status_filter == ItemStatus.NOT_RIPPED:
        stmt = stmt.where(Item.type == ItemType.CD, Item.ripped_at.is_(None), Item.returned_at.is_(None))
    elif status_filter == ItemStatus.RIPPED:
        stmt = stmt.where(Item.type == ItemType.CD, Item.ripped_at.is_not(None))
    elif status_filter == ItemStatus.NOT_RETURNED:
        stmt = stmt.where(Item.returned_at.is_(None))
    elif status_filter == ItemStatus.RETURNED:
        stmt = stmt.where(Item.returned_at.is_not(None))

    if library:
        stmt = stmt.where(Item.library == library)
    if artist:
        stmt = stmt.where(func.lower(func.coalesce(Item.artist, "")).contains(artist.lower()))
    if author:
        stmt = stmt.where(func.lower(func.coalesce(Item.author, "")).contains(author.lower()))

    stmt = stmt.order_by(*sort_clause(sort))
    return list(session.scalars(stmt).all())


def get_item_or_404(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="資料が見つかりません。")
    return item


def create_item(session: Session, payload: ItemCreate) -> Item:
    values = payload.model_dump()
    values["library"] = values.get("library") or DEFAULT_LIBRARY
    validate_item_state(values)
    ensure_not_duplicate(session, values)

    item = Item(**values)
    session.add(item)
    commit_item(session, values)
    session.refresh(item)
    return item


def update_item(session: Session, item: Item, payload: ItemUpdate) -> Item:
    changes = payload.model_dump(exclude_unset=True)
    for field_name, value in changes.items():
        setattr(item, field_name, value)

    values = item_state(item)
    validate_item_state(values)
    ensure_not_duplicate(session, values, exclude_id=item.id)

    session.add(item)
    commit_item(session, values, exclude_id=item.id)
    session.refresh(item)
    return item


def delete_item(session: Session, item: Item) -> None:
    session.delete(item)
    session.commit()


def sort_clause(sort: ItemSort) -> tuple[object, ...]:
    if sort == ItemSort.BORROWED_DATE_ASC:
        return (Item.borrowed_date.asc(), Item.id.asc())
    if sort == ItemSort.DUE_DATE_ASC:
        return (Item.due_date.asc(), Item.id.asc())
    if sort == ItemSort.DUE_DATE_DESC:
        return (Item.due_date.desc(), Item.id.desc())
    if sort == ItemSort.UPDATED_AT_DESC:
        return (Item.updated_at.desc(), Item.id.desc())
    return (Item.borrowed_date.desc(), Item.id.desc())


def validate_item_state(values: dict[str, object]) -> None:
    errors: list[str] = []
    item_type = values.get("type")
    title = values.get("title")
    library = values.get("library")
    borrowed_date = values.get("borrowed_date")
    due_date = values.get("due_date")
    artist = values.get("artist")
    author = values.get("author")

    if item_type is None:
        errors.append("type は必須です。")
    if not title:
        errors.append("title は必須です。")
    if not library:
        errors.append("library は必須です。")
    if borrowed_date is None:
        errors.append("borrowed_date は必須です。")
    if due_date is None:
        errors.append("due_date は必須です。")
    if isinstance(borrowed_date, date) and isinstance(due_date, date) and due_date < borrowed_date:
        errors.append("due_date は borrowed_date 以降の日付にしてください。")

    if item_type == ItemType.BOOK:
        if not author:
            errors.append("book では author が必須です。")
        if artist:
            errors.append("book では artist を設定できません。")
        errors.extend(require_empty(values, CD_ONLY_FIELDS, "book では CD 用フィールドを設定できません。"))
        errors.extend(require_empty(values, DVD_ONLY_FIELDS, "book では tmdb_id を設定できません。"))
    elif item_type == ItemType.CD:
        if not artist:
            errors.append("cd では artist が必須です。")
        if author:
            errors.append("cd では author を設定できません。")
        errors.extend(require_empty(values, BOOK_ONLY_FIELDS, "cd では isbn を設定できません。"))
        errors.extend(require_empty(values, DVD_ONLY_FIELDS, "cd では tmdb_id を設定できません。"))
    elif item_type == ItemType.DVD:
        if not artist:
            errors.append("dvd では artist が必須です。")
        if author:
            errors.append("dvd では author を設定できません。")
        errors.extend(require_empty(values, CD_ONLY_FIELDS, "dvd では CD 用フィールドを設定できません。"))
        errors.extend(require_empty(values, BOOK_ONLY_FIELDS, "dvd では isbn を設定できません。"))
    elif item_type == ItemType.OTHER:
        errors.extend(require_empty(values, CD_ONLY_FIELDS, "other では CD 用フィールドを設定できません。"))
        errors.extend(require_empty(values, BOOK_ONLY_FIELDS, "other では isbn を設定できません。"))
        errors.extend(require_empty(values, DVD_ONLY_FIELDS, "other では tmdb_id を設定できません。"))

    for field_name in ("returned_at", "ripped_at"):
        field_value = values.get(field_name)
        if isinstance(field_value, datetime) and isinstance(borrowed_date, date):
            if field_value.astimezone(TOKYO).date() < borrowed_date:
                errors.append(f"{field_name} は borrowed_date より前にできません。")

    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)


def require_empty(values: dict[str, object], fields: tuple[str, ...], message: str) -> list[str]:
    return [message] if any(values.get(field_name) is not None for field_name in fields) else []


def item_state(item: Item) -> dict[str, object]:
    return {field_name: getattr(item, field_name) for field_name in WRITABLE_FIELDS}


def ensure_not_duplicate(
    session: Session,
    values: dict[str, object],
    *,
    exclude_id: int | None = None,
) -> None:
    title = values.get("title")
    borrowed_date = values.get("borrowed_date")
    creator = values.get("artist") or values.get("author") or ""

    if not title or not borrowed_date:
        return

    stmt = select(Item.id).where(
        func.lower(Item.title) == str(title).lower(),
        Item.borrowed_date == borrowed_date,
        func.lower(func.coalesce(Item.artist, Item.author, "")) == str(creator).lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(Item.id != exclude_id)

    duplicate_id = session.scalar(stmt)
    if duplicate_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同一資料がすでに登録されています。",
        )


def commit_item(session: Session, values: dict[str, object], exclude_id: int | None = None) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        try:
            ensure_not_duplicate(session, values, exclude_id=exclude_id)
        except HTTPException as duplicate_error:
            raise duplicate_error from exc
        raise
