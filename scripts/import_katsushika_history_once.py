#!/usr/bin/env python3
"""One-shot import for Katsushika rental history.
Safety rule: import only rows that have returned date.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from typing import Any
from urllib.parse import urljoin

import requests

from katsushika_common import (
    BASE_LIB_URL,
    DEFAULT_LIBRARY,
    get_credentials,
    jp_date_to_iso,
    key_of,
    login_session,
    map_type,
    strip_tags,
)

API = "http://localhost:18080/api/items"


def detail_field(html_text: str, label: str) -> str:
    m = re.search(rf"<th[^>]*>{label}</th>\s*<td[^>]*>(.*?)</td>", html_text, re.S | re.I)
    return strip_tags(m.group(1)) if m else ""


def map_history_type(fields: dict[str, str]) -> str:
    # 履歴詳細ページは「書名」「ＩＳＢＮ」欄を使うので、共通の判定に載る形へ寄せる
    merged = dict(fields)
    merged["タイトル"] = " ".join(p for p in (fields.get("書名", ""), fields.get("タイトル", "")) if p)
    if not merged.get("ISBN") and fields.get("ＩＳＢＮ"):
        merged["ISBN"] = fields["ＩＳＢＮ"]
    return map_type(merged)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default="OpenClaw")
    ap.add_argument("--item", default="Katsushika")
    args = ap.parse_args()

    username, password = get_credentials(args.vault, args.item)
    s = login_session(username, password)

    history = s.get(urljoin(BASE_LIB_URL, "rentalhistorylist"), timeout=20)
    sections = re.findall(r'<section class="infotable">(.*?)</section>', history.text, re.S | re.I)

    existing = requests.get(API, timeout=20).json()
    seen = {key_of(i) for i in existing}

    inserted = skipped = no_return = 0
    for sec in sections:
        m = re.search(r'<a[^>]+href="([^"]*rentalhistorydetail\?[^"]+)"[^>]*>\s*<span>(.*?)</span>', sec, re.S | re.I)
        if not m:
            continue
        rel = html.unescape(m.group(1))
        fallback_title = strip_tags(m.group(2))

        detail = s.get(urljoin(BASE_LIB_URL, rel), timeout=20)
        fields: dict[str, str] = {}
        for fm in re.finditer(r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td>(.*?)</td>', detail.text, re.S | re.I):
            fields[strip_tags(fm.group(1))] = strip_tags(fm.group(2))

        loan = jp_date_to_iso(detail_field(detail.text, "貸出日"), fallback="")
        returned = jp_date_to_iso(detail_field(detail.text, "返却日"), fallback="")

        if not returned:
            no_return += 1
            continue

        item_type = map_history_type(fields)
        title = fields.get("タイトル") or fields.get("書名") or fallback_title
        person = fields.get("著作者") or fields.get("著者") or fields.get("著者名") or ""
        item: dict[str, Any] = {
            "type": item_type,
            "title": title,
            "library": DEFAULT_LIBRARY,
            "borrowed_date": loan,
            "due_date": returned,
            "returned_at": returned + "T00:00:00Z",
        }
        if person:
            item["author" if item_type == "book" else "artist"] = person

        k = key_of(item)
        if k in seen:
            skipped += 1
            continue
        r = requests.post(API, json=item, timeout=20)
        if r.ok:
            inserted += 1
            seen.add(k)

    print(
        json.dumps(
            {"fetched": len(sections), "inserted": inserted, "skipped": skipped, "no_return_skipped": no_return},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
