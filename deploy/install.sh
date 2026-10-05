#!/usr/bin/env bash
# Первичная установка бота на Ubuntu-сервер. Запускать из корня проекта: bash deploy/install.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
SERVICE=sklad-bot

cd "$DIR"

sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

missing=0
[ -f .env ] || { echo "Нет файла $DIR/.env"; missing=1; }
[ -f credentials/credentials.json ] || { echo "Нет файла $DIR/credentials/credentials.json"; missing=1; }
if [ "$missing" -ne 0 ]; then
    echo "Скопируйте секреты с Mac (scp) и запустите скрипт ещё раз."
    exit 1
fi
chmod 600 .env credentials/credentials.json

sed -e "s|__USER__|$USER_NAME|g" -e "s|__DIR__|$DIR|g" deploy/sklad-bot.service \
    | sudo tee /etc/systemd/system/$SERVICE.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE
sleep 3
sudo systemctl --no-pager status $SERVICE || true
echo
echo "Логи: journalctl -u $SERVICE -f"
