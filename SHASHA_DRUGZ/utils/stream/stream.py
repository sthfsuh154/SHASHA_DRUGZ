import asyncio
import json
import os
from random import randint
from typing import Union
from pyrogram.types import InlineKeyboardMarkup
import config
from SHASHA_DRUGZ import Carbon, YouTube, app
from SHASHA_DRUGZ.core.call import SHASHA, _safe_send_photo, _safe_send_message
from SHASHA_DRUGZ.misc import db
from SHASHA_DRUGZ.utils.database import add_active_video_chat, is_active_chat
from SHASHA_DRUGZ.utils.exceptions import AssistantErr
from SHASHA_DRUGZ.utils.inline import aq_markup, queuemarkup, close_markup, stream_markup, stream_markup2
from SHASHA_DRUGZ.utils.pastebin import SHASHABin
from SHASHA_DRUGZ.utils.stream.queue import put_queue, put_queue_index
from SHASHA_DRUGZ.utils.thumbnails import get_thumb

SUPPORTED_VIDEO_CODECS = {"h264"}
SUPPORTED_AUDIO_CODECS = {"aac"}


async def _probe(file_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        file_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
    except Exception as e:
        print(f"[_probe] ffprobe launch failed for {file_path}: {e}")
        return {"video_codec": None, "audio_codec": None, "format": None}

    result = {"video_codec": None, "audio_codec": None, "format": None}
    try:
        data = json.loads(stdout)
        fmt = data.get("format", {}).get("format_name", "")
        result["format"] = fmt.lower() if fmt else None
        for s in data.get("streams", []):
            ctype = s.get("codec_type", "")
            cname = s.get("codec_name", "").lower()
            if ctype == "video" and result["video_codec"] is None:
                result["video_codec"] = cname
            elif ctype == "audio" and result["audio_codec"] is None:
                result["audio_codec"] = cname
    except Exception as ex:
        print(f"[_probe] JSON parse error for {file_path}: {ex}")
    return result


def _compat_is_valid(source_path: str, compat_path: str) -> bool:
    try:
        if not os.path.exists(compat_path):
            return False
        if os.path.getsize(compat_path) == 0:
            return False
        src_mtime    = os.path.getmtime(source_path)
        compat_mtime = os.path.getmtime(compat_path)
        return compat_mtime >= src_mtime
    except Exception:
        return False


async def ensure_compatible(file_path: str, video: bool = False) -> str:
    if not file_path or not os.path.exists(file_path):
        print(f"[ensure_compatible] File not found: {file_path}")
        return file_path

    # ✅ FIX: Reject corrupt/empty files immediately — don't waste time on them
    if os.path.getsize(file_path) == 0:
        print(f"[ensure_compatible] File is empty (0 bytes), skipping: {file_path}")
        return file_path

    if file_path.endswith("_compat.mp4") or file_path.endswith("_compat.m4a"):
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path

    info = await _probe(file_path)
    v_codec = info["video_codec"]
    a_codec = info["audio_codec"]
    fmt     = info["format"] or ""

    # ✅ FIX: If ffprobe found NO streams at all, the file is corrupt — bail out
    if v_codec is None and a_codec is None:
        print(f"[ensure_compatible] No streams found in {file_path} — file may be corrupt")
        return file_path

    is_mp4_container = "mov,mp4" in fmt or fmt == "mp4"

    if video:
        needs_v = (v_codec is not None) and (v_codec not in SUPPORTED_VIDEO_CODECS)
        needs_a = (a_codec is not None) and (a_codec not in SUPPORTED_AUDIO_CODECS)
        no_vid  = v_codec is None

        if is_mp4_container and not needs_v and not needs_a and not no_vid:
            return file_path

        out_path = os.path.splitext(file_path)[0] + "_compat.mp4"
        if _compat_is_valid(file_path, out_path):
            print(f"[ensure_compatible] Using valid cache: {out_path}")
            return out_path

        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass

        cmd = ["ffmpeg", "-y", "-i", file_path]
        if no_vid:
            cmd += ["-f", "lavfi", "-i", "color=c=black:s=1280x720:r=24", "-shortest"]
            v_flag = "libx264"
        else:
            v_flag = "copy" if not needs_v else "libx264"
        a_flag = "copy" if not needs_a else "aac"
        cmd += ["-c:v", v_flag, "-c:a", a_flag]
        if v_flag == "libx264":
            cmd += ["-preset", "ultrafast", "-crf", "23"]
        if a_flag == "aac":
            cmd += ["-b:a", "128k"]
        cmd += ["-f", "mp4", "-movflags", "+faststart", out_path]
    else:
        needs_a = (a_codec is not None) and (a_codec not in SUPPORTED_AUDIO_CODECS)
        is_native_audio = (
            file_path.lower().endswith((".m4a", ".aac")) and not needs_a
        )
        if is_native_audio:
            return file_path

        out_path = os.path.splitext(file_path)[0] + "_compat.m4a"
        if _compat_is_valid(file_path, out_path):
            print(f"[ensure_compatible] Using valid cache: {out_path}")
            return out_path

        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass

        a_flag = "copy" if not needs_a else "aac"
        cmd = ["ffmpeg", "-y", "-i", file_path, "-vn", "-c:a", a_flag]
        if a_flag == "aac":
            cmd += ["-b:a", "128k"]
        cmd.append(out_path)

    print(f"[ensure_compatible] Running: {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
    except Exception as e:
        print(f"[ensure_compatible] ffmpeg launch failed: {e}")
        return file_path

    if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        print(f"[ensure_compatible] ffmpeg error for {file_path}:\n{stderr.decode(errors='replace')}")
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        return file_path

    print(f"[ensure_compatible] Done: {file_path} → {out_path}")
    return out_path


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
                (title, duration_min, duration_sec, thumbnail, vidid,) = \
                    await YouTube.details(search, False if spotify else True)
            except:
                continue
            if str(duration_min) == "None":
                continue
            if duration_sec > config.DURATION_LIMIT:
                continue
            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id, original_chat_id, f"vid_{vidid}", title, duration_min,
                    user_name, vidid, user_id, "video" if video else "audio",
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
                    chat_id, original_chat_id, file_path, video=status, image=img,
                )
                await put_queue(
                    chat_id, original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title, duration_min, user_name, vidid, user_id,
                    "video" if video else "audio", forceplay=forceplay,
                )
                button = stream_markup(_, vidid, chat_id)
                # ✅ FIX: use _safe_send_photo so deployed bots send via their own client
                run = await _safe_send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{vidid}",
                        title[:23], duration_min, user_name,
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
            return await _safe_send_photo(
                chat_id=original_chat_id,
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
                chat_id, original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title, duration_min, user_name, vidid, user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = queuemarkup(_, vidid, chat_id)
            await _safe_send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=_["queue_4"].format(position, title[:20], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await SHASHA.join_call(
                chat_id, original_chat_id, file_path, video=status, image=img,
            )
            await put_queue(
                chat_id, original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title, duration_min, user_name, vidid, user_id,
                "video" if video else "audio", forceplay=forceplay,
            )
            button = stream_markup(_, vidid, chat_id)
            run = await _safe_send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:12], duration_min, user_name,
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
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await _safe_send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:12], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await SHASHA.join_call(chat_id, original_chat_id, file_path, video=None)
            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "audio", forceplay=forceplay,
            )
            button = stream_markup2(_, chat_id)
            run = await _safe_send_photo(
                chat_id=original_chat_id,
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
        file_path    = result["path"]
        link         = result["link"]
        title        = (result["title"]).title()
        duration_min = result["dur"]
        status       = True if video else None

        # ✅ FIX: Validate file before processing — catch corrupt/empty downloads
        if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise AssistantErr(_["play_14"])

        file_path = await ensure_compatible(file_path, video=bool(video))

        # ✅ FIX: If ensure_compatible returned the original and it's still corrupt,
        #         don't attempt to play — pytgcalls will throw NoAudioSourceFound
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise AssistantErr(_["play_14"])

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await _safe_send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:12], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await SHASHA.join_call(chat_id, original_chat_id, file_path, video=status)
            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "video" if video else "audio",
                forceplay=forceplay,
            )
            if video:
                await add_active_video_chat(chat_id)
            button = stream_markup2(_, chat_id)
            run = await _safe_send_photo(
                chat_id=original_chat_id,
                photo=config.TELEGRAM_VIDEO_URL if video else config.TELEGRAM_AUDIO_URL,
                caption=_["stream_1"].format(link, title[:12], duration_min, user_name),
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
                chat_id, original_chat_id, f"live_{vidid}", title, duration_min,
                user_name, vidid, user_id, "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await _safe_send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:12], duration_min, user_name),
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
                chat_id, original_chat_id, file_path, video=status, image=img,
            )
            await put_queue(
                chat_id, original_chat_id, f"live_{vidid}", title, duration_min,
                user_name, vidid, user_id, "video" if video else "audio",
                forceplay=forceplay,
            )
            button = stream_markup2(_, chat_id)
            run = await _safe_send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:12], duration_min, user_name,
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
                chat_id, original_chat_id, "index_url", title, duration_min,
                user_name, link, "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await mystic.edit_text(
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await SHASHA.join_call(
                chat_id, original_chat_id, link, video=True if video else None,
            )
            await put_queue_index(
                chat_id, original_chat_id, "index_url", title, duration_min,
                user_name, link, "video" if video else "audio", forceplay=forceplay,
            )
            button = stream_markup2(_, chat_id)
            run = await _safe_send_photo(
                chat_id=original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption=_["stream_2"].format(user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            await mystic.delete()
