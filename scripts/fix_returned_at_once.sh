#!/usr/bin/env bash
set -euo pipefail
set -a
source ~/.config/op/service-account.env
set +a
python3 /home/kouki/clawd/scripts/kashidashi-sync/backfill_returned_at_from_history.py \
  --base-url http://localhost:18080 \
  --vault OpenClaw \
  --item Katsushika
