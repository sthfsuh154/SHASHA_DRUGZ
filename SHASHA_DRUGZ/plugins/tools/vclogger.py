import asyncio
import random
from logging import getLogger
from typing import Dict, Set

from pyrogram.raw import functions

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import mongodb
from SHASHA_DRUGZ.utils.database import get_assistant

LOGGER = getLogger(__name__)

# ════════════════════════════════════════════
# GLOBAL STATE
# ════════════════════════════════════════════
vc_active_users: Dict[int, Set[int]] = {}
active_vc_chats: Set[int] = set()
vc_logging_status: Dict[int, bool] = {}

vcloggerdb = mongodb.vclogger


# ════════════════════════════════════════════
# SMALL CAPS
# ════════════════════════════════════════════
def to_small_caps(text: str) -> str:
    mapping = {
        "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
        "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
        "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
        "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
        "y": "ʏ", "z": "ᴢ",
        "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ",
        "G": "ɢ", "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ",
        "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ",
        "S": "s", "T": "ᴛ", "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x",
        "Y": "ʏ", "Z": "ᴢ",
    }
    return "".join(mapping.get(c, c) for c in text)


# ════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════
async def load_vc_logger_status():
    """Load all enabled chats from DB and start their monitors."""
    try:
        enabled_chats = []
        async for doc in vcloggerdb.find({}):
            chat_id = doc.get("chat_id")
            status = doc.get("status", False)
            if chat_id is None:
                continue
            vc_logging_status[chat_id] = status
            if status:
                enabled_chats.append(chat_id)

        for chat_id in enabled_chats:
            asyncio.create_task(check_and_monitor_vc(chat_id))

        LOGGER.info(f"VC Logger: loaded {len(vc_logging_status)} chat(s), "
                    f"started monitors for {len(enabled_chats)} enabled chat(s).")
    except Exception as e:
        LOGGER.error(f"VC Logger load_vc_logger_status error: {e}")


async def get_vc_logger_status(chat_id: int) -> bool:
    """Return cached status, or fetch from DB. Defaults to True if not found."""
    if chat_id in vc_logging_status:
        return vc_logging_status[chat_id]
    try:
        doc = await vcloggerdb.find_one({"chat_id": chat_id})
        if doc:
            status = doc.get("status", True)
            vc_logging_status[chat_id] = status
            return status
    except Exception as e:
        LOGGER.error(f"get_vc_logger_status error for {chat_id}: {e}")
    return True


# ════════════════════════════════════════════
# VC PARTICIPANT FETCHING
# ════════════════════════════════════════════
async def get_group_call_participants(userbot, peer) -> list:
    """Fetch live VC participants via raw API. Returns [] when no VC is active."""
    try:
        full_chat = await userbot.invoke(
            functions.channels.GetFullChannel(channel=peer)
        )
        if not hasattr(full_chat.full_chat, "call") or not full_chat.full_chat.call:
            return []
        call = full_chat.full_chat.call
        participants = await userbot.invoke(
            functions.phone.GetGroupParticipants(
                call=call, ids=[], sources=[], offset="", limit=100
            )
        )
        return participants.participants
    except Exception as e:
        err = str(e).upper()
        if "420" in err:
            try:
                wait_time = int(err.split("FLOOD_WAIT_")[1].split("]")[0])
            except Exception:
                wait_time = 10
            LOGGER.warning(f"Flood wait {wait_time}s for VC participants fetch.")
            await asyncio.sleep(wait_time + 1)
            return await get_group_call_participants(userbot, peer)
        if any(x in err for x in ["GROUPCALL_NOT_FOUND", "CALL_NOT_FOUND", "NO_GROUPCALL"]):
            return []
        LOGGER.error(f"get_group_call_participants error: {e}")
        return []


# ════════════════════════════════════════════
# JOIN / LEAVE HANDLERS
# ════════════════════════════════════════════
async def handle_user_join(chat_id: int, user_id: int, userbot):
    """
    Post a permanent join notification via the userbot.
    The userbot is used (not app) because it is guaranteed to be
    a member of the group — it is the assistant monitoring the VC.
    Fires once per join; fires again if the user rejoins after leaving.
    """
    try:
        user = await userbot.get_users(user_id)
        name = to_small_caps((user.first_name or "Someone").strip())
        mention = f'<a href="tg://user?id={user_id}"><b>{name}</b></a>'

        messages = [
            f"🎤 {mention} <b>ᴊᴜsᴛ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ᴠᴄ – ʟᴇᴛ's ᴍᴀᴋᴇ ɪᴛ ʟɪᴠᴇʟʏ! 🎶</b>",
            f"✨ {mention} <b>ɪs ɴᴏᴡ ɪɴ ᴛʜᴇ ᴠᴄ – ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 💫</b>",
            f"🎵 {mention} <b>ʜᴀs ᴊᴏɪɴᴇᴅ – ʟᴇᴛ's ʀᴏᴄᴋ ᴛʜɪs ᴠɪʙᴇ! 🔥</b>",
        ]

        await userbot.send_message(chat_id, random.choice(messages), parse_mode="html")

    except Exception as e:
        LOGGER.error(f"handle_user_join error — user={user_id} chat={chat_id}: {e}")


