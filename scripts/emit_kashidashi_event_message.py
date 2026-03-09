#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default="/home/kouki/dev/kashidashi-app/state")
    ap.add_argument("--consume", action="store_true")
    args = ap.parse_args()

    state_dir = Path(args.state_dir)
    event_path = state_dir / "katsushika_last_event.json"
    sent_path = state_dir / "katsushika_last_sent_digest.txt"

    if not event_path.exists():
        print("NO_CHANGE")
        return 0

    event = json.loads(event_path.read_text(encoding="utf-8"))
    digest = event.get("snapshot_digest", "")
    sent = sent_path.read_text(encoding="utf-8").strip() if sent_path.exists() else ""

    if (not event.get("changed")) or (digest and digest == sent):
        print("NO_CHANGE")
        return 0

    print(event.get("message", "[kashidashi] 変更あり"))

    if args.consume and digest:
        sent_path.write_text(digest + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
