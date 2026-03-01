# MTProto Proxy Management System

Управление MTProto прокси через Telegram бота.

## Возможности

- 🚀 Создание и управление MTProto прокси
- 🤖 Telegram бот для управления
- 🔒 Безопасность (защита по Telegram ID)
- 📦 Docker-based (легко развернуть)

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/gkarev/mtproto-proxy.git
cd mtproto-proxy

# 2. Настроить переменные окружения
cp .env.example .env
nano .env

# 3. Сгенерировать секрет
./scripts/generate_secret.sh

# 4. Запустить
docker-compose up -d
```

## Требования

- Docker
- Docker Compose
- Telegram бот (от @BotFather)

## Настройка .env

```env
SERVER_IP=YOUR_SERVER_IP           # IP сервера
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN # Токен от @BotFather
ALLOWED_USER_ID=YOUR_TELEGRAM_ID   # Ваш Telegram ID
```

## Как получить:

### Telegram Bot Token
1. Откройте @BotFather в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям, получите токен

### Telegram ID
1. Откройте @userinfobot в Telegram
2. Получите свой ID

## Команды бота

| Команда | Описание |
|---------|---------|
| `/start` | Главное меню |
| `/proxy add <порт>` | Добавить прокси |
| `/proxy list` | Список прокси |
| `/proxy status` | Статус |

## Структура проекта

```
mtproto-proxy/
├── docker-compose.yml   # Оркестрация
├── .env.example        # Пример конфигурации
├── bot/               # Telegram бот
│   ├── bot.py
│   └── Dockerfile
├── mtg/               # MTG прокси
│   ├── mtg
│   ├── run_mtg.sh
│   └── Dockerfile
├── config/            # Конфигурация
│   └── proxies.json
└── scripts/          # Скрипты
    └── generate_secret.sh
```

## Управление

```bash
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Перезапуск
docker-compose restart

# Логи
docker-compose logs -f
```

## Безопасность

- ⚠️ Не публикуйте `.env` и `config/proxies.json`
- ⚠️ Добавьте их в `.gitignore`
- ✅ Бот проверяет Telegram ID перед выполнением команд

## Автор

gkarev

## Лицензия

MIT
