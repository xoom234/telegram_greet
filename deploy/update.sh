#!/usr/bin/env bash
# Обновление бота на сервере до последней версии из GitHub: bash deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."

git pull --ff-only
.venv/bin/pip install -r requirements.txt
sudo systemctl restart sklad-bot
sleep 3
sudo systemctl --no-pager status sklad-bot || true
