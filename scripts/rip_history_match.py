#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

RIP_ROOT = Path('/mnt/media/audio/_incoming')
ALIAS_PATH = Path('/home/kouki/dev/kashidashi-app/config/rip-title-aliases.json')


@dataclass
class RipRecord:
    ripped_at: str
    title_norm: str
    artist_norm: str


def norm(s: str | None) -> str:
    if not s:
        return ''
    x = s.lower().strip()
    x = x.replace('〜', '~').replace('～', '~')
    x = x.replace('・', '').replace('／', '/').replace('　', ' ')
    x = re.sub(r'\(disc[- ]?\d+\)', ' ', x, flags=re.I)
    x = re.sub(r'\[disc[- ]?\d+\]', ' ', x, flags=re.I)
    x = re.sub(r'disc[- ]?\d+', ' ', x, flags=re.I)
    x = re.sub(r'[^0-9a-zぁ-んァ-ヶ一-龠]+', '', x)
    return x


def _rip_time_from_dirname(dirname: str) -> str | None:
    m = re.match(r'rip_(\d{8})T(\d{6})Z', dirname)
    if not m:
        return None
    dt = datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    return dt.isoformat().replace('+00:00', 'Z')


def _load_aliases() -> dict[str, list[str]]:
    if not ALIAS_PATH.exists():
        return {}
    try:
        raw = json.loads(ALIAS_PATH.read_text(encoding='utf-8'))
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            if isinstance(v, list):
                out[norm(k)] = [norm(str(x)) for x in v]
        return out
    except Exception:
        return {}


def load_rip_records() -> list[RipRecord]:
    aliases = _load_aliases()
    recs: list[RipRecord] = []
    for meta in sorted(RIP_ROOT.glob('rip_*/meta.json')):
        try:
            obj = json.loads(meta.read_text(encoding='utf-8'))
        except Exception:
            continue
        ripped_at = _rip_time_from_dirname(meta.parent.name)
        if not ripped_at:
            continue
        t = norm(obj.get('album'))
        a = norm(obj.get('artist'))
        if not t:
            continue
        recs.append(RipRecord(ripped_at=ripped_at, title_norm=t, artist_norm=a))
        for alias in aliases.get(t, []):
            recs.append(RipRecord(ripped_at=ripped_at, title_norm=alias, artist_norm=a))
    return recs


def find_ripped_at(title: str | None, artist: str | None, borrowed_date: str | None, records: Iterable[RipRecord]) -> str | None:
    t = norm(title)
    a = norm(artist)
    b = (borrowed_date or '').strip()

    b_date = None
    if b:
        try:
            b_date = datetime.strptime(b, '%Y-%m-%d').date()
        except Exception:
            b_date = None

    def in_window(ripped_at: str) -> bool:
        if not b_date:
            return True
        try:
            r_date = datetime.strptime(ripped_at[:10], '%Y-%m-%d').date()
        except Exception:
            return False
        return b_date <= r_date <= (b_date + timedelta(days=3))

    # 1) exact title normalized
    candidates = [r for r in records if t and r.title_norm == t and in_window(r.ripped_at)]

    # 2) loose title (contains), useful for suffix/prefix differences
    if not candidates:
        candidates = [r for r in records if t and (t in r.title_norm or r.title_norm in t) and in_window(r.ripped_at)]

    # 3) fallback: same date-window + artist when title scripts differ (EN/JP)
    if not candidates and a:
        artist_matches = [r for r in records if r.artist_norm and (r.artist_norm in a or a in r.artist_norm) and in_window(r.ripped_at)]
        if len(artist_matches) == 1:
            return artist_matches[0].ripped_at

    if not candidates:
        return None
    candidates.sort(key=lambda x: x.ripped_at)
    return candidates[-1].ripped_at
