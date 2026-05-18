import os
import re
import time
import imghdr
import subprocess
from traceback import format_exc
from uuid import uuid4

import pyrogram
from pyrogram import Client, filters
from pyrogram.raw import functions as raw_functions
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import (
    PeerIdInvalid,
    ShortnameOccupyFailed,
    StickerEmojiInvalid,
    StickersetInvalid,
    UserIsBlocked,
)

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import get_assistant   # ← userbot client
from config import BOT_USERNAME
from SHASHA_DRUGZ.utils.errors import capture_err
from SHASHA_DRUGZ.utils.files import (
    get_document_from_file_id,
    resize_file_to_sticker_size,
    upload_document,
)
from SHASHA_DRUGZ.utils.stickerset import (
    add_sticker_to_set,
    create_sticker,
    create_sticker_set,
    get_sticker_set_by_name,
)

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
MAX_STICKERS = 120
STATIC_TYPES  = ["jpeg", "png", "webp"]

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _clean_username(username: str) -> str:
    u = username.lstrip("@").lower()
    u = re.sub(r"[^a-z0-9_]", "", u)
    u = re.sub(r"_{2,}", "_", u)
    return u

def _make_packname(bot_username: str, user_id: int, num: int = 0) -> str:
    bot    = _clean_username(bot_username)
    prefix = f"f{num}_" if num else "f"
    name   = f"{prefix}{user_id}_by_{bot}"
    return re.sub(r"_{2,}", "_", name)

# ------------------------------------------------------------------------------
# Video/GIF → .webm sticker conversion
# ------------------------------------------------------------------------------
async def make_video_sticker(
    client, file_path: str, emoji: str, msg: Message, chat_id: int
):
    """Convert a video / GIF to a Telegram video sticker (.webm)."""
    out = f"sticker_{uuid4().hex}.webm"
    try:
        duration = float(
            subprocess.check_output([
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ]).decode().strip()
        )
    except Exception:
        duration = 3.0

    process = subprocess.Popen(
        [
            "ffmpeg", "-i", file_path,
            "-vf", "scale=512:512:force_original_aspect_ratio=decrease,fps=30",
            "-c:v", "libvpx-vp9", "-b:v", "256K",
            "-an", "-t", "3", "-y", out,
        ],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    last_update = time.time()
    while True:
        line = process.stderr.readline()
        if not line:
            break
        m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
        if m:
            current = (
                int(m.group(1)) * 3600
                + int(m.group(2)) * 60
                + float(m.group(3))
            )
            percent = min(current / duration * 100, 100)
            if time.time() - last_update > 1:
                bar = "█" * int(percent // 10) + "░" * (10 - int(percent // 10))
                try:
                    await msg.edit(f"🎬 **Converting...**\n[{bar}] {percent:.1f}%")
                except Exception:
                    pass
                last_update = time.time()
    process.wait()

    await msg.edit("📤 Uploading sticker...")
    sticker = await create_sticker(
        await upload_document(client, out, chat_id),
        emoji,
    )
    os.remove(out)
    return sticker

# ------------------------------------------------------------------------------
# Command: /st <sticker_id> – send a sticker by its file_id
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("st"))
async def generate_sticker(client, message: Message):
    if len(message.command) == 2:
        try:
            await client.send_sticker(message.chat.id, sticker=message.command[1])
        except Exception as e:
            await message.reply_text(f"Error: {e}")
    else:
        await message.reply_text("Please provide a sticker ID after /st command.")

# ------------------------------------------------------------------------------
# Command: /packkang – copy an entire sticker pack
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("packkang"))
async def _packkang(client, message: Message):
    txt = await message.reply_text("**ᴘʀᴏᴄᴇssɪɴɢ....**")
    if not message.reply_to_message:
        return await txt.edit("ʀᴇᴘʟʏ ᴛᴏ ᴍᴇssᴀɢᴇ")
    if not message.reply_to_message.sticker:
        return await txt.edit("ʀᴇᴘʟʏ ᴛᴏ sᴛɪᴄᴋᴇʀ")
    if (
        message.reply_to_message.sticker.is_animated
        or message.reply_to_message.sticker.is_video
    ):
        return await txt.edit("ʀᴇᴘʟʏ ᴛᴏ ᴀ ɴᴏɴ-ᴀɴɪᴍᴀᴛᴇᴅ sᴛɪᴄᴋᴇʀ")

    pack_title = (
        message.text.split(maxsplit=1)[1]
        if len(message.command) >= 2
        else f"{message.from_user.first_name}'s Pack"
    )

    try:
        stickers = await app.invoke(
            pyrogram.raw.functions.messages.GetStickerSet(
                stickerset=pyrogram.raw.types.InputStickerSetShortName(
                    short_name=message.reply_to_message.sticker.set_name
                ),
                hash=0,
            )
        )
    except StickersetInvalid:
        return await txt.edit("The sticker set is invalid or no longer exists.")

    sticks = [
        pyrogram.raw.types.InputStickerSetItem(
            document=pyrogram.raw.types.InputDocument(
                id=doc.id,
                access_hash=doc.access_hash,
                file_reference=doc.file_reference,
            ),
            emoji=doc.attributes[1].alt,
        )
        for doc in stickers.documents
    ]
    new_short_name = f"pack{uuid4().hex}_by_{_clean_username(app.me.username)}"
    try:
        await app.invoke(
            pyrogram.raw.functions.stickers.CreateStickerSet(
                user_id=await app.resolve_peer(message.from_user.id),
                title=pack_title,
                short_name=new_short_name,
                stickers=sticks,
            )
        )
        await txt.edit(
            f"**ʜᴇʀᴇ ɪs ʏᴏᴜʀ ᴋᴀɴɢᴇᴅ ʟɪɴᴋ**!\n**ᴛᴏᴛᴀʟ sᴛɪᴄᴋᴇʀ**: {len(sticks)}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(
                    "ᴘᴀᴄᴋ ʟɪɴᴋ",
                    url=f"https://t.me/addstickers/{new_short_name}",
                )]]
            ),
        )
    except Exception as e:
        await txt.edit(f"Failed: {e}")

