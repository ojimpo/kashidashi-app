"""Characterization tests for scripts/sync_katsushika_to_kashidashi.py.

現時点の挙動をそのまま固定するテストです（理想の挙動ではありません）。
図書館サイトへの実アクセスは行わず、純粋関数と dry-run 経路のみを対象にします。
"""

from __future__ import annotations

from typing import Any

import sync_katsushika_to_kashidashi as sync


class TestNormalizeText:
    def test_none_and_empty_become_empty_string(self) -> None:
        assert sync.normalize_text(None) == ""
        assert sync.normalize_text("") == ""

    def test_collapses_whitespace_and_lowercases(self) -> None:
        assert sync.normalize_text("  Future   Listening  ") == "future listening"
        assert sync.normalize_text("A\tB\nC") == "a b c"


class TestKeyOf:
    def test_prefers_artist_over_author(self) -> None:
        key = sync.key_of(
            {"title": "T", "artist": "Artist", "author": "Author", "borrowed_date": "2026-03-01"}
        )
        assert key.person == "artist"

    def test_falls_back_to_author_then_empty(self) -> None:
        assert sync.key_of({"title": "T", "author": "Author", "borrowed_date": "2026-03-01"}).person == "author"
        assert sync.key_of({"title": "T", "borrowed_date": "2026-03-01"}).person == ""

    def test_borrowed_date_is_stringified_and_stripped(self) -> None:
        key = sync.key_of({"title": "T", "borrowed_date": " 2026-03-01 "})
        assert key.borrowed_date == "2026-03-01"

    def test_missing_borrowed_date_becomes_empty_string(self) -> None:
        assert sync.key_of({"title": "T"}).borrowed_date == ""


class TestStripTags:
    def test_removes_tags_and_unescapes_entities(self) -> None:
        assert sync.strip_tags("<b>A &amp; B</b>") == "A & B"

    def test_br_becomes_whitespace(self) -> None:
        assert sync.strip_tags("line1<br/>line2") == "line1 line2"
        assert sync.strip_tags("line1<BR >line2") == "line1 line2"

    def test_nbsp_and_runs_of_whitespace_collapse(self) -> None:
        assert sync.strip_tags("a\xa0\xa0 b   c") == "a b c"


class TestJpDateToIso:
    def test_converts_japanese_date(self) -> None:
        assert sync.jp_date_to_iso("2026年3月8日") == "2026-03-08"
        assert sync.jp_date_to_iso("貸出日: 2026年 12月 31日 (木)") == "2026-12-31"

    def test_returns_input_unchanged_when_no_match(self) -> None:
        assert sync.jp_date_to_iso("2026-03-08") == "2026-03-08"
        assert sync.jp_date_to_iso("") == ""


class TestParseDlMap:
    def test_extracts_dt_dd_pairs(self) -> None:
        block = "<dl><dt>貸出日</dt><dd>2026年3月1日</dd><dt>返却期限</dt> <dd><b>2026年3月15日</b></dd></dl>"
        assert sync.parse_dl_map(block) == {
            "貸出日": "2026年3月1日",
            "返却期限": "2026年3月15日",
        }

    def test_empty_block_returns_empty_map(self) -> None:
        assert sync.parse_dl_map("<p>no dl here</p>") == {}


class TestParseDetailFields:
    def test_extracts_th_scope_row_pairs(self) -> None:
        html_text = (
            '<table><tr><th scope="row">タイトル</th><td>Future Listening</td></tr>'
            '<tr><th scope="row">著作者</th><td>The Librarians</td></tr></table>'
        )
        assert sync.parse_detail_fields(html_text) == {
            "タイトル": "Future Listening",
            "著作者": "The Librarians",
        }

    def test_skips_pairs_with_empty_key_or_value(self) -> None:
        html_text = '<th scope="row">空</th><td></td><th scope="row">残す</th><td>値</td>'
        assert sync.parse_detail_fields(html_text) == {"残す": "値"}


class TestMapType:
    def test_cd_keywords(self) -> None:
        assert sync.map_type({"資料形態": "コンパクトディスク"}) == "cd"
        assert sync.map_type({"数量": "CD 1枚"}) == "cd"
        assert sync.map_type({"資料形態": "録音資料"}) == "cd"

    def test_dvd_keywords(self) -> None:
        assert sync.map_type({"資料形態": "DVD"}) == "dvd"
        assert sync.map_type({"資料形態": "ビデオディスク"}) == "dvd"

    def test_book_keywords_and_publisher_fallback(self) -> None:
        assert sync.map_type({"資料形態": "図書"}) == "book"
        assert sync.map_type({"数量": "1冊"}) == "book"
        assert sync.map_type({"出版社": "SomePub"}) == "book"
        assert sync.map_type({"ISBN": "9781234567890"}) == "book"

    def test_unknown_becomes_other(self) -> None:
        assert sync.map_type({}) == "other"
        assert sync.map_type({"資料形態": "紙芝居"}) == "other"

    def test_cd_takes_priority_over_book_keywords(self) -> None:
        # 「録音図書」のように両方のキーワードを含む場合は CD 判定が先勝ちする（現状の挙動）
        assert sync.map_type({"資料形態": "録音図書"}) == "cd"


class FakeResponse:
    def __init__(self, payload: list[dict[str, Any]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> list[dict[str, Any]]:
        return self._payload


class TestImportItemsDryRun:
    def test_dry_run_skips_existing_and_counts_new(self, monkeypatch) -> None:
        existing = [
            {"title": "Future Listening", "artist": "The Librarians", "borrowed_date": "2026-03-01"}
        ]
        monkeypatch.setattr(sync.requests, "get", lambda url, timeout: FakeResponse(existing))

        items = [
            # 既存と同一キー（大文字小文字・空白差は無視される）
            {"title": " future  listening ", "artist": "THE LIBRARIANS", "borrowed_date": "2026-03-01"},
            {"title": "New Disc", "artist": "Somebody", "borrowed_date": "2026-03-02"},
            # dry-run 中の重複も 2 件目以降はスキップされる
            {"title": "New Disc", "artist": "Somebody", "borrowed_date": "2026-03-02"},
        ]
        summary = sync.import_items("http://localhost:18080", items, dry_run=True)

        assert summary["fetched"] == 3
        assert summary["inserted"] == 1
        assert summary["skipped"] == 2
        assert summary["errors"] == 0
        assert summary["inserted_items"] == [items[1]]
