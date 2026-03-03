#!/usr/bin/env python3
"""
MTProto Proxy Telegram Bot
Управление MTProto прокси через Telegram
"""
import os
import json
import logging
import subprocess
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ─── Логирование ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mtproto-bot")

# ─── Конфигурация ────────────────────────────────────────────────────────────
SERVER_IP = os.environ.get("SERVER_IP", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config/proxies.json")
MTG_IMAGE = os.environ.get("MTG_IMAGE", "mtproto-mtg:latest")
MTG_BINARY = os.environ.get("MTG_BINARY", "/usr/local/bin/mtg")

PORT_MIN = 1024
PORT_MAX = 65535


# ─── Конфиг ─────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Загрузка конфигурации из JSON-файла."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "proxies" not in data:
                data["proxies"] = {}
            return data
    except FileNotFoundError:
        logger.warning("Файл конфига не найден: %s — создаю пустой", CONFIG_PATH)
        return {"proxies": {}}
    except json.JSONDecodeError as e:
        logger.error("Ошибка разбора JSON в конфиге: %s", e)
        return {"proxies": {}}
    except OSError as e:
        logger.error("Ошибка чтения конфига: %s", e)
        return {"proxies": {}}


def save_config(data: dict) -> bool:
    """Сохранение конфигурации. Возвращает True при успехе."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Конфиг сохранён: %s", CONFIG_PATH)
        return True
    except OSError as e:
        logger.error("Ошибка записи конфига: %s", e)
        return False


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def generate_secret() -> str:
    """Генерация MTProto-секрета через бинарник mtg, fallback — hex."""
    try:
        result = subprocess.run(
            [MTG_BINARY, "generate-secret", "t.me"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            secret = result.stdout.strip()
            logger.info("Секрет сгенерирован через mtg binary")
            return secret
        logger.warning("mtg binary вернул код %d: %s", result.returncode, result.stderr.strip())
    except FileNotFoundError:
        logger.warning("MTG binary не найден по пути: %s", MTG_BINARY)
    except subprocess.TimeoutExpired:
        logger.warning("Таймаут при генерации секрета через mtg")
    except OSError as e:
        logger.warning("Ошибка запуска mtg: %s", e)

    # Fallback: стандартный hex-секрет (32 байта = 64 символа)
    fallback = secrets.token_hex(32)
    logger.info("Использован fallback для генерации секрета")
    return fallback


def is_port_valid(port: int) -> tuple[bool, str]:
    """Проверка допустимости порта."""
    if not (PORT_MIN <= port <= PORT_MAX):
        return False, f"Порт должен быть от {PORT_MIN} до {PORT_MAX}"
    return True, ""


def is_port_in_use(port: int) -> bool:
    """Проверка — занят ли порт уже каким-то контейнером."""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Ports}}"],
        capture_output=True, text=True
    )
    return f":{port}->" in result.stdout or f"0.0.0.0:{port}" in result.stdout


def get_running_containers() -> list[str]:
    """Список работающих контейнеров с префиксом mtproto-."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=mtproto-", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            logger.error("docker ps вернул ошибку: %s", result.stderr.strip())
            return []
        return [c for c in result.stdout.strip().split("\n") if c]
    except subprocess.TimeoutExpired:
        logger.error("Таймаут при запросе docker ps")
        return []
    except OSError as e:
        logger.error("Ошибка при вызове docker: %s", e)
        return []


def start_proxy_container(proxy_id: str, port: int | str, secret: str) -> tuple[bool, str]:
    """Запустить Docker-контейнер для прокси."""
    container_name = f"mtproto-{proxy_id}"

    # Останавливаем старый (если есть) — идемпотентно
    subprocess.run(["docker", "stop", container_name], capture_output=True)
    subprocess.run(["docker", "rm", container_name], capture_output=True)

    config_dir = os.path.dirname(CONFIG_PATH)

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:8443",
        "-v", f"{config_dir}:/app/config:ro",
        "-e", f"PROXY_ID={proxy_id}",
        "--restart", "unless-stopped",
        MTG_IMAGE,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        logger.error("Таймаут при запуске контейнера %s", container_name)
        return False, "Таймаут при запуске"
    except OSError as e:
        logger.error("Ошибка запуска контейнера %s: %s", container_name, e)
        return False, str(e)

    if result.returncode != 0:
        err = result.stderr.strip()
        logger.error("docker run завершился с кодом %d: %s", result.returncode, err)
        return False, err or "Неизвестная ошибка Docker"

    logger.info("Контейнер %s запущен на порту %s", container_name, port)
    return True, "Запущен"


def stop_proxy_container(proxy_id: str) -> tuple[bool, str]:
    """Остановить контейнер прокси."""
    container_name = f"mtproto-{proxy_id}"
    try:
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True, text=True, timeout=15
        )
    except subprocess.TimeoutExpired:
        return False, "Таймаут при остановке"
    except OSError as e:
        return False, str(e)

    if result.returncode != 0:
        logger.warning("Не удалось остановить %s: %s", container_name, result.stderr.strip())
        return False, "Контейнер не найден или уже остановлен"

    logger.info("Контейнер %s остановлен", container_name)
    return True, "Остановлен"


