#!/bin/sh

# MTG Proxy Runner
# Читает конфигурацию из /app/config/proxies.json

CONFIG_FILE="/app/config/proxies.json"

# PROXY_ID передаётся через переменную окружения или аргумент
PROXY_ID="${PROXY_ID:-${1:-default}}"

echo "MTG Proxy starting for: $PROXY_ID"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    exit 1
fi

# Читаем конфиг через python3 (alpine has it)
SECRET=$(python3 -c "
import json
import sys
with open('$CONFIG_FILE') as f:
    data = json.load(f)
    proxies = data.get('proxies', {})
    proxy = proxies.get('$PROXY_ID', {})
    print(proxy.get('secret', ''))
")

# Port inside container is always 8443 (external port is mapped via docker)
PORT_INTERNAL="8443"

if [ -z "$SECRET" ]; then
    echo "Error: Proxy '$PROXY_ID' not found in config"
    exit 1
fi

echo "Starting MTG with port: $PORT_INTERNAL, secret: $SECRET"

# Запускаем MTG
exec mtg simple-run "0.0.0.0:$PORT_INTERNAL" "$SECRET" --prefer-ip prefer-ipv4
