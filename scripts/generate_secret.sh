#!/bin/bash
# Генерация секрета для MTProto прокси
# Использование: ./scripts/generate_secret.sh

echo "Генерация секрета для MTProto..."

# Генерируем случайный секрет (32 байта = 64 hex символа)
SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")

echo "Ваш секрет:"
echo "$SECRET"

echo ""
echo "Добавьте этот секрет в config/proxies.json:"
echo ""
cat << EOF
{
  "proxies": {
    "default": {
      "secret": "$SECRET",
      "port": "8443",
      "status": "active",
      "owner": "admin",
      "created_at": "$(date -Iseconds)"
    }
  },
  "server": {
    "ip": "YOUR_SERVER_IP"
  }
}
EOF