async def handle_user_leave(chat_id: int, user_id: int, userbot):
    """
    Post a permanent leave notification via the userbot.
    Fires once per leave event; fires again if the user leaves again later.
    """
    try:
        user = await userbot.get_users(user_id)
        name = to_small_caps((user.first_name or "Someone").strip())
        mention = f'<a href="tg://user?id={user_id}"><b>{name}</b></a>'

        messages = [
            f"👋 {mention} <b>ʟᴇғᴛ ᴛʜᴇ ᴠᴄ – ʜᴏᴘᴇ ᴛᴏ sᴇᴇ ʏᴏᴜ ʙᴀᴄᴋ sᴏᴏɴ! 🌟</b>",
            f"🚪 {mention} <b>sᴛᴇᴘᴘᴇᴅ ᴏᴜᴛ – ᴅᴏɴ'ᴛ ᴛᴀᴋᴇ ᴛᴏᴏ ʟᴏɴɢ, ᴡᴇ'ʟʟ ᴍɪss ʏᴏᴜ! 💖</b>",
            f"✌️ {mention} <b>sᴀɪᴅ ɢᴏᴏᴅʙʏᴇ – ᴄᴏᴍᴇ ʙᴀᴄᴋ ᴀɴᴅ ᴊᴏɪɴ ᴛʜᴇ ғᴜɴ ᴀɢᴀɪɴ! 🎶</b>",
        ]

        await userbot.send_message(chat_id, random.choice(messages), parse_mode="html")

    except Exception as e:
        LOGGER.error(f"handle_user_leave error — user={user_id} chat={chat_id}: {e}")


# ════════════════════════════════════════════
# MONITOR LOOP
# ════════════════════════════════════════════
async def monitor_vc_chat(chat_id: int):
    """
    Polls VC participants every 5 seconds.
    Detects joins and leaves, then fires the relevant notification.
    Stops automatically when logging is disabled or the chat is removed
    from active_vc_chats.
    """
    userbot = await get_assistant(chat_id)
    if not userbot:
        LOGGER.warning(f"VC monitor: no assistant for chat={chat_id}, stopping.")
        active_vc_chats.discard(chat_id)
        return

    #LOGGER.info(f"VC monitor started: chat={chat_id}")

    while chat_id in active_vc_chats and await get_vc_logger_status(chat_id):
        try:
            peer = await userbot.resolve_peer(chat_id)
            participants_list = await get_group_call_participants(userbot, peer)

            new_users: Set[int] = set()
            for p in participants_list:
                if hasattr(p, "peer") and hasattr(p.peer, "user_id"):
                    new_users.add(p.peer.user_id)

            current_users = vc_active_users.get(chat_id, set())
            joined = new_users - current_users
            left = current_users - new_users

            if joined or left:
                tasks = (
                    [handle_user_join(chat_id, uid, userbot) for uid in joined]
                    + [handle_user_leave(chat_id, uid, userbot) for uid in left]
                )
                await asyncio.gather(*tasks, return_exceptions=True)

            vc_active_users[chat_id] = new_users

        except Exception as e:
            LOGGER.error(f"VC monitor poll error: chat={chat_id} — {e}")

        await asyncio.sleep(5)

    active_vc_chats.discard(chat_id)
    vc_active_users.pop(chat_id, None)
    LOGGER.info(f"VC monitor stopped: chat={chat_id}")


async def check_and_monitor_vc(chat_id: int):
    """Start the monitor for a chat if it is not already running."""
    if not await get_vc_logger_status(chat_id):
        return
    if chat_id in active_vc_chats:
        return
    userbot = await get_assistant(chat_id)
    if not userbot:
        LOGGER.warning(f"check_and_monitor_vc: no assistant for chat={chat_id}.")
        return
    try:
        active_vc_chats.add(chat_id)
        asyncio.create_task(monitor_vc_chat(chat_id))
    except Exception as e:
        LOGGER.error(f"check_and_monitor_vc error: chat={chat_id} — {e}")
        active_vc_chats.discard(chat_id)


# ════════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════════
async def initialize_vc_logger():
    """Called on bot startup to load DB state and launch all monitors."""
    await load_vc_logger_status()

# ════════════════════════════════════════════
# MODULE METADATA
# ════════════════════════════════════════════
__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_61"
__help__ = """
🔻 /vclogger ➠ ᴍᴀɴᴀɢᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ʟᴏɢɢɪɴɢ ᴏɴ ᴀ ɢʀᴏᴜᴘ
     • /vclogger on  → ᴇɴᴀʙʟᴇ ᴠᴄ ʟᴏɢɢɪɴɢ
     • /vclogger off → ᴅɪsᴀʙʟᴇ ᴠᴄ ʟᴏɢɢɪɴɢ
🔻 /resetvclogger ➠ ʀᴇsᴇᴛ ᴠᴄ ʟᴏɢɢᴇʀ ᴛᴏ ᴇɴᴀʙʟᴇᴅ ꜰᴏʀ ᴀʟʟ ᴄʜᴀᴛs (ʙᴏᴛ ᴏᴡɴᴇʀ ᴏɴʟʏ)
🔻 /reload_vclog ➠ ʀᴇʟᴏᴀᴅ ᴠᴄ ʟᴏɢɢᴇʀ sᴛᴀᴛᴜs ꜰʀᴏᴍ ᴅʙ (ʙᴏᴛ ᴏᴡɴᴇʀ ᴏɴʟʏ)
🔻 /vcstatus ➠ ᴅᴇʙᴜɢ ᴍᴏɴɪᴛᴏʀ sᴛᴀᴛᴇ (ᴘʀɪᴠᴀᴛᴇ)
"""