def restart_proxy_container(proxy_id: str) -> tuple[bool, str]:
    """Перезапустить контейнер прокси."""
    container_name = f"mtproto-{proxy_id}"
    try:
        result = subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return False, "Таймаут при перезапуске"
    except OSError as e:
        return False, str(e)

    if result.returncode != 0:
        logger.warning("Не удалось перезапустить %s: %s", container_name, result.stderr.strip())
        return False, "Контейнер не найден"

    logger.info("Контейнер %s перезапущен", container_name)
    return True, "Перезапущен"


# ─── Авторизация ─────────────────────────────────────────────────────────────

def check_user(update: Update) -> bool:
    """Проверка — является ли пользователь разрешённым."""
    user = update.effective_user
    if user is None:
        return False
    allowed = user.id == ALLOWED_USER_ID
    if not allowed:
        logger.warning("Отказано в доступе пользователю id=%d", user.id)
    return allowed


# ─── UI-хелперы ──────────────────────────────────────────────────────────────

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Список прокси", callback_data="proxy_list")],
        [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
        [InlineKeyboardButton("🔧 Управление", callback_data="proxy_manage")],
        [InlineKeyboardButton("ℹ️ Статус", callback_data="proxy_status")],
    ])


def build_proxy_row(name: str, is_running: bool) -> list[list[InlineKeyboardButton]]:
    """Строит строки кнопок для одного прокси в списке."""
    status_icon = "✅" if is_running else "❌"
    rows = [
        [InlineKeyboardButton(
            f"🔗 {status_icon} {name} — подключиться",
            callback_data=f"proxy_connect_{name}"
        )],
        [
            InlineKeyboardButton("▶️ Старт", callback_data=f"proxy_start_{name}"),
            InlineKeyboardButton("⏹ Стоп", callback_data=f"proxy_stop_{name}"),
            InlineKeyboardButton("🔄 Рестарт", callback_data=f"proxy_restart_{name}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"proxy_delete_confirm_{name}"),
        ],
    ]
    return rows


def build_status_text(proxies: dict, running: list[str]) -> str:
    """Строит текст статуса для всех прокси."""
    if not proxies:
        return "📭 Нет прокси\n\nИспользуйте <code>/proxy add &lt;порт&gt;</code> для добавления."
    lines = ["ℹ️ <b>Статус системы:</b>\n"]
    for name, data in proxies.items():
        port = data.get("port", "?")
        container_name = f"mtproto-{name}"
        icon = "✅" if container_name in running else "❌"
        lines.append(f"{icon} <b>{name}</b> — порт <code>{port}</code>")
    return "\n".join(lines)


# ─── Обработчики команд ──────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — главное меню."""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    await update.message.reply_text(
        "🔐 <b>MTProto Proxy Manager</b>\n\nВыберите действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help — справка."""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    text = (
        "📖 <b>Команды:</b>\n\n"
        "<code>/start</code> — Главное меню\n"
        "<code>/proxy add &lt;порт&gt;</code> — Добавить и запустить прокси\n"
        "<code>/help</code> — Эта справка\n\n"
        "<b>Пример:</b> <code>/proxy add 8443</code>\n\n"
        f"<b>Допустимый диапазон портов:</b> {PORT_MIN}–{PORT_MAX}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def proxy_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /proxy add <порт> — добавить прокси."""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    args = context.args or []

    # Разбор: /proxy add 8443  или  /proxy 8443
    if args and args[0] == "add":
        args = args[1:]

    if not args:
        await update.message.reply_text(
            "Использование: <code>/proxy add &lt;порт&gt;</code>\n"
            f"Пример: <code>/proxy add 8443</code>\n"
            f"Допустимый диапазон: {PORT_MIN}–{PORT_MAX}",
            parse_mode="HTML",
        )
        return

    try:
        port = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Порт должен быть числом.")
        return

    # Валидация диапазона
    valid, err = is_port_valid(port)
    if not valid:
        await update.message.reply_text(f"❌ {err}")
        return

    # Проверка занятости порта
    if is_port_in_use(port):
        await update.message.reply_text(
            f"❌ Порт <code>{port}</code> уже занят другим контейнером.",
            parse_mode="HTML",
        )
        return

    proxy_id = f"proxy{port}"
    config = load_config()

    if proxy_id in config.get("proxies", {}):
        await update.message.reply_text(f"⚠️ Прокси <code>{proxy_id}</code> уже существует!", parse_mode="HTML")
        return

    secret = generate_secret()
    config["proxies"][proxy_id] = {
        "secret": secret,
        "port": str(port),
        "status": "active",
        "owner": "admin",
    }

    if not save_config(config):
        await update.message.reply_text("❌ Не удалось сохранить конфиг. Проверьте права доступа.")
        return

    # Автозапуск
    success, msg_run = start_proxy_container(proxy_id, port, secret)
    http_link = f"https://t.me/proxy?server={SERVER_IP}&port={port}&secret={secret}"

    if success:
        text = (
            f"✅ <b>Прокси создан и запущен!</b>\n\n"
            f"• ID: <code>{proxy_id}</code>\n"
            f"• Сервер: <code>{SERVER_IP}</code>\n"
            f"• Порт: <code>{port}</code>\n\n"
            f'<a href="{http_link}">👆 Быстрое подключение</a>\n\n'
            f"<i>или вручную: Настройки → Прокси → Добавить → MTProto</i>"
        )
    else:
        text = (
            f"⚠️ <b>Прокси создан, но не запущен</b>\n\n"
            f"• ID: <code>{proxy_id}</code>\n"
            f"• Порт: <code>{port}</code>\n\n"
            f"Ошибка: <code>{msg_run}</code>\n\n"
            f"Запустите вручную через меню управления."
        )

    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
    logger.info("Прокси %s создан пользователем %d", proxy_id, update.effective_user.id)


# ─── Обработчик кнопок ───────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый диспетчер callback-кнопок."""
    query = update.callback_query
    await query.answer()

    if not check_user(update):
        await query.edit_message_text("⛔ Доступ запрещён")
        return

    data = query.data

    routes = {
        "main_menu":    lambda: show_main_menu(query),
        "proxy_list":   lambda: show_proxy_list(query),
        "proxy_add":    lambda: show_proxy_add(query),
        "proxy_status": lambda: show_proxy_status(query),
        "proxy_manage": lambda: show_proxy_manage(query),
    }

    if data in routes:
        await routes[data]()
    elif data.startswith("proxy_connect_"):
        await show_proxy_connect(query, data.removeprefix("proxy_connect_"))
    elif data.startswith("proxy_start_"):
        await action_start_proxy(query, data.removeprefix("proxy_start_"))
    elif data.startswith("proxy_stop_"):
        await action_stop_proxy(query, data.removeprefix("proxy_stop_"))
    elif data.startswith("proxy_restart_"):
        await action_restart_proxy(query, data.removeprefix("proxy_restart_"))
    elif data.startswith("proxy_delete_confirm_"):
        await show_delete_confirm(query, data.removeprefix("proxy_delete_confirm_"))
    elif data.startswith("proxy_delete_do_"):
        await action_delete_proxy(query, data.removeprefix("proxy_delete_do_"))
    else:
        logger.warning("Неизвестный callback: %s", data)


# ─── Экраны ──────────────────────────────────────────────────────────────────

async def show_main_menu(query):
    await query.edit_message_text(
        "🔐 <b>MTProto Proxy Manager</b>\n\nВыберите действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML",
    )


async def show_proxy_list(query):
    """Список прокси с кнопками управления."""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()

    if not proxies:
        await query.edit_message_text(
            "📭 Нет прокси. Добавьте первый!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
            ]),
        )
        return

    msg_lines = ["📋 <b>Список прокси:</b>\n"]
    keyboard = []

    for name, data in proxies.items():
        port = data.get("port", "?")
        container_name = f"mtproto-{name}"
        is_running = container_name in running
        status_icon = "✅" if is_running else "❌"

        msg_lines.append(f"{status_icon} <b>{name}</b> — порт <code>{port}</code>")
        keyboard.extend(build_proxy_row(name, is_running))

    keyboard.append([InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "\n".join(msg_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def show_proxy_add(query):
    """Инструкция по добавлению прокси."""
    await query.edit_message_text(
        "➕ <b>Добавить прокси</b>\n\n"
        "Отправьте команду в чат:\n\n"
        "<code>/proxy add 8443</code>\n\n"
        f"Где <code>8443</code> — любой свободный порт ({PORT_MIN}–{PORT_MAX}).\n\n"
        "После добавления прокси будет <b>автоматически запущен</b>.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]),
        parse_mode="HTML",
    )


async def show_proxy_status(query):
    """Статус всех прокси."""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()

    await query.edit_message_text(
        build_status_text(proxies, running),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="proxy_status")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]),
        parse_mode="HTML",
    )


