#!/usr/bin/env bash
set -euo pipefail
cd /home/kouki/clawd/scripts/kashidashi-sync
set -a
source ~/.config/op/service-account.env
set +a
TS="$(date +%F_%H-%M-%S)"
LOG_DIR="/home/kouki/clawd/scripts/kashidashi-sync/logs"
mkdir -p "$LOG_DIR"
OUT_JSON="$LOG_DIR/sync_katsushika_${TS}.json"
OUT_LOG="$LOG_DIR/sync_katsushika_${TS}.log"
python3 /home/kouki/clawd/scripts/kashidashi-sync/sync_katsushika_with_events.py \
  --base-url "http://localhost:18080" \
  --vault "OpenClaw" \
  --item "Katsushika" \
  --state-dir "/home/kouki/clawd/scripts/kashidashi-sync/state" \
  --out "$OUT_JSON" \
  >> "$OUT_LOG" 2>&1
echo "done: $OUT_JSON" >> "$OUT_LOG"
