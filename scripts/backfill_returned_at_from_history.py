#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://www.lib.city.katsushika.lg.jp/"
ALIAS_PATH = Path('/home/kouki/clawd/scripts/kashidashi-sync/config/return-title-aliases.json')


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(html.unescape(s).replace("\xa0", " ").split())


def norm_title(s: str | None) -> str:
    x = (s or "").lower().strip()
    x = x.replace("～", "~").replace("〜", "~")
    x = re.sub(r"\(.*?\)", "", x)
    x = re.sub(r"（.*?）", "", x)
    x = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠]+", "", x)
    return x


def jp_date(s: str) -> str:
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", s)
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def load_title_alias_map() -> dict[str, list[str]]:
    if not ALIAS_PATH.exists():
        return {}
    try:
        raw = json.loads(ALIAS_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    for k, vals in raw.items():
        nk = norm_title(k)
        if not nk:
            continue
        arr = [norm_title(str(v)) for v in vals if norm_title(str(v))]
        if arr:
            out[nk] = arr
    return out


def title_keys_for_match(title: str | None, alias_map: dict[str, list[str]]) -> list[str]:
    base = norm_title(title)
    if not base:
        return []
    keys = [base]
    for a in alias_map.get(base, []):
        if a not in keys:
            keys.append(a)
    # reverse lookup
    for k, vals in alias_map.items():
        if base in vals and k not in keys:
            keys.append(k)
    return keys


def get_credentials(vault: str, item: str) -> tuple[str, str]:
    p = subprocess.run(["op", "item", "get", item, "--vault", vault, "--format", "json"], capture_output=True, text=True, check=True)
    obj = json.loads(p.stdout)
    u = w = ""
    for f in obj.get("fields", []):
        label = (f.get("label") or "").lower()
        purpose = (f.get("purpose") or "").lower()
        fid = (f.get("id") or "").lower()
        val = f.get("value") or ""
        if not u and (purpose == "username" or fid == "username" or "user" in label or "id" in label):
            u = val
        if not w and (purpose == "password" or fid == "password" or "pass" in label):
            w = val
    if not u or not w:
        raise RuntimeError("credentials not found")
    return u, w


def _absorb_history_page(s: requests.Session, html_text: str, out: dict[tuple[str, str], str], seen_details: set[str]) -> list[str]:
    sections = re.findall(r'<section class="infotable">(.*?)</section>', html_text, re.S | re.I)
    loans: list[str] = []
    for sec in sections:
        m = re.search(r'<a[^>]+href="([^"]*rentalhistorydetail\?[^"]+)"[^>]*>\s*<span>(.*?)</span>', sec, re.S | re.I)
        if not m:
            continue
        rel = html.unescape(m.group(1))
        if rel in seen_details:
            continue
        seen_details.add(rel)
        fallback_title = strip_tags(m.group(2))

        d = s.get(urljoin(BASE, rel), timeout=20)
        row_fields = {}
        for fm in re.finditer(r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td>(.*?)</td>', d.text, re.S | re.I):
            row_fields[strip_tags(fm.group(1))] = strip_tags(fm.group(2))

        mloan = re.search(r'<th[^>]*>貸出日</th>\s*<td[^>]*>(.*?)</td>', d.text, re.S | re.I)
        mret = re.search(r'<th[^>]*>返却日</th>\s*<td[^>]*>(.*?)</td>', d.text, re.S | re.I)
        loan = jp_date(strip_tags(mloan.group(1))) if mloan else ""
        ret = jp_date(strip_tags(mret.group(1))) if mret else ""
        if not loan or not ret:
            continue

        title = row_fields.get("タイトル") or row_fields.get("書名") or fallback_title
        out[(norm_title(title), loan)] = ret
        loans.append(loan)
    return loans


def fetch_history_return_map(username: str, password: str, min_loan_date: str | None = None) -> dict[tuple[str, str], str]:
    s = requests.Session()
    r = s.get(urljoin(BASE, "login"), timeout=20)
    action = re.search(r'<form[^>]*id="ida"[^>]*action="([^"]+)"', r.text, re.I).group(1)
    s.post(urljoin(r.url, action), data={"textUserId": username, "textPassword": password, "buttonLogin": "ログイン"}, timeout=20)

    out: dict[tuple[str, str], str] = {}
    seen_details: set[str] = set()
    seen_pages: set[str] = set()
    queue: list[str] = [urljoin(BASE, "rentalhistorylist")]
    passed_zone = False
    pages = 0
    while queue and pages < 15:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        resp = s.get(url, timeout=20)
        pages += 1
        loans = _absorb_history_page(s, resp.text, out, seen_details)
        for href in re.findall(r'href="([^"]*pageLinkListview-\d+-pageLink)"', resp.text):
            u = urljoin(resp.url, html.unescape(href))
            if u not in seen_pages and u not in queue:
                queue.append(u)
        if min_loan_date and loans:
            if max(loans) >= min_loan_date:
                passed_zone = True
            elif passed_zone:
                # Pages are newest-first; once a whole page is older than
                # the oldest open loan, nothing reachable later can match.
                break

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:18080")
    ap.add_argument("--vault", default="OpenClaw")
    ap.add_argument("--item", default="Katsushika")
    args = ap.parse_args()

    u, w = get_credentials(args.vault, args.item)
    ret_map = fetch_history_return_map(u, w)
    alias_map = load_title_alias_map()

    items_url = args.base_url.rstrip("/") + "/api/items"
    items = requests.get(items_url, timeout=20).json()

    updated = []
    skipped = []
    for it in items:
        if it.get("returned_at") is None:
            continue
        borrowed = it.get("borrowed_date")
        ret = None
        for tk in title_keys_for_match(it.get("title"), alias_map):
            ret = ret_map.get((tk, borrowed))
            if ret:
                break
        if not ret:
            skipped.append({"id": it.get("id"), "title": it.get("title"), "reason": "no history match"})
            continue
        target = ret + "T00:00:00Z"
        if it.get("returned_at") == target:
            skipped.append({"id": it.get("id"), "title": it.get("title"), "reason": "already correct"})
            continue

        r = requests.patch(f"{items_url}/{it['id']}", json={"returned_at": target, "ripped_at": it.get("ripped_at")}, timeout=20)
        if r.ok:
            updated.append({"id": it.get("id"), "title": it.get("title"), "returned_at": target})
        else:
            skipped.append({"id": it.get("id"), "title": it.get("title"), "reason": f"patch {r.status_code}"})

    print(json.dumps({"updated": len(updated), "skipped": len(skipped), "updated_items": updated}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
