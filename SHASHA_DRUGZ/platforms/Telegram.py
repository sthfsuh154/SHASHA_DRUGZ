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
    "audio/mpeg":               "mp3",
    "audio/mp3":                "mp3",
    "audio/mp4":                "m4a",
    "audio/x-m4a":              "m4a",
    "audio/m4a":                "m4a",
    "audio/aac":                "aac",
    "audio/x-aac":              "aac",
    "audio/ogg":                "ogg",
    "audio/opus":               "opus",
    "audio/x-opus":             "opus",
    "audio/flac":               "flac",
    "audio/x-flac":             "flac",
    "audio/wav":                "wav",
    "audio/x-wav":              "wav",
    "audio/vnd.wave":           "wav",
    "audio/webm":               "webm",
    "audio/x-ms-wma":           "wma",
    "audio/wma":                "wma",
    "audio/aiff":               "aiff",
    "audio/x-aiff":             "aiff",
    "audio/amr":                "amr",
    "audio/amr-wb":             "awb",
    "audio/3gpp":               "3gp",
    "audio/3gpp2":              "3g2",
    "audio/x-ape":              "ape",
    "audio/ape":                "ape",
    "audio/dsd":                "dsd",
    "audio/x-tta":              "tta",
    "audio/x-wavpack":          "wv",
    "audio/speex":              "spx",
    "audio/midi":               "mid",
    "audio/x-midi":             "mid",
    "audio/x-realaudio":        "ra",
    "audio/vnd.rn-realaudio":   "ra",
    "audio/basic":              "au",
    "audio/au":                 "au",
}

# ─────────────────────────────────────────────
#  Supported VIDEO file extensions & MIME types
# ─────────────────────────────────────────────
VIDEO_MIME_MAP = {
    "video/mp4":                "mp4",
    "video/x-m4v":              "m4v",
    "video/x-matroska":         "mkv",
    "video/matroska":           "mkv",
    "video/webm":               "webm",
    "video/x-msvideo":          "avi",
    "video/avi":                "avi",
    "video/quicktime":          "mov",
    "video/x-ms-wmv":           "wmv",
    "video/wmv":                "wmv",
    "video/x-flv":              "flv",
    "video/flv":                "flv",
    "video/mpeg":               "mpeg",
    "video/mpg":                "mpg",
    "video/x-mpeg":             "mpeg",
    "video/3gpp":               "3gp",
    "video/3gpp2":              "3g2",
    "video/ogg":                "ogv",
    "video/mp2t":               "ts",
    "video/x-mpeg2-ts":         "ts",
    "video/mxf":                "mxf",
    "video/x-ms-asf":           "asf",
    "video/divx":               "divx",
    "video/x-divx":             "divx",
    "video/x-xvid":             "avi",
    "video/vnd.rn-realvideo":   "rv",
    "video/x-real-video":       "rv",
    "video/h264":               "h264",
    "video/x-h264":             "h264",
    "video/hevc":               "hevc",
    "video/h265":               "hevc",
    "video/vp8":                "webm",
    "video/vp9":                "webm",
    "video/m2ts":               "m2ts",
    "video/x-m2ts":             "m2ts",
    "video/x-ms-vob":           "vob",
    "video/dvd":                "vob",
    # Catch-all for application/octet-stream video files
    "application/octet-stream": "mp4",
}

# ─────────────────────────────────────────────
#  Document extension sets (for doc-type media)
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
                guessed = mimetypes.guess_extension(mime)
                if guessed:
                    return guessed.lstrip(".").lower()
        except Exception:
            pass

        # 3. hardcoded fallback
        return fallback

    def is_video_document(self, file) -> bool:
        """
        Returns True if a document file is actually a video based on
        its extension OR mime type.
        """
        try:
            name = file.file_name or ""
            if "." in name:
                ext = name.rsplit(".", 1)[-1].lower().strip()
                if ext in DOCUMENT_VIDEO_EXTS:
                    return True
        except Exception:
            pass
        try:
            mime = (file.mime_type or "").lower().strip()
            if mime in VIDEO_MIME_MAP:
                return True
            if mime.startswith("video/"):
                return True
        except Exception:
            pass
        return False

    def is_audio_document(self, file) -> bool:
        """
        Returns True if a document file is actually audio based on
        its extension OR mime type.
        """
        try:
            name = file.file_name or ""
            if "." in name:
                ext = name.rsplit(".", 1)[-1].lower().strip()
                if ext in DOCUMENT_AUDIO_EXTS:
                    return True
        except Exception:
            pass
        try:
            mime = (file.mime_type or "").lower().strip()
            if mime in AUDIO_MIME_MAP:
                return True
            if mime.startswith("audio/"):
                return True
        except Exception:
            pass
        return False

    # ── public API ───────────────────────────────────────────────────────

    async def send_split_text(self, message, string):
        n = self.chars_limit
        out = [(string[i: i + n]) for i in range(0, len(string), n)]
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

        NOTE: ensure_compatible() in stream.py will re-encode to H.264+AAC
              if the actual codec inside the file isn't supported by ntgcalls.
              So we just need to preserve the real extension here.
        """
        downloads_dir = os.path.realpath("downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        if audio:
            if isinstance(audio, Voice):
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
