#!/usr/bin/env python3
"""Sync currently borrowed items from Katsushika library into kashidashi.

- Credentials are fetched from 1Password item (vault/item configurable)
- Dedup key: title + artist/author + borrowed_date
- Default API base: http://localhost:18080
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from katsushika_common import (
    BASE_LIB_URL,
    DEFAULT_LIBRARY,
    DedupKey,
    get_credentials,
    jp_date_to_iso,
    key_of,
    login_session,
    map_type,
    normalize_text,
    parse_detail_fields,
    parse_dl_map,
    strip_tags,
)
from rip_history_match import find_ripped_at, load_rip_records

__all__ = [
    "DedupKey",
    "fetch_current_loans",
    "get_credentials",
    "import_items",
    "jp_date_to_iso",
    "key_of",
    "main",
    "map_type",
    "normalize_text",
    "parse_detail_fields",
    "parse_dl_map",
    "strip_tags",
]


def fetch_current_loans(username: str, password: str, rip_records: list | None = None) -> list[dict[str, Any]]:
    s = login_session(username, password)

    rentallist = s.get(urljoin(BASE_LIB_URL, "rentallist"), timeout=20)
    sections = re.findall(r'<section class="infotable">(.*?)</section>', rentallist.text, re.S | re.I)

    items: list[dict[str, Any]] = []
    for sec in sections:
        t = re.search(r'<h3>.*?<a[^>]+href="([^"]*rentaldetail\?conum=\d+)"[^>]*>\s*<span>(.*?)</span>', sec, re.S | re.I)
        if not t:
            continue
        detail_rel = html.unescape(t.group(1))
        fallback_title = strip_tags(t.group(2))
        dls = parse_dl_map(sec)

        borrowed = jp_date_to_iso(dls.get("貸出日", ""))
        due = jp_date_to_iso(dls.get("返却期限", ""))

        detail = s.get(urljoin(BASE_LIB_URL, detail_rel), timeout=20)
        fields = parse_detail_fields(detail.text)
        item_type = map_type(fields)
        title = fields.get("タイトル", fallback_title) or fallback_title
        person = (fields.get("著作者") or fields.get("著者") or "").strip()

        row: dict[str, Any] = {
            "type": item_type,
            "title": title,
            "library": DEFAULT_LIBRARY,
            "borrowed_date": borrowed,
            "due_date": due,
        }
        if item_type == "book":
            if person:
                row["author"] = person
            if fields.get("ISBN"):
                row["isbn"] = fields["ISBN"]
        else:
            if person:
                row["artist"] = person
            if item_type == "cd" and rip_records:
                ripped_at = find_ripped_at(title, person, borrowed, rip_records)
                if ripped_at:
                    row["ripped_at"] = ripped_at

        if item_type == "other":
            row["notes"] = f"raw_type={fields.get('資料形態', 'unknown')}"

        items.append(row)

    return items


def import_items(base_url: str, items: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    items_url = base_url.rstrip("/") + "/api/items"

    existing = requests.get(items_url, timeout=20)
    existing.raise_for_status()
    seen = {key_of(i) for i in existing.json()}

    inserted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for item in items:
        k = key_of(item)
        if k in seen:
            skipped.append(item)
            continue
        if dry_run:
            inserted.append(item)
            seen.add(k)
            continue
        try:
            r = requests.post(items_url, json=item, timeout=20)
            r.raise_for_status()
            inserted.append(r.json())
            seen.add(k)
        except Exception as e:  # noqa: BLE001
            errors.append({"item": item, "error": str(e)})

    return {
        "fetched": len(items),
        "inserted": len(inserted),
        "skipped": len(skipped),
        "errors": len(errors),
        "inserted_items": inserted,
        "skipped_items": skipped,
        "error_items": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:18080")
    ap.add_argument("--vault", default="OpenClaw")
    ap.add_argument("--item", default="Katsushika")
    ap.add_argument("--out", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    username, password = get_credentials(args.vault, args.item)
    rip_records = load_rip_records()
    items = fetch_current_loans(username, password, rip_records=rip_records)
    summary = import_items(args.base_url, items, dry_run=args.dry_run)

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")

    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        raise
