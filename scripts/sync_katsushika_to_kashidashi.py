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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from rip_history_match import find_ripped_at, load_rip_records

BASE_LIB_URL = "https://www.lib.city.katsushika.lg.jp/"


@dataclass(frozen=True)
class DedupKey:
    title: str
    person: str
    borrowed_date: str


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().split()).lower()


def key_of(item: dict[str, Any]) -> DedupKey:
    person = item.get("artist") or item.get("author") or ""
    return DedupKey(
        normalize_text(item.get("title")),
        normalize_text(person),
        str(item.get("borrowed_date") or "").strip(),
    )


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return " ".join(s.replace("\xa0", " ").split())


def jp_date_to_iso(s: str) -> str:
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", s)
    if not m:
        return s
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def parse_dl_map(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", block, re.S | re.I):
        out[strip_tags(m.group(1))] = strip_tags(m.group(2))
    return out


def parse_detail_fields(html_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for m in re.finditer(r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td>(.*?)</td>', html_text, re.S | re.I):
        k = strip_tags(m.group(1))
        v = strip_tags(m.group(2))
        if k and v:
            fields[k] = v
    return fields


def map_type(fields: dict[str, str]) -> str:
    val = " ".join([fields.get("資料形態", ""), fields.get("数量", ""), fields.get("タイトル", "")]).lower()
    if any(k in val for k in ["コンパクトディスク", "cd", "録音"]):
        return "cd"
    if any(k in val for k in ["dvd", "ビデオディスク", "映像"]):
        return "dvd"
    if any(k in val for k in ["図書", "冊", "文庫", "単行本"]):
        return "book"
    if fields.get("出版社") or fields.get("出版者") or fields.get("ページ数") or fields.get("ISBN"):
        return "book"
    return "other"


def get_credentials(vault: str, item: str) -> tuple[str, str]:
    cmd = ["op", "item", "get", item, "--vault", vault, "--format", "json"]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"op item get failed: {p.stderr.strip()}")
    obj = json.loads(p.stdout)

    username = ""
    password = ""
    for f in obj.get("fields", []):
        fid = (f.get("id") or "").lower()
        purpose = (f.get("purpose") or "").lower()
        label = (f.get("label") or "").lower()
        val = f.get("value") or ""
        if not username and (purpose == "username" or fid == "username" or "user" in label or "id" in label):
            username = val
        if not password and (purpose == "password" or fid == "password" or "pass" in label):
            password = val

    if not username or not password:
        raise RuntimeError("Could not resolve username/password from 1Password item")
    return username, password


def fetch_current_loans(username: str, password: str, rip_records: list | None = None) -> list[dict[str, Any]]:
    s = requests.Session()
    login = s.get(urljoin(BASE_LIB_URL, "login"), timeout=20)
    m = re.search(r'<form[^>]*id="ida"[^>]*action="([^"]+)"', login.text, re.I)
    if not m:
        raise RuntimeError("Login form not found")
    action = m.group(1)
    s.post(
        urljoin(login.url, action),
        data={"textUserId": username, "textPassword": password, "buttonLogin": "ログイン"},
        timeout=20,
    )

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
            "library": "葛飾区立中央図書館",
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