async def show_proxy_manage(query):
    """Меню управления прокси."""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()

    if not proxies:
        await query.edit_message_text(
            "📭 Нет прокси для управления.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
            ]),
        )
        return

    msg_lines = ["🔧 <b>Управление прокси:</b>\n"]
    keyboard = []

    for name, data in proxies.items():
        port = data.get("port", "?")
        container_name = f"mtproto-{name}"
        is_running = container_name in running
        status = "✅ работает" if is_running else "❌ остановлен"

        msg_lines.append(f"• <b>{name}</b> (порт <code>{port}</code>) — {status}")
        keyboard.extend(build_proxy_row(name, is_running))

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "\n".join(msg_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def show_proxy_connect(query, proxy_id: str):
    """Данные для подключения к прокси."""
    config = load_config()
    proxy = config.get("proxies", {}).get(proxy_id)

    if not proxy:
        await query.edit_message_text(
            "❌ Прокси не найден.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 К списку", callback_data="proxy_list")],
            ]),
        )
        return

    secret = proxy.get("secret", "")
    port = proxy.get("port", "8443")
    http_link = f"https://t.me/proxy?server={SERVER_IP}&port={port}&secret={secret}"

    text = (
        f"🔗 <b>Прокси: {proxy_id}</b>\n\n"
        f"• Сервер: <code>{SERVER_IP}</code>\n"
        f"• Порт: <code>{port}</code>\n\n"
        f'<a href="{http_link}">👆 Быстрое подключение</a>\n\n'
        f"<i>или вручную:\n"
        f"Настройки → Прокси → Добавить\n"
        f"Тип: MTProto\n"
        f"Сервер: {SERVER_IP} Порт: {port}</i>"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 К списку", callback_data="proxy_list")],
        ]),
        parse_mode="HTML",
    )


