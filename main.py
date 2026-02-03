# main.py
import asyncio
import os
import sys
import logging

# Logging for Heroku stability
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait

from config import Config
from database.mongo import (
    add_session, get_sessions, delete_all_sessions, 
    is_sudo, get_bot_settings, update_bot_settings, 
    add_sudo, remove_sudo, get_all_sudos
)
from utils.helpers import parse_target, auto_join, get_progress_card
from utils.user_guide import GUIDE_TEXT
from report import send_single_report

app = Client(
    "UltimateReportBot", 
    api_id=Config.API_ID, 
    api_hash=Config.API_HASH, 
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

U_STATE = {}

async def verify_user(uid):
    settings = await get_bot_settings()
    sudo = await is_sudo(uid)
    
    # 1. Force Subscribe Check
    if settings.get("force_sub") and not sudo:
        try:
            # Bot must be admin in the channel
            await app.get_chat_member(settings['force_sub'], uid)
        except UserNotParticipant:
            return "JOIN_REQUIRED", settings["force_sub"]
        except Exception as e:
            logger.error(f"F-Sub Verification Error: {e}")
    
    # 2. Min Session Check (Bypassed for Sudo/Owner)
    if not sudo:
        sessions = await get_sessions(uid)
        min_s = settings.get("min_sessions", Config.DEFAULT_MIN_SESSIONS)
        if len(sessions) < min_s:
            return "MIN_SESS", min_s
            
    return "OK", None

@app.on_message(filters.command("start", Config.PREFIX) & filters.private)
async def start_handler(client, message: Message):
    uid = message.from_user.id
    status, data = await verify_user(uid)
    
    if status == "JOIN_REQUIRED":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{data}")]])
        return await message.reply_text(
            "🚫 **Access Denied!**\n\nYou must join our update channel to use this bot.", 
            reply_markup=kb
        )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Launch Reporter", callback_data="launch_flow")],
        [InlineKeyboardButton("📂 Manage Sessions", callback_data="manage_sessions"), InlineKeyboardButton("📖 User Guide", callback_data="open_guide")],
        [InlineKeyboardButton("⚙️ Owner Panel", callback_data="owner_panel")] if uid == Config.OWNER_ID else []
    ])
    await message.reply_text(f"💎 **Ultimate OxyReport Pro v3.0**\n\nWelcome {message.from_user.first_name}!", reply_markup=kb)

