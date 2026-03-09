#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sync_katsushika_to_kashidashi import (
    fetch_current_loans,
    get_credentials,
    import_items,
    key_of,
)


def item_to_line(item: dict[str, Any]) -> str:
    who = item.get("artist") or item.get("author") or "-"
    return f"- [{item.get('type')}] {item.get('title')} / {who} / {item.get('borrowed_date')}→{item.get('due_date')}"


def digest_items(items: list[dict[str, Any]]) -> str:
    serial = [
        {
            "type": i.get("type"),
            "title": i.get("title"),
            "artist": i.get("artist"),
            "author": i.get("author"),
            "borrowed_date": i.get("borrowed_date"),
            "due_date": i.get("due_date"),
        }
        for i in sorted(items, key=lambda x: (x.get("title") or "", x.get("borrowed_date") or ""))
    ]
    raw = json.dumps(serial, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:18080")
    ap.add_argument("--vault", default="OpenClaw")
    ap.add_argument("--item", default="Katsushika")
    ap.add_argument("--state-dir", default="/home/kouki/dev/kashidashi-app/state")
    ap.add_argument("--out", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = state_dir / "katsushika_current_loans.json"
    last_event_path = state_dir / "katsushika_last_event.json"

    username, password = get_credentials(args.vault, args.item)
    current = fetch_current_loans(username, password)

    prev: list[dict[str, Any]] = []
    if snapshot_path.exists():
        prev = json.loads(snapshot_path.read_text(encoding="utf-8"))

    prev_map = {key_of(i): i for i in prev}
    curr_map = {key_of(i): i for i in current}

    newly_borrowed = [curr_map[k] for k in curr_map.keys() - prev_map.keys()]
    returned = [prev_map[k] for k in prev_map.keys() - curr_map.keys()]

    import_summary = import_items(args.base_url, current, dry_run=args.dry_run)

    event = {
        "changed": bool(newly_borrowed or returned),
        "newly_borrowed": newly_borrowed,
        "returned": returned,
        "snapshot_digest": digest_items(current),
        "fetched": import_summary["fetched"],
        "inserted": import_summary["inserted"],
        "skipped": import_summary["skipped"],
        "errors": import_summary["errors"],
        "message": "\n".join(
            [
                "[kashidashi] 貸出状況に変更がありました" if (newly_borrowed or returned) else "[kashidashi] 変更なし",
                f"取得: {import_summary['fetched']} / 新規登録: {import_summary['inserted']} / 既存スキップ: {import_summary['skipped']} / エラー: {import_summary['errors']}",
                ("\n新規貸出:\n" + "\n".join(item_to_line(i) for i in newly_borrowed)) if newly_borrowed else "",
                ("\n返却:\n" + "\n".join(item_to_line(i) for i in returned)) if returned else "",
            ]
        ).strip(),
    }

    snapshot_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    last_event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = {**import_summary, "event": event}
    text = json.dumps(output, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    return 0 if import_summary["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
