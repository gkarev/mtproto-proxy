#!/usr/bin/env python3
"""
MTProto Proxy Telegram Bot
Управление MTProto прокси через Telegram
"""
import os
import json
import subprocess
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Конфигурация из переменных окружения
SERVER_IP = os.environ.get("SERVER_IP", "127.0.0.1")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

# Путь к конфигу
CONFIG_PATH = "/app/config/proxies.json"
MTG_IMAGE = "mtproto-mtg:latest"

def load_config():
    """Загрузка конфигурации"""
    path = os.environ.get("CONFIG_PATH", CONFIG_PATH)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return {"proxies": {}}

def save_config(data):
    """Сохранение конфигурации"""
    path = os.environ.get("CONFIG_PATH", CONFIG_PATH)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def generate_secret():
    """Генерация нового секрета"""
    return secrets.token_hex(16)

def get_running_containers():
    """Получить список работающих контейнеров"""
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=mtproto-", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    return [c for c in result.stdout.strip().split("\n") if c]

def start_proxy_container(proxy_id, port, secret):
    """Запустить контейнер прокси"""
    container_name = f"mtproto-{proxy_id}"
    
    # Check if already running
    if container_name in get_running_containers():
        return False, "Уже запущен"
    
    # Stop old container if exists
    subprocess.run(["docker", "stop", container_name], capture_output=True)
    subprocess.run(["docker", "rm", container_name], capture_output=True)
    
    # Run new container
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:8443",
        "-v", f"{os.environ.get('CONFIG_PATH', '/app/config/proxies.json').replace('proxies.json', '')}:/app/config:ro",
        "-e", f"PROXY_ID={proxy_id}",
        MTG_IMAGE
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        return False, f"Ошибка: {result.stderr}"
    
    return True, "Запущен"

def stop_proxy_container(proxy_id):
    """Остановить контейнер прокси"""
    container_name = f"mtproto-{proxy_id}"
    result = subprocess.run(["docker", "stop", container_name], capture_output=True, text=True)
    
    if result.returncode != 0:
        return False, "Контейнер не найден или уже остановлен"
    
    return True, "Остановлен"

def restart_proxy_container(proxy_id):
    """Перезапустить контейнер прокси"""
    container_name = f"mtproto-{proxy_id}"
    result = subprocess.run(["docker", "restart", container_name], capture_output=True, text=True)
    
    if result.returncode != 0:
        return False, "Контейнер не найден"
    
    return True, "Перезапущен"

def check_user(update: Update) -> bool:
    """Проверка разрешённого пользователя"""
    return update.effective_user.id == ALLOWED_USER_ID

