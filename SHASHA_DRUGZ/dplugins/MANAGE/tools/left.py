from SHASHA_DRUGZ import app
from pyrogram import Client, filters, enums
from pyrogram.errors import RPCError
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest
from pyrogram.enums import ParseMode
from pyrogram import *
from pyrogram.types import *
from os import environ
from typing import Union, Optional
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from asyncio import sleep
from logging import getLogger
import random
import asyncio
import os
import time
import aiohttp

from SHASHA_DRUGZ.utils.shasha_ban import admin_filter

logger = getLogger(__name__)

random_photo = [
    "https://files.catbox.moe/qz10e1.jpg",
    "https://files.catbox.moe/qz10e1.jpg",
    "https://files.catbox.moe/qz10e1.jpg",
]

bg_path = "SHASHA_DRUGZ/assets/userinfo.png"
font_path = "SHASHA_DRUGZ/assets/hiroko.ttf"
get_font = lambda font_size, font_path: ImageFont.truetype(font_path, font_size)


async def get_userinfo_img(
    bg_path: str,
    font_path: str,
    user_id: Union[int, str],
    profile_path: Optional[str] = None
):
    bg = Image.open(bg_path).convert("RGBA")

    if profile_path and os.path.exists(profile_path):
        try:
            img = Image.open(profile_path).convert("RGBA")
            mask = Image.new("L", img.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.pieslice([(0, 0), img.size], 0, 360, fill=255)
            circular_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
            circular_img.paste(img, (0, 0), mask)
            resized = circular_img.resize((400, 400))
            bg.paste(resized, (440, 160), resized)
        except Exception:
            pass  # silently skip if profile photo can't be processed

    img_draw = ImageDraw.Draw(bg)
    img_draw.text(
        (529, 627),
        text=str(user_id).upper(),
        font=get_font(46, font_path),
        fill=(255, 255, 255),
    )

    path = f"./userinfo_img_{user_id}.png"
    bg.save(path)
    return path


@Client.on_chat_member_updated(filters.group, group=-22)
async def member_has_left(client: Client, member: ChatMemberUpdated):
    if (
        not member.new_chat_member
        and member.old_chat_member
        and member.old_chat_member.status not in {"banned", "left", "restricted"}
    ):
        user = (
            member.old_chat_member.user
            if member.old_chat_member
            else member.from_user
        )

        welcome_photo = None
        photo_path = None

        if user.photo:
            try:
                photo_path = await app.download_media(user.photo.big_file_id)

                # Validate the file is a real image before using it
                with Image.open(photo_path) as test_img:
                    test_img.verify()

                welcome_photo = await get_userinfo_img(
                    bg_path=bg_path,
                    font_path=font_path,
                    user_id=user.id,
                    profile_path=photo_path,
                )
            except Exception:
                pass  # silently fall through to random photo
            finally:
                # Always clean up the downloaded temp file
                if photo_path and os.path.exists(photo_path):
                    try:
                        os.remove(photo_path)
                    except Exception:
                        pass

        if not welcome_photo:
            welcome_photo = random.choice(random_photo)

        caption = (
            "**❅─────✧❅✦❅✧─────❅**\n\n"
            "**๏ ᴀ ᴍᴇᴍʙᴇʀ ʟᴇғᴛ ᴛʜᴇ ɢʀᴏᴜᴘ🥀**\n\n"
            f"**➻** {member.old_chat_member.user.mention}\n\n"
            "**๏ ᴏᴋ ʙʏᴇ ᴅᴇᴀʀ ᴀɴᴅ ʜᴏᴘᴇ ᴛᴏ sᴇᴇ ʏᴏᴜ ᴀɢᴀɪɴ ɪɴ ᴛʜɪs ᴄᴜᴛᴇ ɢʀᴏᴜᴘ ᴡɪᴛʜ ʏᴏᴜʀ ғʀɪᴇɴᴅs✨**\n\n"
            "**ㅤ•─╼⃝𖠁 ʙʏᴇ ♡︎ ʙᴀʙʏ 𖠁⃝╾─•**"
        )

        button_text = "๏ ᴠɪᴇᴡ ᴜsᴇʀ ๏"
        deep_link = f"tg://openmessage?user_id={user.id}"

        try:
            message = await client.send_photo(
                chat_id=member.chat.id,
                photo=welcome_photo,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(button_text, url=deep_link)]
                ])
            )

            async def delete_message():
                await asyncio.sleep(9999999999999999999999)
                await message.delete()

            asyncio.create_task(delete_message())

        except Exception:
            pass  # silently ignore send failures

        # Clean up generated userinfo image from disk
        if welcome_photo and os.path.exists(welcome_photo):
            try:
                os.remove(welcome_photo)
            except Exception:
                pass


MOD_TYPE = "MANAGEMENT"
MOD_NAME = "LeftNotice"
MOD_PRICE = "40"
