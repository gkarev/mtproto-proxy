# Code Review: mtproto-proxy

## 📋 Обзор проекта

**Название:** MTProto Proxy Management System  
**Назначение:** Управление MTProto прокси через Telegram бота  
**Стек:** Python 3.11 (bot), Alpine (MTG), Docker  

---

## 🏗 Файловая структура

```
mtproto-proxy/
├── bot/
│   ├── bot.py           # 527 строк — основная логика
│   └── Dockerfile       # Python 3.11-slim
├── mtg/
│   ├── mtg              # Бинарник (12.7 MB)
│   ├── run_mtg.sh       # Скрипт запуска
│   └── Dockerfile       # Alpine
├── config/
│   └── proxies.json     # Конфигурация прокси
├── scripts/
│   └── generate_secret.sh
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🔴 Критические проблемы

### 1. **Безопасность: Уязвимость к Race Condition**
**Файл:** `bot/bot.py`, строки 59-75

```python
def start_proxy_container(proxy_id, port, secret):
    # ...
    if container_name in get_running_containers():
        return False, "Уже запущен"
    # Stop old container
    subprocess.run(["docker", "stop", container_name], ...)
    subprocess.run(["docker", "rm", container_name], ...)
```

**Проблема:** Проверка и запуск контейнера не атомарны. Между `get_running_containers()` и `docker run` может вмешаться другой процесс. Используйте `docker run --rm` или `docker upsert`.

### 2. **Безопасность: Отсутствие валидации портов**
**Файл:** `bot/bot.py`, строка 336

```python
port = int(port_arg)  # Нет проверки диапазона!
```

**Проблема:** Пользователь может указать любой порт (0, 65535, отрицательный). Нет валидации:
- Ports < 1024 могут требовать root
- Ports > 65535 вызовут ошибку Docker
- Конфликты с системными сервисами

**Рекомендация:**
```python
if not (1024 <= port <= 65535):
    await update.message.reply_text("Порт должен быть от 1024 до 65535")
    return
```

### 3. **Безопасность: Docker socket в контейнере бота**
**Файл:** `docker-compose.yml`, строка 20

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

**Проблема:** Бот имеет полный доступ к Docker API из контейнера. Это означает:
- Возможность выполнять любые команды на хосте
- Управление всеми контейнерами системы
- Потенциальный privilege escalation

**Рекомендация:** Использовать Docker API через TCP с ограниченными правами или отдельный docker-compose для изоляции.

### 4. **Уязвимость: Command Injection**
**Файл:** `bot/bot.py`, строки 70-80

```python
cmd = [
    "docker", "run", "-d",
    "--name", container_name,  # user-controlled!
    "-p", f"{port}:8443",
    # ...
]
result = subprocess.run(cmd, capture_output=True, text=True)
```

**Проблема:** `proxy_id` формируется как `f"proxy{port}"`, но не экранируется. Хотя в текущей реализации это безопасно, лучше явно валидировать имена.

---

## 🟠 Серьёзные проблемы

### 5. **Отсутствие обработки ошибок**
**Файл:** `bot/bot.py`

- `load_config()` (строки 21-28): Generic `except:` скрывает все ошибки
- `generate_secret()` (строки 37-50): Try/except без логирования
- `get_running_containers()` (строки 52-56): Не проверяет `result.returncode`

**Рекомендация:**
```python
def load_config():
    path = os.environ.get("CONFIG_PATH", CONFIG_PATH)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config not found: {path}")
        return {"proxies": {}}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return {"proxies": {}}
```

### 6. **Нет логирования**
**Файл:** `bot/bot.py`

Отсутствует модуль `logging`. Все операции выполняются без записи в лог. Невозможно отладить проблемы в продакшене.

### 7. **Устаревший формат секрета**
**Файлы:** `scripts/generate_secret.sh`, `mtg/run_mtg.sh`

Скрипт генерации создаёт 64-символьный hex (SHA-256), но MTG ожидает Base64-подобный формат `dd...` (64 символа). Несоответствие может привести к ошибкам подключения.

**Текущий формат (скрипт):** `openssl rand -hex 32` → 64 hex-символов  
**Ожидаемый MTG:** Формат `ee...` (base64 без padding)

### 8. **Harcoded пути**
**Файл:** `bot/bot.py`, строка 40

```python
MTG_BINARY = "/root/.openclaw/workspace/mtproto-proxy/mtg/mtg"
```

Путь захардкожен и не работает внутри Docker-контейнера. В контейнере MTG находится в `/usr/local/bin/mtg`.

---

## 🟡 Умеренные проблемы

### 9. **UI/UX: Кнопки управления неинформативны**
**Файл:** `bot/bot.py`, строки 195-198

```python
keyboard.append([
    InlineKeyboardButton("▶️", callback_data=f"proxy_start_{name}"),
    InlineKeyboardButton("⏹️", callback_data=f"proxy_stop_{name}"),
    ...
])
```

**Проблема:** 
- Кнопки без подписей — непонятно что делают
- Нет визуальной индикации текущего состояния (какая кнопка активна)
- Нет отображения статуса прокси (работает/остановлен)

### 10. **UI/UX: Нет подтверждения при удалении**
**Файл:** `bot/bot.py`, строки 280-295

Удаление происходит мгновенно без подтверждения. Один случайный клик — и прокси удалён.

**Рекомендация:** Добавить inline-кнопки "Да, удалить" / "Отмена".

### 11. **Дублирование кода**
**Файл:** `bot/bot.py`

- `show_proxy_list()` и `show_proxy_status()` делают похожие вещи
- `show_proxy_status_command()` — дубликат `show_proxy_status()`
- Нет DRY-принципа

### 12. **Нет проверки занятых портов**
**Файл:** `bot/bot.py`

При добавлении прокси не проверяется, занят ли порт другим контейнером или сервисом.

### 13. **Неполная документация**
**Файл:** `README.md`

- Нет описания структуры JSON-конфига
- Нет troubleshooting section
- Нет примеров использования API

---

## 🟢 Мелкие улучшения

### 14. **Отсутствие rate limiting**
Бот не защищён от спама или случайных повторных нажатий.

### 15. **Нет health check**
Docker compose не содержит healthcheck для сервисов.

### 16. **Конфигурация в файле, а не в env**
`config/proxies.json` содержит данные, которые лучше хранить в переменных окружения или secrets.

### 17. **Неиспользуемый код**
- `proxy_list` и `proxy_status` как CommandHandler (строки 400-401), хотя есть CallbackQueryHandler
- Функция `show_proxy_status_command()` экспортируется, но не используется

---

## 📊 Итоговая оценка

| Категория | Оценка |
|-----------|--------|
| Безопасность | 🔴 Плохо |
| Надёжность | 🟠 Ниже среднего |
| UX/UI | 🟡 Ниже среднего |
| Код качество | 🟡 Ниже среднего |
| Документация | 🟠 Ниже среднего |

---

## 🎯 Рекомендации по приоритетам

### Срочно (P0):
1. Валидация портов
2. Логирование
3. Обработка ошибок
4. Подтверждение удаления

### Важно (P1):
5. Исправить формат генерации секрета
6. Убрать hardcoded пути
7. Улучшить UI кнопок
8. Изолировать Docker socket

### Желательно (P2):
9. Добавить логирование
10. DRY refactoring
11. Rate limiting
12. Health checks

---

*Review generated: 2026-03-02*