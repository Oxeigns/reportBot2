# utils/helpers.py
import re
import asyncio
from pyrogram import Client, functions, types

def parse_target(url: str):
    """Link se Chat ID aur Message ID nikalne ke liye logic"""
    url = url.strip()
    # Handle private channel links (t.me/c/...) and public links
    m = re.search(r"(?:t\.me|telegram\.me)/(c/)?([^/]+)/?(\d+)?", url)
    if not m:
        raise ValueError("Invalid Link Format! Please send a valid t.me link.")
    
    is_private = m.group(1) == "c/"
    chat_part = m.group(2)
    msg_id = m.group(3)

    if not msg_id:
        # Agar sirf profile link ho toh profile report logic
        chat_id = int("-100" + chat_part) if is_private else chat_part
        return chat_id, None
    
    if is_private:
        chat_id = int("-100" + chat_part)
    else:
        chat_id = chat_part if not chat_part.isdigit() else int(chat_part)
        
    return chat_id, int(msg_id)

async def auto_join(client: Client, invite_link: str):
    """Reporting se pehle channel join karne ka logic"""
    try:
        if "t.me/+" in invite_link or "t.me/joinchat/" in invite_link:
            hash_code = invite_link.split("+")[-1] if "+" in invite_link else invite_link.split("/")[-1]
            await client.invoke(functions.messages.ImportChatInvite(hash=hash_code))
        else:
            username = invite_link.split("/")[-1]
            await client.join_chat(username)
        return True
    except Exception:
        return False

def get_progress_card(target, success, failed, total, sessions_count):
    """Live Reporting Panel ka Design (Advanced UI)"""
    percentage = (success + failed) / total * 100
    p_bar = "🟢" * int(percentage / 10) + "⚪" * (10 - int(percentage / 10))
    
    card = (
        f"📊 **Ultimate Live Report Panel**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **Target:** `{target}`\n"
        f"📈 **Progress:** `{percentage:.1f}%`\n"
        f"|{p_bar}|\n\n"
        f"✅ **Success:** `{success}`\n"
        f"❌ **Failed:** `{failed}`\n"
        f"🔢 **Total Requested:** `{total}`\n"
        f"🧵 **Active Sessions:** `{sessions_count}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ **Status:** `Processing Cloud Queries...`"
    )
    return card
