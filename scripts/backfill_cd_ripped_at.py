#!/usr/bin/env python3
from __future__ import annotations

import json
import requests

from rip_history_match import find_ripped_at, load_rip_records

API = 'http://localhost:18080/api/items'


def main() -> int:
    records = load_rip_records()
    items = requests.get(API, timeout=20).json()
    updated = []
    skipped = []

    for it in items:
        if it.get('type') != 'cd':
            continue
        if it.get('ripped_at'):
            skipped.append({'id': it['id'], 'reason': 'already set'})
            continue
        ripped_at = find_ripped_at(it.get('title'), it.get('artist'), it.get('borrowed_date'), records)
        if not ripped_at:
            skipped.append({'id': it['id'], 'reason': 'no match'})
            continue
        r = requests.patch(f"{API}/{it['id']}", json={'ripped_at': ripped_at}, timeout=20)
        if r.ok:
            updated.append({'id': it['id'], 'title': it.get('title'), 'ripped_at': ripped_at})
        else:
            skipped.append({'id': it['id'], 'reason': f'patch failed {r.status_code}'})

    print(json.dumps({'updated': len(updated), 'skipped': len(skipped), 'updated_items': updated, 'skipped_items': skipped}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