async def show_delete_confirm(query, proxy_id: str):
    """Экран подтверждения удаления прокси."""
    await query.edit_message_text(
        f"🗑 <b>Удалить прокси <code>{proxy_id}</code>?</b>\n\n"
        "⚠️ Контейнер будет остановлен и удалён вместе с настройками.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"proxy_delete_do_{proxy_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data="proxy_list"),
            ],
        ]),
        parse_mode="HTML",
    )


# ─── Действия над прокси ────────────────────────────────────────────────────

async def action_start_proxy(query, proxy_id: str):
    config = load_config()
    proxy = config.get("proxies", {}).get(proxy_id)

    if not proxy:
        await query.answer("❌ Прокси не найден", show_alert=True)
        return

    port = proxy.get("port", "8443")
    secret = proxy.get("secret", "")
    success, msg = start_proxy_container(proxy_id, port, secret)

    if success:
        await query.answer(f"✅ {proxy_id} запущен!", show_alert=False)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)

    await show_proxy_list(query)


async def action_stop_proxy(query, proxy_id: str):
    success, msg = stop_proxy_container(proxy_id)

    if success:
        await query.answer(f"✅ {proxy_id} остановлен", show_alert=False)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)

    await show_proxy_list(query)


async def action_restart_proxy(query, proxy_id: str):
    success, msg = restart_proxy_container(proxy_id)

    if success:
        await query.answer(f"✅ {proxy_id} перезапущен", show_alert=False)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)

    await show_proxy_list(query)


