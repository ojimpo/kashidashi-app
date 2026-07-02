"""Characterization tests for app/services.py validation and sorting internals.

リファクタリング前に、エラーメッセージの内容と順序・ソート句の対応を固定します。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.domain import ItemSort, ItemType
from app.services import sort_clause, validate_item_state


def base_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "type": ItemType.CD,
        "title": "Future Listening",
        "artist": "The Librarians",
        "author": None,
        "library": "葛飾区立中央図書館",
        "borrowed_date": date(2026, 3, 1),
        "due_date": date(2026, 3, 15),
        "returned_at": None,
        "ripped_at": None,
        "image_url": None,
        "musicbrainz_release_id": None,
        "isbn": None,
        "tmdb_id": None,
        "metadata_artist": None,
        "metadata_album": None,
        "source": None,
        "match_status": None,
        "rip_discid": None,
        "notes": None,
    }
    values.update(overrides)
    return values


def errors_for(values: dict[str, object]) -> list[str]:
    with pytest.raises(HTTPException) as exc_info:
        validate_item_state(values)
    assert exc_info.value.status_code == 422
    return exc_info.value.detail


class TestRequiredFields:
    def test_valid_cd_passes(self) -> None:
        validate_item_state(base_values())

    def test_all_required_fields_missing(self) -> None:
        assert errors_for(
            base_values(type=None, title=None, library=None, borrowed_date=None, due_date=None)
        ) == [
            "type は必須です。",
            "title は必須です。",
            "library は必須です。",
            "borrowed_date は必須です。",
            "due_date は必須です。",
        ]

    def test_due_date_before_borrowed_date(self) -> None:
        assert errors_for(base_values(due_date=date(2026, 2, 28))) == [
            "due_date は borrowed_date 以降の日付にしてください。"
        ]


class TestTypeSpecificRules:
    def test_book_rules(self) -> None:
        assert errors_for(
            base_values(
                type=ItemType.BOOK,
                artist="X",
                author=None,
                ripped_at=datetime(2026, 3, 5, tzinfo=timezone.utc),
                tmdb_id="500",
            )
        ) == [
            "book では author が必須です。",
            "book では artist を設定できません。",
            "book では CD 用フィールドを設定できません。",
            "book では tmdb_id を設定できません。",
        ]

    def test_cd_rules(self) -> None:
        assert errors_for(
            base_values(artist=None, author="X", isbn="978", tmdb_id="500")
        ) == [
            "cd では artist が必須です。",
            "cd では author を設定できません。",
            "cd では isbn を設定できません。",
            "cd では tmdb_id を設定できません。",
        ]

    def test_dvd_rules(self) -> None:
        assert errors_for(
            base_values(
                type=ItemType.DVD,
                artist=None,
                author="X",
                musicbrainz_release_id="mbid",
                isbn="978",
            )
        ) == [
            "dvd では artist が必須です。",
            "dvd では author を設定できません。",
            "dvd では CD 用フィールドを設定できません。",
            "dvd では isbn を設定できません。",
        ]

    def test_other_allows_artist_and_author_but_no_media_fields(self) -> None:
        validate_item_state(base_values(type=ItemType.OTHER, artist="A", author="B"))
        assert errors_for(
            base_values(type=ItemType.OTHER, rip_discid="d", isbn="978", tmdb_id="5")
        ) == [
            "other では CD 用フィールドを設定できません。",
            "other では isbn を設定できません。",
            "other では tmdb_id を設定できません。",
        ]

    def test_cd_only_fields_trigger_single_message(self) -> None:
        # 複数の CD 用フィールドが同時に設定されていてもメッセージは 1 件
        assert errors_for(
            base_values(type=ItemType.BOOK, artist=None, author="X", rip_discid="d", metadata_album="a")
        ) == ["book では CD 用フィールドを設定できません。"]


class TestTimestampRules:
    def test_returned_and_ripped_before_borrowed_date(self) -> None:
        early = datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)
        assert errors_for(base_values(returned_at=early, ripped_at=early)) == [
            "returned_at は borrowed_date より前にできません。",
            "ripped_at は borrowed_date より前にできません。",
        ]

    def test_timestamps_compared_in_jst(self) -> None:
        # UTC では 2/28 でも JST では 3/1 になる時刻は許容される
        utc_edge = datetime(2026, 2, 28, 15, 30, tzinfo=timezone.utc)
        validate_item_state(base_values(returned_at=utc_edge))


class TestSortClause:
    @pytest.mark.parametrize(
        ("sort", "expected"),
        [
            (ItemSort.BORROWED_DATE_DESC, "items.borrowed_date DESC, items.id DESC"),
            (ItemSort.BORROWED_DATE_ASC, "items.borrowed_date ASC, items.id ASC"),
            (ItemSort.DUE_DATE_ASC, "items.due_date ASC, items.id ASC"),
            (ItemSort.DUE_DATE_DESC, "items.due_date DESC, items.id DESC"),
            (ItemSort.UPDATED_AT_DESC, "items.updated_at DESC, items.id DESC"),
        ],
    )
    def test_sort_clause_mapping(self, sort: ItemSort, expected: str) -> None:
        rendered = ", ".join(str(clause) for clause in sort_clause(sort))
        assert rendered == expected
