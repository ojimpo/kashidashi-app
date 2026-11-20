#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import requests

from backfill_returned_at_from_history import (
    fetch_history_return_map,
    load_title_alias_map,
    norm_title,
    title_keys_for_match,
)
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


def mark_returned_items(
    base_url: str,
    current: list[dict[str, Any]],
    history_return_map: dict[tuple[str, str], str],
    alias_map: dict[str, list[str]],
    dry_run: bool = False,
) -> dict[str, Any]:
    items_url = base_url.rstrip("/") + "/api/items"
    existing = requests.get(items_url, timeout=20)
    existing.raise_for_status()
    all_items = existing.json()

    # strict key sometimes fails when artist/author表記が揺れるため、返却判定は title+borrowed_date を優先
    def loose_key(item: dict[str, Any]) -> tuple[str, str]:
        title = " ".join(str(item.get("title") or "").strip().split()).lower()
        borrowed = str(item.get("borrowed_date") or "").strip()
        return (title, borrowed)

    current_strict_keys = {key_of(i) for i in current}
    current_loose_keys = {loose_key(i) for i in current}

    marked: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for it in all_items:
        if it.get("returned_at"):
            continue

        # still on loan if either strict or loose key matches current page
        if key_of(it) in current_strict_keys or loose_key(it) in current_loose_keys:
            continue

        # Use real returned date from rental history (date-only). If missing, keep item untouched.
        borrowed = str(it.get("borrowed_date") or "")
        ret_date = None
        for tk in title_keys_for_match(it.get("title"), alias_map):
            ret_date = history_return_map.get((tk, borrowed))
            if ret_date:
                break
        if not ret_date:
            unresolved.append({"id": it.get("id"), "title": it.get("title"), "borrowed_date": it.get("borrowed_date")})
            continue

        returned_at_iso = f"{ret_date}T00:00:00Z"

        if dry_run:
            marked.append({"id": it.get("id"), "title": it.get("title"), "returned_at": returned_at_iso})
            continue

        try:
            patch_payload = {"returned_at": returned_at_iso}
            # defensive: preserve ripped_at for CDs even if backend treats absent nullable fields aggressively
            if it.get("type") == "cd" and it.get("ripped_at"):
                patch_payload["ripped_at"] = it.get("ripped_at")
            r = requests.patch(f"{items_url}/{it['id']}", json=patch_payload, timeout=20)
            r.raise_for_status()
            marked.append({"id": it.get("id"), "title": it.get("title"), "returned_at": returned_at_iso})
        except Exception as e:  # noqa: BLE001
            errors.append({"id": it.get("id"), "title": it.get("title"), "error": str(e)})

    return {"marked_returned": marked, "return_unresolved": unresolved, "return_errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:18080")
    ap.add_argument("--vault", default="OpenClaw")
    ap.add_argument("--item", default="Katsushika")
    ap.add_argument("--state-dir", default="/home/kouki/clawd/scripts/kashidashi-sync/state")
    ap.add_argument("--out", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = state_dir / "katsushika_current_loans.json"
    last_event_path = state_dir / "katsushika_last_event.json"

    username, password = get_credentials(args.vault, args.item)
    current = fetch_current_loans(username, password)
    # Only history back to the oldest still-open loan can resolve a return,
    # so bound the history walk by that date instead of paging everything.
    open_dates: list[str] = []
    api_ok = True
    try:
        existing_resp = requests.get(args.base_url.rstrip("/") + "/api/items", timeout=20)
        existing_resp.raise_for_status()
        open_dates = [
            str(i.get("borrowed_date"))
            for i in existing_resp.json()
            if not i.get("returned_at") and i.get("borrowed_date")
        ]
    except Exception:  # noqa: BLE001
        api_ok = False
    if api_ok and not open_dates:
        history_return_map: dict[tuple[str, str], str] = {}
    else:
        history_return_map = fetch_history_return_map(
            username, password, min_loan_date=min(open_dates) if open_dates else None
        )
    alias_map = load_title_alias_map()

    prev: list[dict[str, Any]] = []
    if snapshot_path.exists():
        prev = json.loads(snapshot_path.read_text(encoding="utf-8"))

    prev_map = {key_of(i): i for i in prev}
    curr_map = {key_of(i): i for i in current}

    newly_borrowed = [curr_map[k] for k in curr_map.keys() - prev_map.keys()]
    returned = [prev_map[k] for k in prev_map.keys() - curr_map.keys()]

    import_summary = import_items(args.base_url, current, dry_run=args.dry_run)
    return_summary = mark_returned_items(args.base_url, current, history_return_map, alias_map, dry_run=args.dry_run)

    event = {
        "changed": bool(newly_borrowed or returned or return_summary['marked_returned']),
        "newly_borrowed": newly_borrowed,
        "returned": returned,
        "snapshot_digest": digest_items(current),
        "fetched": import_summary["fetched"],
        "inserted": import_summary["inserted"],
        "skipped": import_summary["skipped"],
        "errors": import_summary["errors"],
        "return_marked_count": len(return_summary["marked_returned"]),
        "message": "\n".join(
            [
                "[kashidashi] 貸出状況に変更がありました" if (newly_borrowed or returned or return_summary['marked_returned']) else "[kashidashi] 変更なし",
                f"取得: {import_summary['fetched']} / 新規登録: {import_summary['inserted']} / 既存スキップ: {import_summary['skipped']} / エラー: {import_summary['errors']} / 返却反映: {len(return_summary['marked_returned'])} / 返却未確定: {len(return_summary['return_unresolved'])}",
                ("\n新規貸出:\n" + "\n".join(item_to_line(i) for i in newly_borrowed)) if newly_borrowed else "",
                ("\n返却(貸出一覧から消えた):\n" + "\n".join(item_to_line(i) for i in returned)) if returned else "",
            ]
        ).strip(),
    }

    snapshot_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    last_event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = {**import_summary, **return_summary, "event": event}
    text = json.dumps(output, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    return 0 if import_summary["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
