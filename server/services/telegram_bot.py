import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from server.config import load_settings, load_servers
from server.services.monitor import get_all_metrics, collect_server_metrics

logger = logging.getLogger(__name__)

bot_app: Optional[Application] = None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    servers = load_servers()
    metrics = get_all_metrics()

    online = sum(1 for s in servers if metrics.get(s["host"], {}).get("online", False))
    offline = len(servers) - online

    text = (
        f"🖥 **VPS Monitoring**\n\n"
        f"Серверов: {len(servers)}\n"
        f"🟢 Online: {online}\n"
        f"🔴 Offline: {offline}\n\n"
        f"Последнее обновление: {datetime.now().strftime('%H:%M:%S')}"
    )

    keyboard = [
        [InlineKeyboardButton("📊 Статус серверов", callback_data="status")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
        [InlineKeyboardButton("⚙️ Управление", callback_data="manage")],
    ]

    # Add Web App button if available
    webapp_url = f"http://{_get_host()}:8000/telegram-app"
    keyboard.append([
        InlineKeyboardButton("📱 Открыть панель", web_app=WebAppInfo(url=webapp_url))
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    servers = load_servers()
    metrics = get_all_metrics()

    if not servers:
        await query.edit_message_text("Нет добавленных серверов")
        return

    text = "📊 **Статус серверов:**\n\n"
    for srv in servers:
        m = metrics.get(srv["host"], {})
        status = "🟢" if m.get("online") else "🔴"
        cpu = m.get("cpu_percent", 0)
        ram = m.get("ram_percent", 0)
        disk = m.get("disk_percent", 0)
        text += (
            f"{status} **{srv['name']}** ({srv['host']})\n"
            f"   CPU: {cpu}% | RAM: {ram}% | Disk: {disk}%\n\n"
        )

    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="status")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


async def manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    servers = load_servers()
    keyboard = []

    for i, srv in enumerate(servers):
        keyboard.append([
            InlineKeyboardButton(f"🖥 {srv['name']}", callback_data=f"server_{i}")
        ])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    await query.edit_message_text(
        "⚙️ **Управление серверами:**\nВыберите сервер:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def server_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("server_"):
        idx = int(data.split("_")[1])
        servers = load_servers()
        if idx >= len(servers):
            await query.edit_message_text("Сервер не найден")
            return

        srv = servers[idx]
        metrics = get_all_metrics()
        m = metrics.get(srv["host"], {})

        status = "🟢 Online" if m.get("online") else "🔴 Offline"
        text = (
            f"🖥 **{srv['name']}**\n"
            f"Host: `{srv['host']}`\n"
            f"Status: {status}\n"
            f"CPU: {m.get('cpu_percent', 0)}%\n"
            f"RAM: {m.get('ram_percent', 0)}% ({m.get('ram_used_mb', 0):.0f}/{m.get('ram_total_mb', 0):.0f} MB)\n"
            f"Disk: {m.get('disk_percent', 0)}% ({m.get('disk_used_gb', 0):.1f}/{m.get('disk_total_gb', 0):.1f} GB)\n"
            f"Uptime: {m.get('uptime', 'N/A')}\n"
            f"Load: {m.get('load_average', 'N/A')}\n"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Перезагрузить", callback_data=f"reboot_{idx}")],
            [InlineKeyboardButton("📊 Обновить метрики", callback_data=f"refresh_{idx}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="manage")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )

    elif data.startswith("reboot_"):
        idx = int(data.split("_")[1])
        servers = load_servers()
        if idx >= len(servers):
            return

        srv = servers[idx]
        keyboard = [
            [InlineKeyboardButton("✅ Да, перезагрузить", callback_data=f"confirm_reboot_{idx}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"server_{idx}")],
        ]
        await query.edit_message_text(
            f"⚠️ Перезагрузить сервер **{srv['name']}** ({srv['host']})?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )

    elif data.startswith("confirm_reboot_"):
        idx = int(data.split("_")[2])
        servers = load_servers()
        if idx >= len(servers):
            return

        srv = servers[idx]
        try:
            import asyncssh
            conn_kwargs = {
                "host": srv["host"],
                "port": srv.get("port", 22),
                "username": srv.get("username", "root"),
                "known_hosts": None,
            }
            if srv.get("password"):
                conn_kwargs["password"] = srv["password"]

            async with asyncssh.connect(**conn_kwargs) as conn:
                await conn.run("reboot", check=False)

            await query.edit_message_text(
                f"✅ Команда перезагрузки отправлена на **{srv['name']}**",
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Ошибка: {e}",
                parse_mode="Markdown",
            )

    elif data.startswith("refresh_"):
        idx = int(data.split("_")[1])
        servers = load_servers()
        if idx >= len(servers):
            return

        srv = servers[idx]
        await query.edit_message_text("⏳ Собираю метрики...")

        from server.services.monitor import metrics_cache
        result = await collect_server_metrics(srv)
        metrics_cache[srv["host"]] = result

        # Re-show server info
        context.user_data["refresh_target"] = idx
        await server_action_callback(update, context)

    elif data == "refresh":
        await status_callback(update, context)

    elif data == "back":
        # Simulate /start
        servers = load_servers()
        metrics = get_all_metrics()
        online = sum(1 for s in servers if metrics.get(s["host"], {}).get("online", False))
        offline = len(servers) - online

        text = (
            f"🖥 **VPS Monitoring**\n\n"
            f"Серверов: {len(servers)}\n"
            f"🟢 Online: {online}\n"
            f"🔴 Offline: {offline}\n\n"
            f"Последнее обновление: {datetime.now().strftime('%H:%M:%S')}"
        )
        keyboard = [
            [InlineKeyboardButton("📊 Статус серверов", callback_data="status")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
            [InlineKeyboardButton("⚙️ Управление", callback_data="manage")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )


async def send_alert(message: str):
    """Send alert to Telegram chat."""
    settings = load_settings()
    token = settings.get("telegram_bot_token")
    chat_id = settings.get("telegram_chat_id")

    if not token or not chat_id:
        return

    try:
        if bot_app and bot_app.bot:
            await bot_app.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")


def _get_host():
    """Get public host for web app URL."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


async def start_bot():
    """Initialize and start the Telegram bot."""
    global bot_app

    settings = load_settings()
    token = settings.get("telegram_bot_token")

    if not token:
        logger.warning("Telegram bot token not configured")
        return

    bot_app = Application.builder().token(token).build()

    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CallbackQueryHandler(status_callback, pattern="^status$"))
    bot_app.add_handler(CallbackQueryHandler(manage_callback, pattern="^manage$"))
    bot_app.add_handler(CallbackQueryHandler(server_action_callback, pattern="^(server_|reboot_|confirm_reboot_|refresh_|refresh$|back$)"))

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")


async def stop_bot():
    """Stop the Telegram bot."""
    global bot_app
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        bot_app = None