# ------------------------------------------------------------------------------
# Command: /stickerid  /stid – get sticker file_id
# ------------------------------------------------------------------------------
@Client.on_message(filters.command(["stickerid", "stid"]))
async def sticker_id(client, msg: Message):
    if not msg.reply_to_message or not msg.reply_to_message.sticker:
        return await msg.reply_text("Reply to a sticker")
    st = msg.reply_to_message.sticker
    await msg.reply_text(
        f"⊹ <u>**sᴛɪᴄᴋᴇʀ ɪɴғᴏ**</u> ⊹\n"
        f"**⊚ sᴛɪᴄᴋᴇʀ ɪᴅ**: `{st.file_id}`\n\n"
        f"**⊚ sᴛɪᴄᴋᴇʀ ᴜɴɪǫᴜᴇ ɪᴅ**: `{st.file_unique_id}`"
    )

# ------------------------------------------------------------------------------
# Command: /kang – add sticker / image / gif / video to your personal pack
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("kang"))
@capture_err
async def kang(client, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a sticker, image, gif, or video.")
    if not message.from_user:
        return await message.reply_text("Use this command in a chat, not a channel.")

    msg   = await message.reply_text("Kanging...")
    r     = message.reply_to_message
    emoji = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "🤔"
    cid   = message.chat.id

    try:
        # ── Build the sticker object ───────────────────────────────────────────
        if r.sticker:
            s          = r.sticker
            used_emoji = s.emoji or emoji
            if s.is_animated:
                await msg.edit("⚙️ Processing animated sticker...")
                sticker = await create_sticker(
                    await get_document_from_file_id(s.file_id),
                    used_emoji,
                )
            elif s.is_video:
                await msg.edit("⚙️ Processing video sticker...")
                sticker = await create_sticker(
                    await get_document_from_file_id(s.file_id),
                    used_emoji,
                )
            else:
                sticker = await create_sticker(
                    await get_document_from_file_id(s.file_id),
                    used_emoji,
                )
        elif r.video or r.animation:
            await msg.edit("⬇️ Downloading video...")
            file    = await app.download_media(r)
            sticker = await make_video_sticker(client, file, emoji, msg, cid)
            os.remove(file)
        elif r.photo or r.document:
            await msg.edit("⬇️ Downloading media...")
            file  = await app.download_media(r)
            ftype = imghdr.what(file)
            if ftype in STATIC_TYPES:
                file    = await resize_file_to_sticker_size(file)
                sticker = await create_sticker(
                    await upload_document(client, file, cid),
                    emoji,
                )
                os.remove(file)
            else:
                sticker = await make_video_sticker(client, file, emoji, msg, cid)
                os.remove(file)
        else:
            return await msg.edit("Unsupported media type.")

        # ── Pack creation / overflow loop ─────────────────────────────────────
        bot_username = app.me.username
        user_id      = message.from_user.id
        packnum      = 0
        limit        = 0
        packname     = _make_packname(bot_username, user_id)

        while True:
            if limit > 50:
                return await msg.delete()
            try:
                stickerset = await get_sticker_set_by_name(client, packname)
            except StickersetInvalid:
                stickerset = None

            if stickerset is None:
                await create_sticker_set(
                    client,
                    user_id,
                    f"{message.from_user.first_name[:32]}'s kang pack",
                    packname,
                    [sticker],
                )
                break
            elif stickerset.set.count >= MAX_STICKERS:
                packnum += 1
                packname = _make_packname(bot_username, user_id, packnum)
                limit   += 1
                continue
            else:
                await add_sticker_to_set(client, stickerset, sticker)
                break

        await msg.edit(
            f"Sticker Kanged! ✅\n[Add Pack](https://t.me/addstickers/{packname})"
        )

    except (PeerIdInvalid, UserIsBlocked):
        await msg.edit(
            "Please start me in PM first.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(
                    "Start",
                    url=f"https://t.me/{BOT_USERNAME.lstrip('@')}",
                )]]
            ),
        )
    except StickerEmojiInvalid:
        await msg.edit("Invalid emoji. Try a standard emoji like 🤔")
    except ShortnameOccupyFailed:
        await msg.edit("Short name already taken. Try changing your Telegram username.")
    except Exception:
        print(format_exc())
        await msg.edit("Failed to kang sticker. Check logs for details.")

