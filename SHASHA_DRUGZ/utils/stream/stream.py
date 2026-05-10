import asyncio
import os
from random import randint
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from SHASHA_DRUGZ import Carbon, YouTube, app
from SHASHA_DRUGZ.core.call import SHASHA
from SHASHA_DRUGZ.misc import db
from SHASHA_DRUGZ.utils.database import add_active_video_chat, is_active_chat
from SHASHA_DRUGZ.utils.exceptions import AssistantErr
from SHASHA_DRUGZ.utils.inline import aq_markup, queuemarkup, close_markup, stream_markup, stream_markup2
from SHASHA_DRUGZ.utils.pastebin import SHASHABin
from SHASHA_DRUGZ.utils.stream.queue import put_queue, put_queue_index
from SHASHA_DRUGZ.utils.thumbnails import get_thumb


# ─────────────────────────────────────────────────────────────────────────────
#  Formats ntgcalls/pytgcalls can handle WITHOUT conversion
# ─────────────────────────────────────────────────────────────────────────────
NATIVE_VIDEO_EXTS = {"mp4", "m4v", "webm", "mov"}
NATIVE_AUDIO_EXTS = {"mp3", "ogg", "opus", "m4a", "aac", "flac", "wav", "webm"}


def _ext(path: str) -> str:
    """Return lowercase extension without the dot."""
    return os.path.splitext(path)[-1].lstrip(".").lower()