def get_main_menu_keyboard():
    """Главное меню"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Список прокси", callback_data="proxy_list")],
        [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
        [InlineKeyboardButton("🔧 Управление", callback_data="proxy_manage")],
        [InlineKeyboardButton("ℹ️ Статус", callback_data="proxy_status")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    await update.message.reply_text(
        "🔐 <b>MTProto Proxy Manager</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    if not check_user(update):
        await query.edit_message_text("⛔ Доступ запрещён")
        return
    
    # Navigation
    if query.data == "main_menu":
        await show_main_menu(query)
    elif query.data == "proxy_list":
        await show_proxy_list(query)
    elif query.data == "proxy_add":
        await show_proxy_add(query)
    elif query.data == "proxy_status":
        await show_proxy_status(query)
    elif query.data == "proxy_manage":
        await show_proxy_manage(query)
    # Connect
    elif query.data.startswith("proxy_connect_"):
        proxy_id = query.data.replace("proxy_connect_", "")
        await show_proxy_connect(query, proxy_id)
    # Delete
    elif query.data.startswith("proxy_delete_"):
        proxy_id = query.data.replace("proxy_delete_", "")
        await delete_proxy(query, proxy_id)
    # Start
    elif query.data.startswith("proxy_start_"):
        proxy_id = query.data.replace("proxy_start_", "")
        await start_proxy(query, proxy_id)
    # Stop
    elif query.data.startswith("proxy_stop_"):
        proxy_id = query.data.replace("proxy_stop_", "")
        await stop_proxy(query, proxy_id)
    # Restart
    elif query.data.startswith("proxy_restart_"):
        proxy_id = query.data.replace("proxy_restart_", "")
        await restart_proxy(query, proxy_id)

async def show_main_menu(query):
    """Показать главное меню"""
    await query.edit_message_text(
        "🔐 <b>MTProto Proxy Manager</b>\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )

async def show_proxy_list(query):
    """Показать список прокси"""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()
    
    if not proxies:
        await query.edit_message_text(
            "📭 Нет прокси. Добавьте первый!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ])
        )
        return
    
    msg = "📋 <b>Список прокси:</b>\n\n"
    keyboard = []
    
    for name, data in proxies.items():
        container_name = f"mtproto-{name}"
        status = "✅" if container_name in running else "❌"
        msg += f"• <b>{name}</b> {status}\n"
        msg += f"  Порт: {data.get('port')}\n\n"
        
        keyboard.append([InlineKeyboardButton(f"🔗 Подключиться: {name}", callback_data=f"proxy_connect_{name}")])
        keyboard.append([
            InlineKeyboardButton("▶️", callback_data=f"proxy_start_{name}"),
            InlineKeyboardButton("⏹️", callback_data=f"proxy_stop_{name}"),
            InlineKeyboardButton("🔄", callback_data=f"proxy_restart_{name}"),
            InlineKeyboardButton("🗑️", callback_data=f"proxy_delete_{name}")
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def show_proxy_add(query):
    """Показать форму добавления"""
    await query.edit_message_text(
        "➕ <b>Добавить прокси</b>\n\n"
        "Используйте команду:\n"
        "<code>/proxy add 8443</code>\n\n"
        "Где 8443 - порт прокси\n\n"
        "После добавления прокси будет <b>автоматически запущен</b>!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

async def show_proxy_status(query):
    """Показать статус"""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()
    
    msg = "ℹ️ <b>Статус системы:</b>\n\n"
    
    if not proxies:
        msg = "📭 Нет прокси\n\n"
    
    for name, data in proxies.items():
        port = data.get("port", "")
        container_name = f"mtproto-{name}"
        
        if container_name in running:
            msg += f"✅ <b>{name}</b> (порт {port}) - работает\n"
        else:
            msg += f"❌ <b>{name}</b> (порт {port}) - остановлен\n"
    
    await query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

async def show_proxy_manage(query):
    """Меню управления прокси"""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()
    
    if not proxies:
        await query.edit_message_text(
            "📭 Нет прокси для управления",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ])
        )
        return
    
    msg = "🔧 <b>Управление прокси:</b>\n\n"
    keyboard = []
    
    for name, data in proxies.items():
        port = data.get("port", "")
        container_name = f"mtproto-{name}"
        status = "▶️ Запустить" if container_name not in running else "⏹️ Остановить"
        
        keyboard.append([
            InlineKeyboardButton(f"▶️ {name}", callback_data=f"proxy_start_{name}"),
            InlineKeyboardButton(f"⏹️ {name}", callback_data=f"proxy_stop_{name}")
        ])
        keyboard.append([
            InlineKeyboardButton(f"🔄 Перезапустить {name}", callback_data=f"proxy_restart_{name}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def show_proxy_connect(query, proxy_id):
    """Показать данные для подключения"""
    config = load_config()
    proxies = config.get("proxies", {})
    proxy = proxies.get(proxy_id, {})
    
    if not proxy:
        await query.edit_message_text("❌ Прокси не найден")
        return
    
    secret = proxy.get("secret", "")
    port = proxy.get("port", "8443")
    http_link = f"https://t.me/proxy?server={SERVER_IP}&port={port}&secret={secret}"
    
    text = f"""🔗 <b>Прокси: {proxy_id}</b>

<b>Настройки:</b>
• Сервер: <code>{SERVER_IP}</code>
• Порт: <code>{port}</code>

<b>Подключение:</b>

<a href="{http_link}">👆 Нажмите для быстрого подключения</a>