@app.on_callback_query()
async def cb_handler(client, cb: CallbackQuery):
    uid = cb.from_user.id
    data = cb.data
    
    # Global Force Sub Check for every button click
    if data not in ["open_guide", "start_back"]:
        status, val = await verify_user(uid)
        if status == "JOIN_REQUIRED":
            return await cb.answer("🚫 Join the channel first to unlock buttons!", show_alert=True)

    if data == "owner_panel" and uid == Config.OWNER_ID:
        setts = await get_bot_settings()
        kb = [[InlineKeyboardButton(f"Min Sessions: {setts.get('min_sessions', 3)}", callback_data="set_min")],
              [InlineKeyboardButton(f"F-Sub: @{setts.get('force_sub') or 'None'}", callback_data="set_fsub")],
              [InlineKeyboardButton("👤 Sudo List", callback_data="list_sudo"), InlineKeyboardButton("🔄 Restart", callback_data="restart_bot")],
              [InlineKeyboardButton("🔙 Back", callback_data="start_back")]]
        await cb.edit_message_text("⚙️ **Owner Control Panel**", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "launch_flow":
        kb = [[InlineKeyboardButton("✅ Use Saved Sessions", callback_data="choose_saved")],
              [InlineKeyboardButton("➕ Add New Sessions", callback_data="choose_new")],
              [InlineKeyboardButton("🔙 Back", callback_data="start_back")]]
        await cb.edit_message_text("🚀 **Select Session Source**\n\nDo you want to use database sessions or add temporary ones?", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "choose_saved":
        sessions = await get_sessions(uid)
        sudo = await is_sudo(uid)
        setts = await get_bot_settings()
        min_s = setts.get("min_sessions", 3)
        
        if not sudo and len(sessions) < min_s:
            return await cb.answer(f"⚠️ Saved sessions ({len(sessions)}) < Required ({min_s}).", show_alert=True)
        if not sessions and not sudo:
            return await cb.answer("❌ No sessions in database. Add them first!", show_alert=True)

        U_STATE[uid] = {"step": "WAIT_JOIN", "use_saved": True}
        await cb.edit_message_text("🔗 **Step 1: Invite Link**\n\nSend private invite link or `/skip` for public targets.")

    elif data == "choose_new":
        U_STATE[uid] = {"step": "WAIT_SESS_FLOW"}
        await cb.edit_message_text("📝 **Step 1: Temporary Sessions**\n\nSend your Pyrogram Session Strings (comma separated):")

    elif data == "manage_sessions":
        sessions = await get_sessions(uid)
        kb = [[InlineKeyboardButton("➕ Add New Sessions", callback_data="add_sess_p")],
              [InlineKeyboardButton("🗑️ Clear Sessions", callback_data="clear_sess_p")],
              [InlineKeyboardButton("🔙 Back", callback_data="start_back")]]
        await cb.edit_message_text(f"📂 **Session Manager**\nSaved in DB: **{len(sessions)}**", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "add_sess_p":
        U_STATE[uid] = {"step": "WAIT_SESS_ONLY"}
        await cb.edit_message_text("💾 **Add to Database**\n\nSend sessions to save permanently:")

    elif data == "clear_sess_p":
        await delete_all_sessions(uid)
        await cb.answer("✅ Database wiped!", show_alert=True)
        await cb.edit_message_text("📂 Sessions cleared.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="manage_sessions")]]))

    elif data == "list_sudo" and uid == Config.OWNER_ID:
        sudos = await get_all_sudos()
        text = "👤 **Sudo List:**\n" + "\n".join([f"`{s}`" for s in sudos]) if sudos else "None"
        await cb.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add", callback_data="add_sudo_p"), InlineKeyboardButton("➖ Rem", callback_data="rem_sudo_p")], [InlineKeyboardButton("🔙", callback_data="owner_panel")]]))

    elif data == "restart_bot" and uid == Config.OWNER_ID:
        await cb.answer("Restarting...", show_alert=True)
        os.execl(sys.executable, sys.executable, *sys.argv)

    elif data == "set_min" and uid == Config.OWNER_ID:
        U_STATE[uid] = {"step": "WAIT_MIN_SESS"}
        await cb.edit_message_text("🔢 Enter Minimum Sessions (Number):")

    elif data == "set_fsub" and uid == Config.OWNER_ID:
        U_STATE[uid] = {"step": "WAIT_FSUB"}
        await cb.edit_message_text("📢 Enter Channel Username (without @):")

    elif data == "add_sudo_p" and uid == Config.OWNER_ID:
        U_STATE[uid] = {"step": "WAIT_ADD_SUDO"}
        await cb.edit_message_text("👤 Enter User ID to add:")

    elif data == "rem_sudo_p" and uid == Config.OWNER_ID:
        U_STATE[uid] = {"step": "WAIT_REM_SUDO"}
        await cb.edit_message_text("👤 Enter User ID to remove:")

    elif data.startswith("rc_"):
        U_STATE[uid]["code"] = data.split("_")[1]
        U_STATE[uid]["step"] = "WAIT_DESC"
        await cb.edit_message_text("✏️ **Step 4: description**\n\nEnter custom report text:")

    elif data == "open_guide":
        await cb.edit_message_text(GUIDE_TEXT, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start_back")]]))

    elif data == "start_back":
        if uid in U_STATE: del U_STATE[uid]
        kb = [[InlineKeyboardButton("🚀 Launch Reporter", callback_data="launch_flow")],
              [InlineKeyboardButton("📂 Sessions", callback_data="manage_sessions"), InlineKeyboardButton("📖 Guide", callback_data="open_guide")],
              [InlineKeyboardButton("⚙️ Owner", callback_data="owner_panel")] if uid == Config.OWNER_ID else []]
        await cb.edit_message_text("💎 **Ultimate OxyReport Pro v3.0**", reply_markup=InlineKeyboardMarkup(kb))

@app.on_message(filters.private)
async def msg_handler(client, message: Message):
    uid = message.from_user.id
    if uid not in U_STATE: return
    state = U_STATE[uid]
    txt = message.text

    # Owner Controls
    if uid == Config.OWNER_ID:
        if state["step"] == "WAIT_MIN_SESS" and txt.isdigit():
            await update_bot_settings({"min_sessions": int(txt)})
            await message.reply_text(f"✅ Min sessions: {txt}"); del U_STATE[uid]; return
        elif state["step"] == "WAIT_FSUB":
            await update_bot_settings({"force_sub": txt.replace("@", "").strip()})
            await message.reply_text(f"✅ Force Sub: @{txt}"); del U_STATE[uid]; return
        elif state["step"] == "WAIT_ADD_SUDO" and txt.isdigit():
            await add_sudo(int(txt))
            await message.reply_text(f"✅ Added Sudo: {txt}"); del U_STATE[uid]; return
        elif state["step"] == "WAIT_REM_SUDO" and txt.isdigit():
            await remove_sudo(int(txt))
            await message.reply_text(f"✅ Removed Sudo: {txt}"); del U_STATE[uid]; return

    # User Logic
    if state["step"] == "WAIT_SESS_ONLY":
        sess = txt.split(",")
        [await add_session(uid, s.strip()) for s in sess if len(s.strip()) > 50]
        await message.reply_text("✅ Saved to DB!"); del U_STATE[uid]

    elif state["step"] == "WAIT_SESS_FLOW":
        valid = [s.strip() for s in txt.split(",") if len(s.strip()) > 50]
        st = await get_bot_settings(); ms = st.get("min_sessions", 3)
        if not await is_sudo(uid) and len(valid) < ms:
            return await message.reply_text(f"❌ Need {ms} sessions.")
        state["temp_sessions"] = valid
        state["step"] = "WAIT_JOIN"
        await message.reply_text("✅ Sessions OK.\n\n🔗 **Step 2: Private Join**\nSend invite link or `/skip`.")

    elif state["step"] == "WAIT_JOIN":
        state["join"] = txt if txt != "/skip" else None
        state["step"] = "WAIT_TARGET"
        await message.reply_text("🎯 **Step 3: Target Link**\n\nSend t.me/ url:")

    elif state["step"] == "WAIT_TARGET":
        try:
            state["cid"], state["mid"] = parse_target(txt)
            state["url"] = txt; state["step"] = "WAIT_REASON"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Spam", callback_data="rc_1"), InlineKeyboardButton("Porn", callback_data="rc_4")], [InlineKeyboardButton("Violence", callback_data="rc_2"), InlineKeyboardButton("Other", callback_data="rc_8")]])
            await message.reply_text("⚖️ **Step 4: Reason**", reply_markup=kb)
        except Exception as e: await message.reply_text(f"❌ {e}")

    elif state["step"] == "WAIT_DESC":
        state["desc"] = txt; state["step"] = "WAIT_COUNT"
        await message.reply_text("🔢 **Step 5: Count**\n\nHow many reports?")

    elif state["step"] == "WAIT_COUNT" and txt.isdigit():
        state["count"] = int(txt)
        asyncio.create_task(process_reports(message, state))
        del U_STATE[uid]

async def process_reports(msg, config):
    panel = await msg.reply_text("⏳ **Initializing...**")
    uid = msg.from_user.id
    sessions = await get_sessions(uid) if config.get("use_saved") else config.get("temp_sessions", [])
    if not sessions: return await panel.edit_text("❌ No sessions found.")

    clients = []
    for i, s in enumerate(sessions):
        c = Client(name=f"c_{uid}_{i}_{asyncio.get_event_loop().time()}", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=s, in_memory=True)
        try:
            await c.start()
            if config["join"]: await auto_join(c, config["join"])
            clients.append(c)
        except: continue
    
    if not clients: return await panel.edit_text("❌ Connection failed.")
    
    success, failed = 0, 0
    for i in range(config["count"]):
        res = await send_single_report(clients[i % len(clients)], config["cid"], config["mid"], config["code"], config["desc"])
        if res: success += 1
        else: failed += 1
        if i % 5 == 0 or i == config["count"] - 1:
            try: await panel.edit_text(get_progress_card(config["url"], success, failed, config["count"], len(clients)))
            except: pass
        await asyncio.sleep(0.3)
    for c in clients: await c.stop()
    await msg.reply_text("🏁 Task Done!")

async def start_bot():
    await app.start()
    logger.info("Ultimate OxyReport Bot Online!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(start_bot())
