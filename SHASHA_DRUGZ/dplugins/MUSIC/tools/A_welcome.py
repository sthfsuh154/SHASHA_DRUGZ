from SHASHA_DRUGZ import app
from pyrogram import Client, filters, enums
from pyrogram.errors import (
    RPCError,
    ChannelInvalid,
    PeerIdInvalid,
    ChatWriteForbidden,
    UserIsBlocked,
    FloodWait,
    FileReferenceExpired,
    FileReferenceInvalid,
)
from pyrogram.types import (
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatJoinRequest,
    Message,
)
from pyrogram.enums import ParseMode
from pyrogram import *
from pyrogram.types import *
from logging import getLogger
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops
from pathlib import Path
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.extraction import extract_user
from time import time
import random
import asyncio
import os
import aiohttp

# ─────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────
LOGGER = getLogger(__name__)

# ─────────────────────────────────────────────
# Anti-spam state
# ─────────────────────────────────────────────
user_last_message_time = {}
user_command_count = {}
SPAM_THRESHOLD = 2
SPAM_WINDOW_SECONDS = 5

# ─────────────────────────────────────────────
# Random fallback photos
# ─────────────────────────────────────────────
random_photo = [
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
]

# ─────────────────────────────────────────────
# In-memory welcome DB
# ─────────────────────────────────────────────
class WelDatabase:
    def __init__(self):
        self.data = {}

    async def find_one(self, chat_id):
        return chat_id in self.data

    async def add_wlcm(self, chat_id):
        if chat_id not in self.data:
            self.data[chat_id] = {"state": "on"}

    async def rm_wlcm(self, chat_id):
        if chat_id in self.data:
            del self.data[chat_id]


wlcm = WelDatabase()


# ─────────────────────────────────────────────
# Temp state holder
# ─────────────────────────────────────────────
class temp:
    ME = None
    CURRENT = 2
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None


# ─────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────
def circle(pfp, size=(500, 500), brightness_factor=1.0):
    pfp = pfp.resize(size, Image.ANTIALIAS).convert("RGBA")
    pfp = ImageEnhance.Brightness(pfp).enhance(brightness_factor)
    bigsize = (pfp.size[0] * 3, pfp.size[1] * 3)
    mask = Image.new("L", bigsize, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + bigsize, fill=200)
    mask = mask.resize(pfp.size, Image.ANTIALIAS)
    mask = ImageChops.darker(mask, pfp.split()[-1])
    pfp.putalpha(mask)
    return pfp


def welcomepic(pic, user, chatname, id, uname, brightness_factor=1.3):
    background = Image.open("SHASHA_DRUGZ/assets/wel2.png")
    pfp = Image.open(pic).convert("RGBA")
    pfp = circle(pfp, brightness_factor=brightness_factor)
    pfp = pfp.resize((825, 824))
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype("SHASHA_DRUGZ/assets/font.ttf", size=110)
    welcome_font = ImageFont.truetype("SHASHA_DRUGZ/assets/font.ttf", size=60)
    draw.text((2100, 1420), f"ID: {id}", fill=(221, 20, 20), font=font)
    pfp_position = (1990, 435)
    background.paste(pfp, pfp_position, pfp)
    background.save(f"downloads/welcome#{id}.png")
    return f"downloads/welcome#{id}.png"


def _is_valid_image(path: str) -> bool:
    """Return True only if the file exists, is non-empty, and PIL can open it."""
    if not path or not os.path.exists(path):
        return False
    if os.path.getsize(path) == 0:
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


async def _safe_download_profile_photo(client, user_id: int) -> str | None:
    """
    Download the profile photo for *user_id* and return the local path,
    or None if the photo is unavailable / expired / corrupted.
    """
    path = None
    try:
        path = await client.download_media(
            await client.get_profile_photos(user_id, limit=1).__anext__(),
        )
    except (FileReferenceExpired, FileReferenceInvalid):
        # File reference stale — attempt a fresh fetch and re-download
        try:
            photos = await client.get_profile_photos(user_id, limit=1)
            if photos:
                path = await client.download_media(photos[0])
        except Exception as e:
            LOGGER.warning("_safe_download_profile_photo: retry failed for %s: %s", user_id, e)
            return None
    except StopAsyncIteration:
        # User has no profile photo
        return None
    except (PeerIdInvalid, ChannelInvalid):
        return None
    except RPCError as e:
        LOGGER.warning("_safe_download_profile_photo: RPCError for %s: %s", user_id, e)
        return None
    except Exception as e:
        LOGGER.warning("_safe_download_profile_photo: unexpected error for %s: %s", user_id, e)
        return None

    if not _is_valid_image(path):
        # Downloaded file is empty or unreadable — clean up and bail
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return None

    return path