или вручную:
• Настройки → Настройки прокси → Добавить
• Тип: MTProto
• Сервер: <code>{SERVER_IP}</code>
• Порт: <code>{port}</code>"""
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 К списку", callback_data="proxy_list")]
        ]),
        parse_mode="HTML"
    )

async def start_proxy(query, proxy_id):
    """Запустить прокси"""
    config = load_config()
    proxies = config.get("proxies", {})
    
    if proxy_id not in proxies:
        await query.answer("❌ Прокси не найден", show_alert=True)
        return
    
    proxy = proxies[proxy_id]
    port = proxy.get("port", "8443")
    secret = proxy.get("secret", "")
    
    success, msg = start_proxy_container(proxy_id, port, secret)
    
    if success:
        await query.answer(f"✅ {proxy_id} запущен!", show_alert=True)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)
    
    await show_proxy_list(query)

async def stop_proxy(query, proxy_id):
    """Остановить прокси"""
    success, msg = stop_proxy_container(proxy_id)
    
    if success:
        await query.answer(f"✅ {proxy_id} остановлен!", show_alert=True)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)
    
    await show_proxy_list(query)

async def restart_proxy(query, proxy_id):
    """Перезапустить прокси"""
    success, msg = restart_proxy_container(proxy_id)
    
    if success:
        await query.answer(f"✅ {proxy_id} перезапущен!", show_alert=True)
    else:
        await query.answer(f"⚠️ {msg}", show_alert=True)
    
    await show_proxy_list(query)

async def delete_proxy(query, proxy_id):
    """Удалить прокси"""
    config = load_config()
    proxies = config.get("proxies", {})
    
    if proxy_id not in proxies:
        await query.edit_message_text("❌ Прокси не найден")
        return
    
    # Stop and remove container
    container_name = f"mtproto-{proxy_id}"
    subprocess.run(["docker", "stop", container_name], capture_output=True)
    subprocess.run(["docker", "rm", container_name], capture_output=True)
    
    # Remove from config
    del proxies[proxy_id]
    config["proxies"] = proxies
    save_config(config)
    
    await query.answer(f"✅ {proxy_id} удалён!", show_alert=True)
    await show_proxy_list(query)

async def proxy_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить прокси"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    # Get port from command
    if not context.args:
        await update.message.reply_text(
            "Использование: /proxy add <порт>\n"
            "Пример: /proxy add 8443"
        )
        return
    
    # Handle /proxy add <port> or /proxy <port>
    port_arg = context.args[0]
    
    # If first arg is "add", use second arg
    if port_arg == "add":
        if len(context.args) < 2:
            await update.message.reply_text("Укажите порт: /proxy add 8443")
            return
        port_arg = context.args[1]
    
    try:
        port = int(port_arg)
    except ValueError:
        await update.message.reply_text("Порт должен быть числом")
        return
    
    # Generate secret
    proxy_id = f"proxy{port}"
    secret = generate_secret()
    
    # Add to config
    config = load_config()
    
    if proxy_id in config.get("proxies", {}):
        await update.message.reply_text(f"⚠️ Прокси {proxy_id} уже существует!")
        return
    
    config["proxies"][proxy_id] = {
        "secret": secret,
        "port": str(port),
        "status": "active",
        "owner": "admin"
    }
    save_config(config)
    
    # Auto-start container
    success, msg = start_proxy_container(proxy_id, port, secret)
    
    if success:
        await update.message.reply_text(
            f"✅ Прокси создан и запущен!\n\n"
            f"ID: <code>{proxy_id}</code>\n"
            f"Порт: <code>{port}</code>\n"
            f"Секрет: <code>{secret}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"✅ Прокси создан, но не запущен!\n\n"
            f"ID: <code>{proxy_id}</code>\n"
            f"Порт: <code>{port}</code>\n"
            f"Секрет: <code>{secret}</code>\n\n"
            f"Ошибка: {msg}",
            parse_mode="HTML"
        )

async def proxy_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список прокси"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()
    
    if not proxies:
        await update.message.reply_text("📭 Нет прокси")
        return
    
    msg = "📋 <b>Список прокси:</b>\n\n"
    for name, data in proxies.items():
        container_name = f"mtproto-{name}"
        status = "✅" if container_name in running else "❌"
        msg += f"• <b>{name}</b> {status}\n"
        msg += f"  Порт: {data.get('port')}\n\n"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def proxy_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус прокси"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    await show_proxy_status_command(update)

async def show_proxy_status_command(update):
    """Показать статус (для команды)"""
    config = load_config()
    proxies = config.get("proxies", {})
    running = get_running_containers()
    
    msg = "ℹ️ <b>Статус:</b>\n\n"
    for name, data in proxies.items():
        container_name = f"mtproto-{name}"
        if container_name in running:
            msg += f"✅ <b>{name}</b> - работает\n"
        else:
            msg += f"❌ <b>{name}</b> - остановлен\n"
    
    if update.message:
        await update.message.reply_text(msg, parse_mode="HTML")
    else:
        return msg

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    text = """📖 <b>Команды:</b>

/start - Главное меню
/proxy add <порт> - Добавить прокси (автозапуск!)
/proxy list - Список прокси
/proxy status - Статус
/help - Эта справка

Пример: /proxy add 8443"""
    
    await update.message.reply_text(text, parse_mode="HTML")

def main():
    """Запуск бота"""
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set")
        return
    
    if not ALLOWED_USER_ID:
        print("Error: ALLOWED_USER_ID not set")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("proxy", proxy_add))
    app.add_handler(CommandHandler("proxy_list", proxy_list))
    app.add_handler(CommandHandler("proxy_status", proxy_status))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("MTProto Proxy Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
