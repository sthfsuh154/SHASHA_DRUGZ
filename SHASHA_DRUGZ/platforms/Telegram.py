import asyncio
import mimetypes
import os
import time
from typing import Union

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Voice

import config
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.formatters import (
    check_duration,
    convert_bytes,
    get_readable_time,
    seconds_to_min,
)

# ─────────────────────────────────────────────
#  Supported AUDIO file extensions & MIME types
# ─────────────────────────────────────────────
AUDIO_MIME_MAP = {
    # MP3
    "audio/mpeg":           "mp3",
    "audio/mp3":            "mp3",
    # MP4 audio / iTunes
    "audio/mp4":            "m4a",
    "audio/x-m4a":         "m4a",
    "audio/m4a":            "m4a",
    # AAC
    "audio/aac":            "aac",
    "audio/x-aac":         "aac",
    # OGG / Vorbis / Opus
    "audio/ogg":            "ogg",
    "audio/opus":           "opus",
    "audio/x-opus":        "opus",
    # FLAC
    "audio/flac":           "flac",
    "audio/x-flac":        "flac",
    # WAV / PCM
    "audio/wav":            "wav",
    "audio/x-wav":         "wav",
    "audio/vnd.wave":      "wav",
    # WebM audio
    "audio/webm":           "webm",
    # WMA
    "audio/x-ms-wma":      "wma",
    "audio/wma":            "wma",
    # AIFF
    "audio/aiff":           "aiff",
    "audio/x-aiff":        "aiff",
    # AMR (common in voice notes)
    "audio/amr":            "amr",
    "audio/amr-wb":        "awb",
    # 3GP audio
    "audio/3gpp":           "3gp",
    "audio/3gpp2":         "3g2",
    # APE (Monkey's Audio)
    "audio/x-ape":         "ape",
    "audio/ape":            "ape",
    # DSD
    "audio/dsd":            "dsd",
    # TrueAudio
    "audio/x-tta":         "tta",
    # WavPack
    "audio/x-wavpack":     "wv",
    # Speex
    "audio/speex":          "spx",
    # MIDI
    "audio/midi":           "mid",
    "audio/x-midi":        "mid",
    # RA / RealAudio
    "audio/x-realaudio":   "ra",
    "audio/vnd.rn-realaudio": "ra",
    # AU (Sun / NeXT)
    "audio/basic":          "au",
    "audio/au":             "au",
}

# ─────────────────────────────────────────────
#  Supported VIDEO file extensions & MIME types
# ─────────────────────────────────────────────
VIDEO_MIME_MAP = {
    # MP4
    "video/mp4":                    "mp4",
    "video/x-m4v":                 "m4v",
    # MKV (Matroska)
    "video/x-matroska":            "mkv",
    "video/matroska":              "mkv",
    # WebM
    "video/webm":                   "webm",
    # AVI
    "video/x-msvideo":             "avi",
    "video/avi":                    "avi",
    # MOV (QuickTime)
    "video/quicktime":              "mov",
    # WMV
    "video/x-ms-wmv":              "wmv",
    "video/wmv":                    "wmv",
    # FLV
    "video/x-flv":                 "flv",
    "video/flv":                    "flv",
    # MPEG / MPG
    "video/mpeg":                   "mpeg",
    "video/mpg":                    "mpg",
    "video/x-mpeg":                "mpeg",
    # 3GP / 3G2
    "video/3gpp":                   "3gp",
    "video/3gpp2":                 "3g2",
    # OGV
    "video/ogg":                    "ogv",
    # TS (MPEG Transport Stream)
    "video/mp2t":                   "ts",
    "video/x-mpeg2-ts":            "ts",
    # MXF
    "video/mxf":                    "mxf",
    # ASF
    "video/x-ms-asf":              "asf",
    # DivX
    "video/divx":                   "divx",
    "video/x-divx":                "divx",
    # Xvid (usually reported as AVI)
    "video/x-xvid":                "avi",
    # RM / RealVideo
    "video/vnd.rn-realvideo":      "rv",
    "video/x-real-video":          "rv",
    # H.264 raw stream
    "video/h264":                   "h264",
    "video/x-h264":                "h264",
    # H.265 / HEVC raw stream
    "video/hevc":                   "hevc",
    "video/h265":                   "hevc",
    # VP8 / VP9
    "video/vp8":                    "webm",
    "video/vp9":                    "webm",
    # M2TS / Blu-ray
    "video/m2ts":                   "m2ts",
    "video/x-m2ts":                "m2ts",
    # VOB (DVD)
    "video/x-ms-vob":              "vob",
    "video/dvd":                    "vob",
}

# ─────────────────────────────────────────────
#  Supported DOCUMENT / generic extensions
#  (in case someone sends a media file as doc)
# ─────────────────────────────────────────────
DOCUMENT_AUDIO_EXTS = {
    "mp3", "m4a", "aac", "ogg", "opus", "flac", "wav", "webm",
    "wma", "aiff", "aif", "amr", "awb", "3gp", "3g2", "ape",
    "dsd", "tta", "wv", "spx", "mid", "midi", "ra", "au",
}

DOCUMENT_VIDEO_EXTS = {
    "mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "mpeg",
    "mpg", "3gp", "3g2", "ogv", "ts", "mxf", "asf", "divx",
    "rv", "h264", "hevc", "m2ts", "vob", "m4v",
}


