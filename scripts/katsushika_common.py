#!/usr/bin/env python3
"""葛飾区立図書館サイトのスクレイピングで共有するヘルパー。

sync_katsushika_to_kashidashi.py（貸出中の巡回）と
import_katsushika_history_once.py（履歴の一括取り込み）の双方から使う。
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

BASE_LIB_URL = "https://www.lib.city.katsushika.lg.jp/"
DEFAULT_LIBRARY = "葛飾区立中央図書館"


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


def jp_date_to_iso(s: str, fallback: str | None = None) -> str:
    """「YYYY年M月D日」を ISO 形式に変換する。

    日付が見つからないときは fallback（未指定なら入力をそのまま）を返す。
    """
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", s)
    if not m:
        return s if fallback is None else fallback
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


def login_session(username: str, password: str) -> requests.Session:
    """図書館サイトにログイン済みの requests.Session を返す。"""
    session = requests.Session()
    login_page = session.get(urljoin(BASE_LIB_URL, "login"), timeout=20)
    m = re.search(r'<form[^>]*id="ida"[^>]*action="([^"]+)"', login_page.text, re.I)
    if not m:
        raise RuntimeError("Login form not found")
    session.post(
        urljoin(login_page.url, m.group(1)),
        data={"textUserId": username, "textPassword": password, "buttonLogin": "ログイン"},
        timeout=20,
    )
    return session