# ------------------------------------------------------------------------------
# Command: /geteffects         — list ALL available Telegram message effect IDs
# Command: /geteffects <emoji> — look up a SPECIFIC emoji effect ID
#
# WHY USERBOT: Telegram blocks bots from calling messages.GetAvailableEffects
# with BOT_METHOD_INVALID. The assistant userbot (user account) can call it.
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("geteffects") & SUDOERS)
async def get_effects(client, message: Message):
    wait = await message.reply_text("⏳ Fetching effects...")

    # ── Get the userbot client ────────────────────────────────────────────────
    try:
        userbot = await get_assistant(message.chat.id)
    except Exception as e:
        return await wait.edit(
            f"❌ Could not get assistant userbot: `{e}`\n"
            f"Make sure the assistant is in this group."
        )

    # ── Fetch effects from Telegram via userbot ───────────────────────────────
    try:
        result = await userbot.invoke(
            raw_functions.messages.GetAvailableEffects(hash=0)
        )
    except Exception as e:
        return await wait.edit(f"❌ Failed to fetch effects: `{e}`")

    if not result.effects:
        return await wait.edit("No message effects found.")

    # Build a clean emoji → id mapping
    effects_map = {}
    for effect in result.effects:
        emoticon = getattr(effect, "emoticon", None) or "?"
        effects_map[emoticon] = effect.id

    # ── /geteffects <emoji>  — search for a specific emoji ───────────────────
    if len(message.command) >= 2:
        query = message.text.split(maxsplit=1)[1].strip()
        if query in effects_map:
            eid = effects_map[query]
            return await wait.edit(
                f"✨ **Effect ID for** {query}\n\n"
                f"`{eid}`"
            )
        else:
            # Try partial / case-insensitive match on emoticon string
            matches = [
                (emo, eid)
                for emo, eid in effects_map.items()
                if query.lower() in emo.lower()
            ]
            if matches:
                lines = "\n".join(f"{emo} → `{eid}`" for emo, eid in matches)
                return await wait.edit(
                    f"✨ **Partial matches for** `{query}`:\n\n{lines}"
                )
            else:
                return await wait.edit(
                    f"❌ No effect found for `{query}`.\n\n"
                    f"Use `/geteffects` (no argument) to see all available effects."
                )

    # ── /geteffects — list ALL effects ───────────────────────────────────────
    lines = [f"{emo} → `{eid}`" for emo, eid in effects_map.items()]
    header = f"✨ **Available Message Effects** ({len(lines)} total):\n\n"
    full   = header + "\n".join(lines)

    # Telegram 4096-char limit guard — split into chunks if needed
    if len(full) <= 4000:
        await wait.edit(full)
    else:
        chunks = []
        current = header
        for line in lines:
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            chunks.append(current)

        await wait.edit(chunks[0])
        for chunk in chunks[1:]:
            await message.reply_text(chunk)

# ------------------------------------------------------------------------------
# Module metadata
# ------------------------------------------------------------------------------
__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_54"
__help__     = """
🔻 /st <sticker_id> ➠ sᴇɴᴅ sᴛɪᴄᴋᴇʀ ʙʏ ɪᴅ
🔻 /kang ➠ ᴀᴅᴅ sᴛɪᴄᴋᴇʀ/ɪᴍᴀɢᴇ/ɢɪꜰ/ᴠɪᴅᴇᴏ ᴛᴏ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ ᴘᴀᴄᴋ
🔻 /packkang ➠ ᴋᴀɴɢ ᴀɴ ᴇɴᴛɪʀᴇ sᴛɪᴄᴋᴇʀ ᴘᴀᴄᴋ
🔻 /stickerid, /stid ➠ ɢᴇᴛ sᴛɪᴄᴋᴇʀ ɪᴅ & ᴜɴɪǫᴜᴇ ɪᴅ
🔻 /geteffects ➠ [sᴜᴅᴏ] ʟɪsᴛ ᴀʟʟ ᴀᴠᴀɪʟᴀʙʟᴇ ᴍᴇssᴀɢᴇ ᴇꜰꜰᴇᴄᴛ ɪᴅs ᴠɪᴀ ᴀssɪsᴛᴀɴᴛ
🔻 /geteffects <emoji> ➠ [sᴜᴅᴏ] ɢᴇᴛ ᴇꜰꜰᴇᴄᴛ ɪᴅ ꜰᴏʀ ᴀ sᴘᴇᴄɪꜰɪᴄ ᴇᴍᴏᴊɪ
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "KangSticker"
MOD_PRICE = "60"
