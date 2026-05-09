from SHASHA_DRUGZ import app, userbot
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter
from pyrogram import Client, filters, enums
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import (
    RPCError,
    ChannelInvalid,
    PeerIdInvalid,
    ChatWriteForbidden,
    FloodWait,
    FileReferenceExpired,
    FileReferenceInvalid,
    ChatAdminRequired,
    InviteRequestSent,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from pyrogram.types import (
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatJoinRequest,
    Message,
)
from pyrogram import *
from pyrogram.types import *
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops
from logging import getLogger
from pathlib import Path
from typing import Union, Optional
import asyncio
import os
import time
import aiohttp
import requests
import random
import logging

# ─────────────────────────────────────────────
# Suppress pyrogram PEER_ID_INVALID noise
# ─────────────────────────────────────────────
class _PeerIdInvalidFilter(logging.Filter):
    def filter(self, record):
        return "PEER_ID_INVALID" not in record.getMessage()

logging.getLogger("pyrogram.client").addFilter(_PeerIdInvalidFilter())

# ─────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────
LOGGER = getLogger(__name__)

# ─────────────────────────────────────────────
# Fallback photos
# ─────────────────────────────────────────────
random_photo = [
    "https://telegra.ph/file/1949480f01355b4e87d26.jpg",
    "https://telegra.ph/file/3ef2cc0ad2bc548bafb30.jpg",
    "https://telegra.ph/file/a7d663cd2de689b811729.jpg",
    "https://telegra.ph/file/6f19dc23847f5b005e922.jpg",
    "https://telegra.ph/file/2973150dd62fd27a3a6ba.jpg",
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
# Temp state
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
def circle(pfp, size=(500, 500)):
    pfp = pfp.resize(size, Image.LANCZOS).convert("RGBA")
    bigsize = (pfp.size[0] * 3, pfp.size[1] * 3)
    mask = Image.new("L", bigsize, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + bigsize, fill=255)
    mask = mask.resize(pfp.size, Image.LANCZOS)
    mask = ImageChops.darker(mask, pfp.split()[-1])
    pfp.putalpha(mask)
    return pfp

def welcomepic(pic, user, chatname, id, uname, brightness_factor=1.3):
    background = Image.open("SHASHA_DRUGZ/assets/shasha/hb-welcome.jpg")
    pfp = Image.open(pic).convert("RGBA")
    pfp = circle(pfp)
    pfp = pfp.resize((830, 840))
    draw = ImageDraw.Draw(background)
    font_large = ImageFont.truetype("SHASHA_DRUGZ/assets/shasha/ArialReg.TTF", size=140)
    draw.text((2000, 1080), f"{user}", fill=(201, 2, 2), font=font_large)
    draw.text((2000, 1280), f"{id}", fill=(201, 2, 2), font=font_large)
    draw.text((2000, 1510), f"{uname}", fill=(201, 2, 2), font=font_large)
    pfp_position = (280, 390)
    background.paste(pfp, pfp_position, pfp)
    background.save(f"downloads/welcome#{id}.png")
    return f"downloads/welcome#{id}.png"

def _is_valid_image(path: str) -> bool:
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

async def _safe_download_profile_photo(user) -> str:
    fallback = "SHASHA_DRUGZ/assets/upic.png"
    pic = None
    try:
        if not user.photo:
            return fallback
        pic = await app.download_media(
            user.photo.big_file_id,
            file_name=f"pp{user.id}.png",
        )
    except (FileReferenceExpired, FileReferenceInvalid):
        try:
            photos = await app.get_profile_photos(user.id, limit=1)
            if photos:
                pic = await app.download_media(
                    photos[0].file_id,
                    file_name=f"pp{user.id}.png",
                )
        except Exception:
            return fallback
    except AttributeError:
        return fallback
    except (RPCError, Exception):
        return fallback

    if not _is_valid_image(pic):
        if pic and os.path.exists(pic):
            try:
                os.remove(pic)
            except OSError:
                pass
        return fallback
    return pic

# ─────────────────────────────────────────────
# /welcome command
# ─────────────────────────────────────────────
@Client.on_message(filters.command("welcome") & ~filters.private)
async def auto_state(client: Client, message: Message):
    usage = "**ᴜsᴀɢᴇ:**\n**⦿ /welcome [on|off]**"
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
                await message.reply_text("**ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ᴀʟʀᴇᴀᴅʏ ᴅɪsᴀʙʟᴇᴅ !**")
            else:
                await wlcm.add_wlcm(chat_id)
                await message.reply_text(
                    f"**ᴅɪsᴀʙʟᴇᴅ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ɪɴ** {message.chat.title}"
                )
        elif state == "on":
            if not A:
                await message.reply_text("**ᴇɴᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ.**")
            else:
                await wlcm.rm_wlcm(chat_id)
                await message.reply_text(
                    f"**ᴇɴᴀʙʟᴇᴅ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ɪɴ ** {message.chat.title}"
                )
        else:
            await message.reply_text(usage)
    else:
        await message.reply(
            "**sᴏʀʀʏ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴇɴᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ!**"
        )

# ─────────────────────────────────────────────
# New-member welcome handler
# ─────────────────────────────────────────────
@Client.on_chat_member_updated(filters.group, group=-3)
async def greet_new_member(_, member: ChatMemberUpdated):
    chat_id = member.chat.id

    # ── Check if welcome is disabled ─────────────────────────────────────────
    A = await wlcm.find_one(chat_id)
    if A:
        return

    # ── Only fire when a brand-new member joins (not promotions/demotions) ───
    if not (member.new_chat_member and not member.old_chat_member):
        return

    user = (
        member.new_chat_member.user if member.new_chat_member else member.from_user
    )

    # ── Get member count — silently skip if peer not cached ──────────────────
    count = "N/A"
    try:
        count = await app.get_chat_members_count(chat_id)
    except (ChannelInvalid, PeerIdInvalid):
        pass  # peer not yet cached — count stays "N/A"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            count = await app.get_chat_members_count(chat_id)
        except RPCError:
            pass
    except RPCError as e:
        LOGGER.warning("greet_new_member: get_chat_members_count RPCError: %s", e)

    # ── Delete previous welcome message if any ───────────────────────────────
    prev_key = f"welcome-{chat_id}"
    if temp.MELCOW.get(prev_key) is not None:
        try:
            await temp.MELCOW[prev_key].delete()
        except Exception as e:
            LOGGER.error("greet_new_member: could not delete old welcome: %s", e)

    # ── Download profile photo (safe — never raises) ─────────────────────────
    pic = await _safe_download_profile_photo(user)

    # ── Build welcome image ──────────────────────────────────────────────────
    try:
        welcomeimg = welcomepic(
            pic,
            user.first_name,
            member.chat.title,
            user.id,
            user.username or "N/A",
        )
    except Exception as e:
        LOGGER.error("greet_new_member: welcomepic failed: %s", e)
        welcomeimg = None

    # ── Build buttons ────────────────────────────────────────────────────────
    button_text = "⌯ ɴᴇᴡ ϻᴇᴍʙᴇʀ ⌯"
    add_button_text = "⌯ ᴋɪᴅɴᴧᴘ ϻᴇ ⌯"
    deep_link = f"tg://openmessage?user_id={user.id}"
    add_link = f"https://t.me/{app.username}?startgroup=true"
    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(button_text, url=deep_link)],
            [InlineKeyboardButton(text=add_button_text, url=add_link)],
        ]
    )

    caption = f"""
<blockquote>**☆ . * ●¸ . ✦ .★°:. ★ * • ○ ° ★**
 
**{member.chat.title}**
**⊰●⊱┈─★ 𝑾𝑒𝑙𝑐𝑜𝑚𝑒 ★─┈⊰●⊱**</blockquote>\n
<blockquote>**➽────────────────❥**   
**🔻 𝐍ᴀᴍᴇ**    ➥ {user.mention}
**🔻 𝐈ᴅ**       ➥ {user.id}
**🔻 𝐔sᴇʀɴᴀᴍᴇ** ➥ @{user.username or "N/A"}
**🔻 𝐌ᴇᴍʙᴇʀ**   ➥ {count}
**➽────────────────❥**</blockquote>\n  
<blockquote>**☆ . * ●¸ . ✦ .★°:. ★ * • ○ ° ★**</blockquote>
"""

    # ── Send welcome photo or fall back to text-only ─────────────────────────
    try:
        if welcomeimg and os.path.exists(welcomeimg):
            temp.MELCOW[prev_key] = await app.send_photo(
                chat_id,
                photo=welcomeimg,
                caption=caption,
                reply_markup=reply_markup,
            )
        else:
            temp.MELCOW[prev_key] = await app.send_message(
                chat_id,
                text=caption,
                reply_markup=reply_markup,
            )
    except (ChannelInvalid, PeerIdInvalid):
        pass  # peer not yet cached — silently skip
    except ChatWriteForbidden:
        pass  # bot lacks send permission — silently skip
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            if welcomeimg and os.path.exists(welcomeimg):
                temp.MELCOW[prev_key] = await app.send_photo(
                    chat_id,
                    photo=welcomeimg,
                    caption=caption,
                    reply_markup=reply_markup,
                )
            else:
                temp.MELCOW[prev_key] = await app.send_message(
                    chat_id,
                    text=caption,
                    reply_markup=reply_markup,
                )
        except RPCError:
            pass
    except RPCError as e:
        LOGGER.error("greet_new_member: send RPCError: %s", e)
    except Exception as e:
        LOGGER.error("greet_new_member: unexpected send error: %s", e)
    finally:
        # Clean up the downloaded profile photo if it's not the fallback asset
        if (
            pic
            and pic != "SHASHA_DRUGZ/assets/upic.png"
            and os.path.exists(pic)
        ):
            try:
                os.remove(pic)
            except OSError:
                pass

# ─────────────────────────────────────────────
# Module metadata
# ─────────────────────────────────────────────
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_1"
__help__ = """
🔻 /welcome on  ➠  ᴇɴᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /welcome off  ➠  ᴅɪsᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "WELCOME"
MOD_PRICE = "60"