async def ensure_compatible(file_path: str, video: bool = False) -> str:
    """
    Convert a media file to a pytgcalls-compatible format using FFmpeg
    if its container is not natively supported.

    - Video → MP4  (H.264 + AAC, fast copy when possible)
    - Audio → MP3  (copy when possible)

    Returns the (possibly new) file path. The original file is kept
    so the download cache stays valid.
    """
    ext = _ext(file_path)
    native = NATIVE_VIDEO_EXTS if video else NATIVE_AUDIO_EXTS

    if ext in native:
        return file_path  # nothing to do

    out_ext = "mp4" if video else "mp3"
    out_path = os.path.splitext(file_path)[0] + f"_converted.{out_ext}"

    if os.path.exists(out_path):
        return out_path  # already converted from a previous call

    if video:
        # Try stream-copy first (fastest, no quality loss).
        # If the codec isn't H.264/AAC, re-encode transparently.
        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-c:v", "copy",
            "-c:a", "copy",
            "-movflags", "+faststart",
            out_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-vn",                 # drop video stream
            "-c:a", "copy",        # copy audio if already MP3-compatible
            out_path,
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0 or not os.path.exists(out_path):
        # Stream-copy failed → try full re-encode
        if video:
            cmd = [
                "ffmpeg", "-y",
                "-i", file_path,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                out_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", file_path,
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "128k",
                out_path,
            ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    return out_path if os.path.exists(out_path) else file_path


# ─────────────────────────────────────────────────────────────────────────────
#  Main stream dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
):
    if not result:
        return
    if forceplay:
        await SHASHA.force_stop_stream(chat_id)

    # ── PLAYLIST ─────────────────────────────────────────────────────────────
    if streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0
        for search in result:
            if int(count) == config.PLAYLIST_FETCH_LIMIT:
                continue
            try:
                (
                    title,
                    duration_min,
                    duration_sec,
                    thumbnail,
                    vidid,
                ) = await YouTube.details(search, False if spotify else True)
            except:
                continue

            if str(duration_min) == "None":
                continue
            if duration_sec > config.DURATION_LIMIT:
                continue

            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}. {title[:70]}\n"
                msg += f"{_['play_20']} {position}\n\n"

            else:
                if not forceplay:
                    db[chat_id] = []
                status = True if video else None

                try:
                    file_path, direct = await YouTube.download(
                        vidid, mystic, video=status, videoid=True
                    )
                except:
                    raise AssistantErr(_["play_14"])

                img = await get_thumb(vidid)

                await SHASHA.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=status,
                    image=img,
                )

                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                    forceplay=forceplay,
                )

                button = stream_markup(_, vidid, chat_id)

                run = await app.send_photo(
                    original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{vidid}",
                        title[:23],
                        duration_min,
                        user_name,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )

                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"

        if count == 0:
            return
        else:
            link = await SHASHABin(msg)
            lines = msg.count("\n")
            if lines >= 17:
                car = os.linesep.join(msg.split(os.linesep)[:17])
            else:
                car = msg

            carbon = await Carbon.generate(car, randint(100, 10000000))
            upl = close_markup(_)

            return await app.send_photo(
                original_chat_id,
                photo=carbon,
                caption=_["play_21"].format(position, link),
                reply_markup=upl,
            )


    # ── YOUTUBE DIRECT ───────────────────────────────────────────────────────
    elif streamtype == "youtube":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        status = True if video else None

        try:
            file_path, direct = await YouTube.download(
                vidid, mystic, videoid=True, video=status
            )
        except:
            raise AssistantErr(_["play_14"])

        img = await get_thumb(vidid)

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )

            position = len(db.get(chat_id)) - 1
            button = queuemarkup(_, vidid, chat_id)

            await app.send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=_["queue_4"].format(
                    position, title[:20], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

        else:
            if not forceplay:
                db[chat_id] = []

            await SHASHA.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=img,
            )

            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )

            button = stream_markup(_, vidid, chat_id)

            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:12],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"


    # ── SOUNDCLOUD ───────────────────────────────────────────────────────────
    elif streamtype == "soundcloud":
        file_path = result["filepath"]
        title = result["title"]
        duration_min = result["duration_min"]

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
            )

            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)

            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(
                    position, title[:12], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

        else:
            if not forceplay:
                db[chat_id] = []

            await SHASHA.join_call(chat_id, original_chat_id, file_path, video=None)

            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
                forceplay=forceplay,
            )

            button = stream_markup2(_, chat_id)

            run = await app.send_photo(
                original_chat_id,
                photo=config.SOUNCLOUD_IMG_URL,
                caption=_["stream_1"].format(
                    config.SUPPORT_CHAT, title[:12], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"


    # ── TELEGRAM ─────────────────────────────────────────────────────────────
    elif streamtype == "telegram":
        file_path = result["path"]
        link = result["link"]
        title = (result["title"]).title()
        duration_min = result["dur"]
        status = True if video else None

        # ✅ FIX: convert MKV / AVI / WMV / FLV / etc. → MP4 (video)
        #          or any non-native audio container → MP3
        #         before handing the path to ntgcalls / pytgcalls.
        file_path = await ensure_compatible(file_path, video=bool(video))

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)

            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(
                    position, title[:12], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

        else:
            if not forceplay:
                db[chat_id] = []

            await SHASHA.join_call(
                chat_id, original_chat_id, file_path, video=status
            )

            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )

            if video:
                await add_active_video_chat(chat_id)

            button = stream_markup2(_, chat_id)

            run = await app.send_photo(
                original_chat_id,
                photo=config.TELEGRAM_VIDEO_URL if video else config.TELEGRAM_AUDIO_URL,
                caption=_["stream_1"].format(
                    link, title[:12], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"


    # ── LIVE ─────────────────────────────────────────────────────────────────
    elif streamtype == "live":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = "Live Track"
        status = True if video else None

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )

            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)

            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(
                    position, title[:12], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

        else:
            if not forceplay:
                db[chat_id] = []

            n, file_path = await YouTube.video(link)
            if n == 0:
                raise AssistantErr(_["str_3"])

            img = await get_thumb(vidid)

            await SHASHA.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=img,
            )

            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )

            button = stream_markup2(_, chat_id)

            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:12],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"


    # ── INDEX / M3U8 ─────────────────────────────────────────────────────────
    elif streamtype == "index":
        link = result
        title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"
        duration_min = "00:00"

        if await is_active_chat(chat_id):
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
            )

            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)

            await mystic.edit_text(
                text=_["queue_4"].format(
                    position, title[:27], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )

        else:
            if not forceplay:
                db[chat_id] = []

            await SHASHA.join_call(
                chat_id,
                original_chat_id,
                link,
                video=True if video else None,
            )

            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
                forceplay=forceplay,
            )

            button = stream_markup2(_, chat_id)

            run = await app.send_photo(
                original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption=_["stream_2"].format(user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )

            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            await mystic.delete()
