# main.py
import logging
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode

from config import Config
from database.mongo import (
    add_session,
    get_all_sessions,
    delete_all_sessions,
    is_sudo,
    add_sudo,
    remove_sudo,
    get_all_sudos,
    get_bot_settings,
    update_bot_settings
)

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("StartLoveBot")

# ---------------- BOT INIT ----------------
app = Client(
    "startlove",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    parse_mode=ParseMode.HTML
)

# =====================================================
#                     START
# =====================================================
@app.on_message(filters.command("start"))
async def start(_, message):
    settings = await get_bot_settings()
    await message.reply_text(
        f"👋 <b>StartLove Bot Online</b>\n\n"
        f"🔐 Min Sessions: <code>{settings['min_sessions']}</code>\n"
        f"📢 Force Sub: <code>{settings['force_sub']}</code>"
    )

# =====================================================
#                SESSION SYSTEM
# =====================================================
@app.on_message(filters.command("addsession") & filters.private)
async def add_session_cmd(_, message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /addsession <session_string>")

    session = message.text.split(None, 1)[1]
    ok = await add_session(message.from_user.id, session)

    await message.reply_text(
        "✅ Session added successfully" if ok else "❌ Invalid or duplicate session"
    )

@app.on_message(filters.command("sessions") & filters.private)
async def count_sessions(_, message):
    sessions = await get_all_sessions()
    await message.reply_text(f"📊 Total Sessions: <b>{len(sessions)}</b>")

@app.on_message(filters.command("wipe_sessions") & filters.private)
async def wipe_sessions(_, message):
    result = await delete_all_sessions(message.from_user.id)
    await message.reply_text(f"🗑 Session wipe status: <b>{result}</b>")

# =====================================================
#                 SUDO SYSTEM
# =====================================================
@app.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_cmd(_, message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /addsudo <user_id>")

    uid = int(message.command[1])
    ok = await add_sudo(uid, message.from_user.id)
    await message.reply_text("✅ Sudo added" if ok else "❌ Owner only")

@app.on_message(filters.command("rmsudo") & filters.private)
async def remove_sudo_cmd(_, message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /rmsudo <user_id>")

    uid = int(message.command[1])
    ok = await remove_sudo(uid, message.from_user.id)
    await message.reply_text("✅ Sudo removed" if ok else "❌ Owner only")

@app.on_message(filters.command("sudolist") & filters.private)
async def sudo_list(_, message):
    sudos = await get_all_sudos()
    text = "👮 <b>Sudo Users</b>\n\n" + "\n".join(f"<code>{u}</code>" for u in sudos)
    await message.reply_text(text or "No sudos found")

# =====================================================
#               BOT SETTINGS (OWNER)
# =====================================================
@app.on_message(filters.command("setmin") & filters.private)
async def set_min_sessions(_, message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /setmin <number>")

    value = int(message.command[1])
    ok = await update_bot_settings(
        {"min_sessions": value},
        message.from_user.id
    )
    await message.reply_text("✅ Min sessions updated" if ok else "❌ Owner only")

@app.on_message(filters.command("forcesub") & filters.private)
async def force_sub(_, message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /forcesub <channel_username|off>")

    arg = message.command[1]
    value = None if arg.lower() == "off" else arg

    ok = await update_bot_settings(
        {"force_sub": value},
        message.from_user.id
    )
    await message.reply_text("✅ Force sub updated" if ok else "❌ Owner only")

# =====================================================
#                    RUN
# =====================================================
async def main():
    await app.start()
    logger.info("🚀 StartLove Bot Started")
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
