"""Characterization tests for the event/notification helper scripts.

- scripts/sync_katsushika_with_events.py の digest_items / item_to_line
- scripts/emit_kashidashi_event_message.py の CLI 挙動

現時点の挙動をそのまま固定するテストです。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sync_katsushika_with_events import digest_items, item_to_line

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
EMIT_SCRIPT = SCRIPTS_DIR / "emit_kashidashi_event_message.py"


def sample_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "type": "cd",
        "title": "Future Listening",
        "artist": "The Librarians",
        "borrowed_date": "2026-03-01",
        "due_date": "2026-03-15",
    }
    item.update(overrides)
    return item


class TestItemToLine:
    def test_uses_artist_when_present(self) -> None:
        assert (
            item_to_line(sample_item())
            == "- [cd] Future Listening / The Librarians / 2026-03-01→2026-03-15"
        )

    def test_falls_back_to_author_then_dash(self) -> None:
        book = sample_item(type="book", artist=None, author="Author X")
        assert item_to_line(book) == "- [book] Future Listening / Author X / 2026-03-01→2026-03-15"
        anonymous = sample_item(artist=None)
        assert item_to_line(anonymous) == "- [cd] Future Listening / - / 2026-03-01→2026-03-15"


class TestDigestItems:
    def test_digest_is_order_independent(self) -> None:
        a = sample_item(title="Alpha")
        b = sample_item(title="Beta", borrowed_date="2026-03-02")
        assert digest_items([a, b]) == digest_items([b, a])

    def test_digest_changes_with_content(self) -> None:
        assert digest_items([sample_item()]) != digest_items([sample_item(due_date="2026-03-16")])

    def test_digest_ignores_fields_outside_serialized_set(self) -> None:
        # notes や isbn などは digest 対象外（現状の仕様）
        assert digest_items([sample_item()]) == digest_items([sample_item(notes="extra")])

    def test_known_digest_stays_stable(self) -> None:
        # このハッシュ値が変わると、通知の重複抑制 (last_sent_digest) がリセットされる
        assert digest_items([sample_item()]) == (
            "5abe9303f9cfebf5a2ec2e1c653f6c9ea1140c9b8f941545cd5236993d4fc9b9"
        )


def run_emit(state_dir: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EMIT_SCRIPT), "--state-dir", str(state_dir), *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestEmitEventMessage:
    def test_no_event_file_prints_no_change(self, tmp_path: Path) -> None:
        result = run_emit(tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "NO_CHANGE"

    def test_unchanged_event_prints_no_change(self, tmp_path: Path) -> None:
        (tmp_path / "katsushika_last_event.json").write_text(
            json.dumps({"changed": False, "snapshot_digest": "abc", "message": "msg"}),
            encoding="utf-8",
        )
        result = run_emit(tmp_path)
        assert result.stdout.strip() == "NO_CHANGE"

    def test_changed_event_prints_message_and_consume_records_digest(self, tmp_path: Path) -> None:
        (tmp_path / "katsushika_last_event.json").write_text(
            json.dumps({"changed": True, "snapshot_digest": "abc", "message": "hello"}),
            encoding="utf-8",
        )

        without_consume = run_emit(tmp_path)
        assert without_consume.stdout.strip() == "hello"
        assert not (tmp_path / "katsushika_last_sent_digest.txt").exists()

        with_consume = run_emit(tmp_path, "--consume")
        assert with_consume.stdout.strip() == "hello"
        assert (tmp_path / "katsushika_last_sent_digest.txt").read_text(encoding="utf-8") == "abc\n"

        # digest 送信済みになったので、同じイベントは NO_CHANGE になる
        after_consume = run_emit(tmp_path)
        assert after_consume.stdout.strip() == "NO_CHANGE"