async def action_delete_proxy(query, proxy_id: str):
    """Удаление прокси после подтверждения."""
    config = load_config()
    proxies = config.get("proxies", {})

    if proxy_id not in proxies:
        await query.answer("❌ Прокси не найден", show_alert=True)
        await show_proxy_list(query)
        return

    container_name = f"mtproto-{proxy_id}"
    subprocess.run(["docker", "stop", container_name], capture_output=True)
    subprocess.run(["docker", "rm", container_name], capture_output=True)

    del proxies[proxy_id]
    config["proxies"] = proxies

    if not save_config(config):
        await query.answer("❌ Ошибка сохранения конфига", show_alert=True)
        return

    logger.info("Прокси %s удалён", proxy_id)

    # Показываем обновлённый список (конфиг уже изменён)
    updated_proxies = config.get("proxies", {})
    running = get_running_containers()

    if not updated_proxies:
        await query.edit_message_text(
            f"✅ Прокси <code>{proxy_id}</code> удалён.\n\n📭 Список прокси пуст.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
            ]),
            parse_mode="HTML",
        )
        return

    msg_lines = [f"✅ Прокси <code>{proxy_id}</code> удалён.\n\n📋 <b>Список прокси:</b>\n"]
    keyboard = []

    for name, data in updated_proxies.items():
        port = data.get("port", "?")
        container_name = f"mtproto-{name}"
        is_running = container_name in running
        status_icon = "✅" if is_running else "❌"
        msg_lines.append(f"{status_icon} <b>{name}</b> — порт <code>{port}</code>")
        keyboard.extend(build_proxy_row(name, is_running))

    keyboard.append([InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "\n".join(msg_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# ─── Точка входа ─────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN не задан — выход")
        raise SystemExit(1)

    if not ALLOWED_USER_ID:
        logger.critical("ALLOWED_USER_ID не задан — выход")
        raise SystemExit(1)

    if not SERVER_IP:
        logger.warning("SERVER_IP не задан — ссылки на подключение будут некорректны")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("proxy", proxy_add))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("MTProto Proxy Bot запущен (allowed user: %d)", ALLOWED_USER_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