class TeleAPI:
    def __init__(self):
        self.chars_limit = 4096
        self.sleep = 5

    # ── helpers ──────────────────────────────────────────────────────────

    def _resolve_ext(self, file, mime_map: dict, fallback: str) -> str:
        """
        Try to determine a file extension in this order:
          1. file_name attribute  (most reliable)
          2. mime_type attribute  (looked up in our mime_map, then stdlib)
          3. fallback             (hardcoded safe default)
        """
        # 1. file_name
        try:
            name = file.file_name
            if name and "." in name:
                ext = name.rsplit(".", 1)[-1].lower().strip()
                if ext:
                    return ext
        except Exception:
            pass

        # 2. mime_type
        try:
            mime = (file.mime_type or "").lower().strip()
            if mime:
                if mime in mime_map:
                    return mime_map[mime]
                # fall back to Python's stdlib mimetypes
                guessed = mimetypes.guess_extension(mime)
                if guessed:
                    return guessed.lstrip(".").lower()
        except Exception:
            pass

        # 3. hardcoded fallback
        return fallback

    # ── public API ───────────────────────────────────────────────────────

    async def send_split_text(self, message, string):
        n = self.chars_limit
        out = [(string[i : i + n]) for i in range(0, len(string), n)]
        j = 0
        for x in out:
            if j <= 2:
                j += 1
                await message.reply_text(x, disable_web_page_preview=True)
        return True

    async def get_link(self, message):
        return message.link

    async def get_filename(self, file, audio: Union[bool, str] = None):
        try:
            file_name = file.file_name
            if file_name is None:
                file_name = "ᴛᴇʟᴇɢʀᴀᴍ ᴀᴜᴅɪᴏ" if audio else "ᴛᴇʟᴇɢʀᴀᴍ ᴠɪᴅᴇᴏ"
        except Exception:
            file_name = "ᴛᴇʟᴇɢʀᴀᴍ ᴀᴜᴅɪᴏ" if audio else "ᴛᴇʟᴇɢʀᴀᴍ ᴠɪᴅᴇᴏ"
        return file_name

    async def get_duration(self, filex, file_path):
        try:
            dur = seconds_to_min(filex.duration)
        except Exception:
            try:
                dur = await asyncio.get_event_loop().run_in_executor(
                    None, check_duration, file_path
                )
                dur = seconds_to_min(dur)
            except Exception:
                return "Unknown"
        return dur

    async def get_filepath(
        self,
        audio: Union[bool, str] = None,
        video: Union[bool, str] = None,
    ):
        """
        Returns the local download path for an audio or video file.

        Supported audio : mp3 m4a aac ogg opus flac wav webm wma aiff amr
                          awb 3gp 3g2 ape dsd tta wv spx mid ra au
        Supported video : mp4 mkv webm avi mov wmv flv mpeg mpg 3gp 3g2
                          ogv ts mxf asf divx rv h264 hevc m2ts vob m4v
        Voice messages  : always saved as .ogg
        """
        downloads_dir = os.path.realpath("downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        if audio:
            if isinstance(audio, Voice):
                # Telegram Voice messages are always Opus inside OGG
                ext = "ogg"
            else:
                ext = self._resolve_ext(audio, AUDIO_MIME_MAP, "mp3")
            file_name = os.path.join(downloads_dir, f"{audio.file_unique_id}.{ext}")

        if video:
            ext = self._resolve_ext(video, VIDEO_MIME_MAP, "mp4")
            file_name = os.path.join(downloads_dir, f"{video.file_unique_id}.{ext}")

        return file_name

    async def download(self, _, message, mystic, fname):
        lower   = [0,  8,  17, 38, 64, 77, 96]
        higher  = [5,  10, 20, 40, 66, 80, 99]
        checker = [5,  10, 20, 40, 66, 80, 99]
        speed_counter = {}

        if os.path.exists(fname):
            return True

        async def down_load():
            async def progress(current, total):
                if current == total:
                    return

                current_time = time.time()
                start_time   = speed_counter.get(message.id)
                check_time   = current_time - start_time

                upl = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="ᴄᴀɴᴄᴇʟ",
                                callback_data="stop_downloading",
                            )
                        ]
                    ]
                )

                percentage    = current * 100 / total
                percentage    = str(round(percentage, 2))
                speed         = current / check_time
                eta           = int((total - current) / speed)
                eta           = get_readable_time(eta)
                if not eta:
                    eta = "0 sᴇᴄᴏɴᴅs"

                total_size     = convert_bytes(total)
                completed_size = convert_bytes(current)
                speed          = convert_bytes(speed)
                percentage     = int((percentage.split("."))[0])

                for counter in range(7):
                    low   = int(lower[counter])
                    high  = int(higher[counter])
                    check = int(checker[counter])
                    if low < percentage <= high:
                        if high == check:
                            try:
                                await mystic.edit_text(
                                    text=_["tg_1"].format(
                                        app.mention,
                                        total_size,
                                        completed_size,
                                        percentage,
                                        speed,
                                        eta,
                                    ),
                                    reply_markup=upl,
                                )
                                checker[counter] = 100
                            except Exception:
                                pass

            speed_counter[message.id] = time.time()
            try:
                await app.download_media(
                    message.reply_to_message,
                    file_name=fname,
                    progress=progress,
                )
                try:
                    elapsed = get_readable_time(
                        int(time.time()) - int(speed_counter[message.id])
                    )
                except Exception:
                    elapsed = "0 sᴇᴄᴏɴᴅs"
                await mystic.edit_text(_["tg_2"].format(elapsed))
            except Exception:
                await mystic.edit_text(_["tg_3"])

        task = asyncio.create_task(down_load())
        config.lyrical[mystic.id] = task
        await task

        verify = config.lyrical.get(mystic.id)
        if not verify:
            return False

        config.lyrical.pop(mystic.id)
        return True