# ─────────────────────────────────────────────
# /awelcome command
# ─────────────────────────────────────────────
@Client.on_message(filters.command("awelcome") & ~filters.private)
async def auto_state(client, message: Message):
    user_id = message.from_user.id
    current_time = time()

    last_message_time = user_last_message_time.get(user_id, 0)
    if current_time - last_message_time < SPAM_WINDOW_SECONDS:
        user_last_message_time[user_id] = current_time
        user_command_count[user_id] = user_command_count.get(user_id, 0) + 1
        if user_command_count[user_id] > SPAM_THRESHOLD:
            hu = await message.reply_text(
                f"**{message.from_user.mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ ᴅᴏ sᴘᴀᴍ, "
                f"ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**"
            )
            await asyncio.sleep(3)
            await hu.delete()
            return
    else:
        user_command_count[user_id] = 1
        user_last_message_time[user_id] = current_time

    usage = "**ᴜsᴀɢᴇ:**\n**⦿ /awelcome [on|off]**"
    if len(message.command) == 1:
        return await message.reply_text(usage)

    chat_id = message.chat.id

    try:
        user = await app.get_chat_member(chat_id, message.from_user.id)
    except RPCError:
        return await message.reply_text("**ᴄᴏᴜʟᴅ ɴᴏᴛ ᴠᴇʀɪғʏ ᴀᴅᴍɪɴ sᴛᴀᴛᴜs.**")

    if user.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    ):
        A = await wlcm.find_one(chat_id)
        state = message.text.split(None, 1)[1].strip().lower()

        if state == "off":
            if A:
                await message.reply_text(
                    "**ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ᴀʟʀᴇᴀᴅʏ ᴅɪsᴀʙʟᴇᴅ !**"
                )
            else:
                await wlcm.add_wlcm(chat_id)
                await message.reply_text(
                    f"**ᴅɪsᴀʙʟᴇᴅ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ɪɴ** "
                    f"{message.chat.title} ʙʏ ᴀssɪsᴛᴀɴᴛ"
                )
        elif state == "on":
            if not A:
                await message.reply_text(
                    "**ᴇɴᴀʙʟᴇᴅ ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ.**"
                )
            else:
                await wlcm.rm_wlcm(chat_id)
                await message.reply_text(
                    f"**ᴇɴᴀʙʟᴇᴅ ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ɪɴ ** "
                    f"{message.chat.title}"
                )
        else:
            await message.reply_text(usage)
    else:
        await message.reply(
            "**sᴏʀʀʏ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴇɴᴀʙʟᴇ ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ!**"
        )


# ─────────────────────────────────────────────
# New-member welcome handler
# ─────────────────────────────────────────────
@Client.on_chat_member_updated(filters.group, group=-2)
async def greet_new_members(_, member: ChatMemberUpdated):
    try:
        chat_id = member.chat.id

        # ── Check if welcome is disabled for this chat ──────────────────────
        A = await wlcm.find_one(chat_id)
        if A:
            return

        # ── Only fire when a brand-new member joins ──────────────────────────
        if not (member.new_chat_member and not member.old_chat_member):
            return

        user = (
            member.new_chat_member.user
            if member.new_chat_member
            else member.from_user
        )

        # ── Get the assistant client for this chat ───────────────────────────
        try:
            userbot = await get_assistant(chat_id)
        except Exception as e:
            LOGGER.warning("greet_new_members: get_assistant failed for %s: %s", chat_id, e)
            return

        # ── Get member count safely (ChannelInvalid guard) ───────────────────
        count = None
        try:
            count = await app.get_chat_members_count(chat_id)
        except (ChannelInvalid, PeerIdInvalid):
            LOGGER.warning(
                "greet_new_members: peer not cached for get_chat_members_count "
                "in chat %s — skipping count",
                chat_id,
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                count = await app.get_chat_members_count(chat_id)
            except RPCError:
                pass
        except RPCError as e:
            LOGGER.warning("greet_new_members: RPCError on get_chat_members_count: %s", e)

        # ── Build and send welcome message ───────────────────────────────────
        uname = f"@{user.username}" if user.username else user.mention
        welcome_text = f"**Wᴇʟᴄᴏᴍᴇ** {user.mention}\n**{uname}**"
        if count is not None:
            welcome_text += f"\n**Members: {count}**"

        await asyncio.sleep(3)

        try:
            await userbot.send_message(chat_id, text=welcome_text)
        except (ChannelInvalid, PeerIdInvalid):
            LOGGER.warning(
                "greet_new_members: userbot peer not cached for chat %s", chat_id
            )
        except ChatWriteForbidden:
            LOGGER.warning(
                "greet_new_members: bot lacks send permission in chat %s", chat_id
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await userbot.send_message(chat_id, text=welcome_text)
            except RPCError:
                pass
        except RPCError as e:
            LOGGER.error("greet_new_members: send_message RPCError: %s", e)

    except Exception as e:
        LOGGER.error("greet_new_members: unexpected error: %s", e)


# ─────────────────────────────────────────────
# Module metadata
# ─────────────────────────────────────────────
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_1"
__help__ = """
🤖 ASSISTANT WELCOME
🔻 /awelcome on ➠ ᴇɴᴀʙʟᴇs ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇs ғᴏʀ ɴᴇᴡ ᴍᴇᴍʙᴇʀs
🔻 /awelcome off ➠ ᴅɪsᴀʙʟᴇs ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
🔻 /awelcome ➠ sʜᴏᴡs ᴜsᴀɢᴇ ɪɴғᴏ ғᴏʀ ᴀssɪsᴛᴀɴᴛ ᴡᴇʟᴄᴏᴍᴇ sᴇᴛᴛɪɴɢs
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "AssiWelcome"
MOD_PRICE = "30"
