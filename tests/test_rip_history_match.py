"""Characterization tests for scripts/rip_history_match.py.

現時点の照合ロジックの挙動をそのまま固定するテストです。
NAS 上の実ディレクトリには依存せず、monkeypatch と tmp_path で完結させます。
"""

from __future__ import annotations

import json

import rip_history_match as rhm
from rip_history_match import RipRecord


class TestNorm:
    def test_empty_and_none(self) -> None:
        assert rhm.norm(None) == ""
        assert rhm.norm("") == ""

    def test_lowercases_and_strips_symbols(self) -> None:
        assert rhm.norm("Future Listening!") == "futurelistening"
        # 長音符「ー」はカタカナ許容範囲(ァ-ヶ)に含まれず除去される（現状の挙動）
        assert rhm.norm("ハート・ビート") == "ハトビト"

    def test_tilde_variants_unified_then_removed(self) -> None:
        # 〜 と ～ は ~ に寄せられた後、記号として除去される
        assert rhm.norm("A〜B") == rhm.norm("A～B") == "ab"

    def test_disc_numbers_removed(self) -> None:
        assert rhm.norm("Best Album (Disc 1)") == "bestalbum"
        assert rhm.norm("Best Album [disc-2]") == "bestalbum"
        assert rhm.norm("Best Album Disc3") == "bestalbum"

    def test_keeps_japanese_and_alnum(self) -> None:
        assert rhm.norm("宇宙のRhythm 2") == "宇宙のrhythm2"


class TestRipTimeFromDirname:
    def test_valid_dirname(self) -> None:
        assert rhm._rip_time_from_dirname("rip_20260305T123456Z") == "2026-03-05T12:34:56Z"

    def test_invalid_dirname_returns_none(self) -> None:
        assert rhm._rip_time_from_dirname("rip_notadate") is None
        assert rhm._rip_time_from_dirname("other_20260305T123456Z") is None


def record(ripped_at: str, title: str, artist: str = "") -> RipRecord:
    return RipRecord(ripped_at=ripped_at, title_norm=rhm.norm(title), artist_norm=rhm.norm(artist))


class TestFindRippedAt:
    def test_exact_title_match_within_window(self) -> None:
        records = [record("2026-03-02T10:00:00Z", "Future Listening")]
        assert (
            rhm.find_ripped_at("Future Listening", None, "2026-03-01", records)
            == "2026-03-02T10:00:00Z"
        )

    def test_rip_outside_3day_window_is_ignored(self) -> None:
        records = [record("2026-03-10T10:00:00Z", "Future Listening")]
        assert rhm.find_ripped_at("Future Listening", None, "2026-03-01", records) is None

    def test_rip_before_borrow_date_is_ignored(self) -> None:
        records = [record("2026-02-28T10:00:00Z", "Future Listening")]
        assert rhm.find_ripped_at("Future Listening", None, "2026-03-01", records) is None

    def test_no_borrowed_date_matches_any_time(self) -> None:
        records = [record("2020-01-01T00:00:00Z", "Future Listening")]
        assert rhm.find_ripped_at("Future Listening", None, None, records) == "2020-01-01T00:00:00Z"

    def test_loose_containment_match(self) -> None:
        records = [record("2026-03-02T10:00:00Z", "Future Listening (Deluxe Edition)")]
        assert (
            rhm.find_ripped_at("Future Listening", None, "2026-03-01", records)
            == "2026-03-02T10:00:00Z"
        )

    def test_artist_fallback_only_when_unique(self) -> None:
        records = [
            record("2026-03-02T10:00:00Z", "英語タイトル", "Spitz"),
        ]
        # タイトルが照合できなくても、期間内のアーティスト一致が 1 件だけなら採用される
        assert (
            rhm.find_ripped_at("日本語タイトル", "Spitz", "2026-03-01", records)
            == "2026-03-02T10:00:00Z"
        )

        records.append(record("2026-03-03T10:00:00Z", "別のアルバム", "Spitz"))
        # 2 件以上に増えると曖昧なので採用しない
        assert rhm.find_ripped_at("日本語タイトル", "Spitz", "2026-03-01", records) is None

    def test_latest_candidate_wins(self) -> None:
        records = [
            record("2026-03-02T10:00:00Z", "Future Listening"),
            record("2026-03-03T10:00:00Z", "Future Listening"),
        ]
        assert (
            rhm.find_ripped_at("Future Listening", None, "2026-03-01", records)
            == "2026-03-03T10:00:00Z"
        )

    def test_empty_title_never_matches_title_paths(self) -> None:
        records = [record("2026-03-02T10:00:00Z", "Future Listening")]
        assert rhm.find_ripped_at("", None, "2026-03-01", records) is None


class TestLoadRipRecords:
    def test_reads_meta_json_and_applies_aliases(self, tmp_path, monkeypatch) -> None:
        rip_dir = tmp_path / "rip_20260305T120000Z"
        rip_dir.mkdir()
        (rip_dir / "meta.json").write_text(
            json.dumps({"album": "Real Title", "artist": "Artist"}), encoding="utf-8"
        )
        broken_dir = tmp_path / "rip_20260306T120000Z"
        broken_dir.mkdir()
        (broken_dir / "meta.json").write_text("{not json", encoding="utf-8")
        ignored_dir = tmp_path / "rip_badname"
        ignored_dir.mkdir()
        (ignored_dir / "meta.json").write_text(json.dumps({"album": "X"}), encoding="utf-8")

        alias_path = tmp_path / "aliases.json"
        alias_path.write_text(json.dumps({"Real Title": ["Alias Title"]}), encoding="utf-8")

        monkeypatch.setattr(rhm, "RIP_ROOT", tmp_path)
        monkeypatch.setattr(rhm, "ALIAS_PATH", alias_path)

        records = rhm.load_rip_records()

        assert [(r.title_norm, r.ripped_at) for r in records] == [
            ("realtitle", "2026-03-05T12:00:00Z"),
            ("aliastitle", "2026-03-05T12:00:00Z"),
        ]

    def test_missing_alias_file_is_tolerated(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(rhm, "RIP_ROOT", tmp_path)
        monkeypatch.setattr(rhm, "ALIAS_PATH", tmp_path / "does-not-exist.json")
        assert rhm.load_rip_records() == []
