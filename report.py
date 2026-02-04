# main.py
import asyncio
import os
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import UserNotParticipant

from config import Config
from database.mongo import (
    add_session, get_sessions, is_sudo, get_bot_settings, 
    update_bot_settings, add_sudo, remove_sudo, get_all_sudos,
    cleanup_invalid_sessions, get_user_contribution_count
)
from utils.helpers import parse_target, auto_join, get_progress_card
from utils.user_guide import GUIDE_TEXT
from report import send_single_report

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OxyBot")

# --- PREFIX FIXED ---
RAW_P = getattr(Config, "PREFIX", ["/"])
if isinstance(RAW_P, list):
    PREFIXES = []
    for x in RAW_P:
        if isinstance(x, list): PREFIXES.extend([str(i) for i in x])
        else: PREFIXES.append(str(x))
    PREFIXES = list(set(PREFIXES))
else:
    PREFIXES = [str(RAW_P)]

app = Client("OxyBot", api_id=int(Config.API_ID), api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN, in_memory=True)
U_STATE = {}

async def verify_user(uid):
    try:
        s = await get_bot_settings()
        sudo = await is_sudo(uid)
        fsub = s.get("force_sub")
        if fsub and not sudo:
            try: await app.get_chat_member(f"@{fsub.lstrip('@')}", uid)
            except: return "JOIN_REQUIRED", fsub.lstrip("@")
        if not sudo and await get_user_contribution_count(uid) < 1:
            return "MIN_CONTRIBUTION", 1
        return "OK", None
    except: return "OK", None

@app.on_message(filters.command("start", prefixes=PREFIXES) & filters.private)
async def start_handler(client, message: Message):
    uid = message.from_user.id
    status, data = await verify_user(uid)
    pool = await get_sessions()
    if status == "JOIN_REQUIRED":
        return await message.reply_text(f"🛑 Join @{data} and /start again.")
    kb = [[InlineKeyboardButton("🚀 Launch Reporter", callback_data="launch_flow")],
          [InlineKeyboardButton("📂 Pool", callback_data="manage_sessions"), InlineKeyboardButton("📖 Guide", callback_data="open_guide")]]
    if uid == Config.OWNER_ID: kb.append([InlineKeyboardButton("⚙️ Owner", callback_data="owner_panel")])
    await message.reply_text(f"💎 **OxyReport v3.6**\nPool: `{len(pool)}` | Status: `Online`", reply_markup=InlineKeyboardMarkup(kb))

@app.on_callback_query()
async def cb_handler(client, cb: CallbackQuery):
    uid, data = cb.from_user.id, cb.data
    if data == "open_guide": return await cb.edit_message_text(GUIDE_TEXT, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start_back")]]))
    if data == "start_back": return await start_handler(client, cb.message)
    
    status, val = await verify_user(uid)
    if status != "OK" and data not in ["add_sess_p", "manage_sessions"]: return await cb.answer("Unlock pool first!", True)

    if data == "launch_flow":
        if not await is_sudo(uid): return await cb.answer("Sudo only!", True)
        all_s = await get_sessions()
        U_STATE[uid] = {"step": "WAIT_JOIN", "sessions": all_s}
        await cb.edit_message_text("🔗 **Invite Link:**\nSend Invite Link (t.me/+) if Private, or `/skip` for Public:")
    elif data == "manage_sessions":
        cnt = await get_user_contribution_count(uid)
        await cb.edit_message_text(f"📂 **Pool Stats**\nYour Sessions: **{cnt}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add More", callback_data="add_sess_p")], [InlineKeyboardButton("🔙 Back", callback_data="start_back")]]))
    elif data == "add_sess_p":
        U_STATE[uid] = {"step": "WAIT_SESS_ONLY"}
        await cb.edit_message_text("💾 Send **Pyrogram strings** (comma separated):")
    elif data.startswith("rc_"):
        U_STATE[uid]["code"], U_STATE[uid]["step"] = data.split("_")[1], "WAIT_DESC"
        await cb.edit_message_text("✏️ Enter Description:")

@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def msg_handler(client, message: Message):
    uid, txt = message.from_user.id, message.text
    if uid not in U_STATE: return
    state = U_STATE[uid]

    if state["step"] == "WAIT_SESS_ONLY":
        sess = [s.strip() for s in txt.split(",") if len(s.strip()) > 100]
        cnt = 0
        for s in sess:
            if await add_session(uid, s): cnt += 1
        await message.reply_text(f"✅ {cnt} saved!"); U_STATE.pop(uid)
    elif state["step"] == "WAIT_JOIN":
        state["join"] = txt if txt != "/skip" else None
        state["step"] = "WAIT_TARGET"
        await message.reply_text("🎯 **Target Link?**")
    elif state["step"] == "WAIT_TARGET":
        try:
            state["cid"], state["mid"] = parse_target(txt)
            state["url"], state["step"] = txt, "WAIT_REASON"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Spam", callback_data="rc_1"), InlineKeyboardButton("Violence", callback_data="rc_2")], [InlineKeyboardButton("Porn", callback_data="rc_4"), InlineKeyboardButton("Other", callback_data="rc_8")]])
            await message.reply_text("⚖️ Select Reason:", reply_markup=kb)
        except: await message.reply_text("❌ Invalid format!")
    elif state["step"] == "WAIT_DESC":
        state["desc"], state["step"] = txt, "WAIT_COUNT"
        await message.reply_text("🔢 Wave Count?")
    elif state["step"] == "WAIT_COUNT" and txt.isdigit():
        state["count"] = int(txt)
        asyncio.create_task(process_reports(message, state))
        U_STATE.pop(uid)

# --- WORKER LOGIC ---
async def start_instance(s, uid, i, join):
    try:
        cl = Client(name=f"c_{uid}_{i}", api_id=int(Config.API_ID), api_hash=Config.API_HASH, session_string=s, in_memory=True)
        await asyncio.wait_for(cl.start(), timeout=15)
        if join:
            try: await asyncio.wait_for(auto_join(cl, join), timeout=10)
            except: pass
        return cl
    except: return None

async def process_reports(msg, config):
    panel = await msg.reply_text("🛠️ **Initializing Workers...**")
    sessions = config.get("sessions", [])[:30]
    tasks = [start_instance(s, msg.from_user.id, i, config.get("join")) for i, s in enumerate(sessions)]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    clients = [c for c in results if c and not isinstance(c, Exception)]
    
    if not clients: return await panel.edit_text("❌ Initialization failed. Peer resolution issues.")
    
    suc, err, tot = 0, 0, config["count"]
    for i in range(tot):
        res = await send_single_report(clients[i % len(clients)], config["cid"], config["mid"], config["code"], config["desc"])
        if res: suc += 1
        else: err += 1
        if i % 3 == 0 or i == tot-1:
            try: await panel.edit_text(get_progress_card(config["url"], suc, err, tot, len(clients)))
            except: pass
        await asyncio.sleep(0.4)
    
    for c in clients: await c.stop()
    await msg.reply_text(f"🏁 Done! Successful: `{suc}`.")

if __name__ == "__main__":
    app.start()
    app.loop.create_task(cleanup_invalid_sessions())
    logger.info("Ultimate OxyReport Pro is powering up!")
    idle()
    app.stop()
