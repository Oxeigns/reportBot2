# report.py
import asyncio
import logging
from pyrogram import Client
from pyrogram.raw import functions, types
from pyrogram.errors import RPCError, FloodWait, PeerIdInvalid, ChannelInvalid

logger = logging.getLogger(__name__)

async def send_single_report(client: Client, chat_id: int | str, msg_id: int | None, reason_code: str, description: str):
    """
    ULTIMATE REPORT ENGINE v3.1: 
    Fixed 'Peer Id Invalid' and 'Initializing' hang issues.
    """
    try:
        # 1. ROBUST PEER RESOLUTION
        try:
            # Try direct resolution first
            peer = await client.resolve_peer(chat_id)
        except (PeerIdInvalid, ChannelInvalid, KeyError, ValueError):
            # Fallback: Force session to fetch chat metadata
            try:
                chat = await client.get_chat(chat_id)
                peer = await client.resolve_peer(chat.id)
            except Exception as e:
                logger.error(f"Worker {client.name} - Peer Resolution Failed: {e}")
                return False

        # 2. REASON MAPPING
        reasons = {
            '1': types.InputReportReasonSpam(),
            '2': types.InputReportReasonViolence(),
            '3': types.InputReportReasonChildAbuse(),
            '4': types.InputReportReasonPornography(),
            '5': types.InputReportReasonFake(),
            '6': types.InputReportReasonIllegalDrugs(),
            '7': types.InputReportReasonPersonalDetails(),
            '8': types.InputReportReasonOther()
        }
        selected_reason = reasons.get(str(reason_code), types.InputReportReasonOther())

        # 3. EXECUTION
        if msg_id:
            await client.invoke(
                functions.messages.Report(
                    peer=peer,
                    id=[int(msg_id)],
                    reason=selected_reason,
                    message=description
                )
            )
        else:
            await client.invoke(
                functions.account.ReportPeer(
                    peer=peer,
                    reason=selected_reason,
                    message=description
                )
            )
        return True

    except FloodWait as e:
        # SKIP if flood is too long (> 2 minutes) to keep reporting fast
        if e.value > 120:
            logger.warning(f"Worker {client.name} skipped: {e.value}s FloodWait")
            return False
        await asyncio.sleep(e.value)
        return await send_single_report(client, chat_id, msg_id, reason_code, description)

    except RPCError:
        return False
    except Exception:
        return False
