"""
assistant_guard.py
──────────────────
Auto-unban + auto-join the assistant userbot whenever a /play command is
issued in a group where the assistant is missing or banned.
"""
import asyncio
import logging
from functools import wraps
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    InviteHashExpired,
    InviteHashInvalid,
    InviteRequestSent,
    PeerIdInvalid,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from pyrogram.types import Message
from SHASHA_DRUGZ.utils.database import get_assistant

logger = logging.getLogger("assistant_guard")

# ──────────────────────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────
async def _get_assistant_status(bot_client, chat_id: int, assistant_id: int) -> ChatMemberStatus | None:
    try:
        member = await bot_client.get_chat_member(chat_id, assistant_id)
        return member.status
    except (UserNotParticipant, PeerIdInvalid):
        return None
    except Exception as e:
        logger.debug(f"_get_assistant_status [{chat_id}]: {e}")
        return None

async def _bot_can_ban(bot_client, chat_id: int) -> bool:
    try:
        me = await bot_client.get_chat_member(chat_id, bot_client.me.id)
        if me.status == ChatMemberStatus.ADMINISTRATOR:
            return bool(me.privileges and me.privileges.can_restrict_members)
        return False
    except Exception:
        return False

async def _bot_can_invite(bot_client, chat_id: int) -> bool:
    try:
        me = await bot_client.get_chat_member(chat_id, bot_client.me.id)
        if me.status == ChatMemberStatus.ADMINISTRATOR:
            return bool(me.privileges and me.privileges.can_invite_users)
        return False
    except Exception:
        return False

async def _try_unban(bot_client, chat_id: int, assistant_id: int) -> bool:
    try:
        await bot_client.unban_chat_member(chat_id, assistant_id)
        logger.info(f"[assistant_guard] Unbanned assistant {assistant_id} in {chat_id}")
        return True
    except ChatAdminRequired:
        logger.warning(f"[assistant_guard] Bot lacks ban rights in {chat_id}")
        return False
    except FloodWait as e:
        logger.warning(f"[assistant_guard] FloodWait {e.value}s during unban in {chat_id}")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.warning(f"[assistant_guard] Unban failed in {chat_id}: {e}")
        return False

async def _try_join_via_username(bot_client, userbot, chat_id: int) -> bool:
    try:
        chat = await bot_client.get_chat(chat_id)
        username = chat.username
    except Exception as e:
        logger.debug(f"[assistant_guard] get_chat failed for {chat_id}: {e}")
        return False
    if not username:
        return False
    try:
        await userbot.join_chat(username)
        logger.info(f"[assistant_guard] Assistant joined {chat_id} via username")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        try:
            await bot_client.approve_chat_join_request(chat_id, userbot.me.id)
            return True
        except Exception:
            return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Username join failed in {chat_id}: {e}")
        return False

async def _try_join_via_invite(bot_client, userbot, chat_id: int) -> bool:
    try:
        link_obj = await bot_client.create_chat_invite_link(chat_id)
        link = link_obj.invite_link
        await asyncio.sleep(1)
        await userbot.join_chat(link)
        logger.info(f"[assistant_guard] Assistant joined {chat_id} via invite link")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        try:
            await bot_client.approve_chat_join_request(chat_id, userbot.me.id)
            return True
        except Exception:
            return False
    except (InviteHashExpired, InviteHashInvalid):
        logger.warning(f"[assistant_guard] Invite link invalid for {chat_id}")
        return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Invite join failed in {chat_id}: {e}")
        return False

# ──────────────────────────────────────────────────────────────────────────────
#  CORE: ensure assistant is present
# ──────────────────────────────────────────────────────────────────────────────
async def ensure_assistant_in_chat(chat_id: int, userbot=None, bot_client=None) -> bool:
    if bot_client is None:
        from SHASHA_DRUGZ import app
        bot_client = app

    if userbot is None:
        try:
            userbot = await get_assistant(chat_id)
        except Exception as e:
            logger.warning(f"[assistant_guard] Could not get assistant for {chat_id}: {e}")
            return False

    # FIX: 'Client' object has no attribute 'id'. Fallback safely to get_me()
    if userbot.me is not None:
        assistant_id = userbot.me.id
    else:
        me = await userbot.get_me()
        assistant_id = me.id

    status = await _get_assistant_status(bot_client, chat_id, assistant_id)
    if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return True

    if status == ChatMemberStatus.BANNED:
        if not await _bot_can_ban(bot_client, chat_id):
            return False
        unbanned = await _try_unban(bot_client, chat_id, assistant_id)
        if not unbanned:
            return False
        await asyncio.sleep(2)

    if await _try_join_via_username(bot_client, userbot, chat_id):
        return True

    if await _bot_can_invite(bot_client, chat_id):
        if await _try_join_via_invite(bot_client, userbot, chat_id):
            return True

    return False

# ──────────────────────────────────────────────────────────────────────────────
#  PLAY COMMAND INTERCEPTOR
# ──────────────────────────────────────────────────────────────────────────────
PLAY_COMMANDS = [
    "play", "vplay", "cplay", "cvplay",
    "playforce", "vplayforce", "cplayforce", "cvplayforce",
]

@Client.on_message(
    filters.command(PLAY_COMMANDS, prefixes=["/", "!", "%", ".", "@", "#", ""])
    & filters.group,
    group=-10,
)
async def _play_assistant_guard(client: Client, message: Message):
    chat_id = message.chat.id
    userbot = None
    try:
        from SHASHA_DRUGZ.dplugins.COMMON.PREMIUM.setbotinfo import get_custom_assistant_userbot
        bot_id = client.me.id if client.me else None
        if bot_id is not None:
            userbot = get_custom_assistant_userbot(bot_id)
    except Exception:
        pass

    asyncio.create_task(ensure_assistant_in_chat(chat_id, userbot=userbot, bot_client=client))

MOD_TYPE = "MUSIC"
MOD_NAME = "Assist-Guard"
MOD_PRICE = "0"
