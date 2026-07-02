from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .domain import DEFAULT_LIBRARY, ItemSort, ItemSource, ItemStatus, ItemType, MatchStatus
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
    "source",
    "match_status",
    "rip_discid",
    "notes",
)
CD_ONLY_FIELDS = ("ripped_at", "musicbrainz_release_id", "metadata_artist", "metadata_album", "rip_discid")
BOOK_ONLY_FIELDS = ("isbn",)
DVD_ONLY_FIELDS = ("tmdb_id",)
TOKYO = ZoneInfo("Asia/Tokyo")

# 種別ごとの作成者フィールド: (必須フィールド, 設定できないフィールド)
PERSON_FIELDS_BY_TYPE = {
    ItemType.BOOK: ("author", "artist"),
    ItemType.CD: ("artist", "author"),
    ItemType.DVD: ("artist", "author"),
}

# 各種別の専用フィールドグループ: (所有する種別, フィールド群, エラー文言のラベル。助詞「を」まで含む)
EXCLUSIVE_FIELD_GROUPS = (
    (ItemType.CD, CD_ONLY_FIELDS, "CD 用フィールドを"),
    (ItemType.BOOK, BOOK_ONLY_FIELDS, "isbn を"),
    (ItemType.DVD, DVD_ONLY_FIELDS, "tmdb_id を"),
)


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
    values["source"] = values.get("source") or ItemSource.LIBRARY
    values["match_status"] = values.get("match_status") or MatchStatus.MATCHED
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
    borrowed_date = values.get("borrowed_date")
    due_date = values.get("due_date")

    if item_type is None:
        errors.append("type は必須です。")
    if not values.get("title"):
        errors.append("title は必須です。")
    if not values.get("library"):
        errors.append("library は必須です。")
    if borrowed_date is None:
        errors.append("borrowed_date は必須です。")
    if due_date is None:
        errors.append("due_date は必須です。")
    if isinstance(borrowed_date, date) and isinstance(due_date, date) and due_date < borrowed_date:
        errors.append("due_date は borrowed_date 以降の日付にしてください。")

    if item_type in ItemType:
        errors.extend(type_specific_errors(values, item_type))

    for field_name in ("returned_at", "ripped_at"):
        field_value = values.get(field_name)
        if isinstance(field_value, datetime) and isinstance(borrowed_date, date):
            if field_value.astimezone(TOKYO).date() < borrowed_date:
                errors.append(f"{field_name} は borrowed_date より前にできません。")

    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)


def type_specific_errors(values: dict[str, object], item_type: ItemType) -> list[str]:
    errors: list[str] = []
    person_fields = PERSON_FIELDS_BY_TYPE.get(item_type)
    if person_fields is not None:
        required_field, forbidden_field = person_fields
        if not values.get(required_field):
            errors.append(f"{item_type} では {required_field} が必須です。")
        if values.get(forbidden_field):
            errors.append(f"{item_type} では {forbidden_field} を設定できません。")
    for owner_type, fields, label in EXCLUSIVE_FIELD_GROUPS:
        if owner_type != item_type:
            errors.extend(require_empty(values, fields, f"{item_type} では {label}設定できません。"))
    return errors


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
