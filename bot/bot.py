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

def load_config():
    """Загрузка конфигурации"""
    path = os.environ.get("CONFIG_PATH", "/app/config/proxies.json")
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return {"proxies": {}}

def save_config(data):
    """Сохранение конфигурации"""
    path = os.environ.get("CONFIG_PATH", "/app/config/proxies.json")
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def generate_secret():
    """Генерация нового секрета"""
    return secrets.token_hex(16)

def check_user(update: Update) -> bool:
    """Проверка разрешённого пользователя"""
    return update.effective_user.id == ALLOWED_USER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Список прокси", callback_data="proxy_list")],
        [InlineKeyboardButton("➕ Добавить прокси", callback_data="proxy_add")],
        [InlineKeyboardButton("ℹ️ Статус", callback_data="proxy_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔐 <b>MTProto Proxy Manager</b>\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    if not check_user(update):
        await query.edit_message_text("⛔ Доступ запрещён")
        return
    
    if query.data == "proxy_list":
        await show_proxy_list(query)
    elif query.data == "proxy_add":
        await show_proxy_add(query)
    elif query.data == "proxy_status":
        await show_proxy_status(query)
    elif query.data.startswith("proxy_connect_"):
        proxy_id = query.data.replace("proxy_connect_", "")
        await show_proxy_connect(query, proxy_id)
    elif query.data.startswith("proxy_delete_"):
        proxy_id = query.data.replace("proxy_delete_", "")
        await delete_proxy(query, proxy_id)

async def show_proxy_list(query):
    """Показать список прокси"""
    config = load_config()
    proxies = config.get("proxies", {})
    
    if not proxies:
        await query.edit_message_text("📭 Нет прокси. Добавьте первый!")
        return
    
    msg = "📋 <b>Список прокси:</b>\n\n"
    keyboard = []
    
    for name, data in proxies.items():
        status = "✅" if data.get("status") == "active" else "❌"
        msg += f"• <b>{name}</b> {status}\n"
        msg += f"  Порт: {data.get('port')}\n\n"
        keyboard.append([InlineKeyboardButton(f"🔗 Подключиться: {name}", callback_data=f"proxy_connect_{name}")])
        keyboard.append([InlineKeyboardButton(f"🗑️ Удалить: {name}", callback_data=f"proxy_delete_{name}")])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить", callback_data="proxy_add")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="HTML")

async def show_proxy_add(query):
    """Показать форму добавления"""
    await query.edit_message_text(
        "➕ <b>Добавить прокси</b>\n\n"
        "Используйте команду:\n"
        "<code>/proxy add 8443</code>\n\n"
        "Где 8443 - порт прокси",
        parse_mode="HTML"
    )

async def show_proxy_status(query):
    """Показать статус"""
    try:
        # Check if container is running
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=mtproto-", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )
        containers = result.stdout.strip().split("\n")
        
        msg = "ℹ️ <b>Статус системы:</b>\n\n"
        
        # Check each proxy port
        config = load_config()
        for name, data in config.get("proxies", {}).items():
            port = data.get("port", "")
            container_name = f"mtproto-{name}"
            
            if container_name in containers:
                msg += f"✅ <b>{name}</b> (порт {port}) - работает\n"
            else:
                msg += f"❌ <b>{name}</b> (порт {port}) - остановлен\n"
        
    except Exception as e:
        msg = f"Ошибка: {e}"
    
    await query.edit_message_text(msg, parse_mode="HTML")

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
    
    keyboard = [[InlineKeyboardButton("📋 К списку", callback_data="proxy_list")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

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
    
    await query.edit_message_text(f"✅ Прокси {proxy_id} удалён")

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
    config["proxies"][proxy_id] = {
        "secret": secret,
        "port": str(port),
        "status": "active",
        "owner": "admin"
    }
    save_config(config)
    
    # Start container (simplified - would need docker SDK)
    await update.message.reply_text(
        f"✅ Прокси создан!\n\n"
        f"ID: {proxy_id}\n"
        f"Порт: {port}\n"
        f"Секрет: {secret}\n\n"
        f"Для запуска перезапустите docker-compose"
    )

async def proxy_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список прокси"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    config = load_config()
    proxies = config.get("proxies", {})
    
    if not proxies:
        await update.message.reply_text("📭 Нет прокси")
        return
    
    msg = "📋 <b>Список прокси:</b>\n\n"
    for name, data in proxies.items():
        status = "✅" if data.get("status") == "active" else "❌"
        msg += f"• <b>{name}</b> {status}\n"
        msg += f"  Порт: {data.get('port')}\n\n"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def proxy_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус прокси"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )
        containers = result.stdout.strip().split("\n")
        
        config = load_config()
        proxies = config.get("proxies", {})
        
        msg = "ℹ️ <b>Статус:</b>\n\n"
        for name, data in proxies.items():
            container_name = f"mtproto-{name}"
            if container_name in containers:
                msg += f"✅ <b>{name}</b> - работает\n"
            else:
                msg += f"❌ <b>{name}</b> - остановлен\n"
        
    except Exception as e:
        msg = f"Ошибка: {e}"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка"""
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    text = """📖 <b>Команды:</b>

/start - Главное меню
/proxy add <порт> - Добавить прокси
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
