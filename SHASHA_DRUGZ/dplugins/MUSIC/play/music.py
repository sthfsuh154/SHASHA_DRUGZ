import random
import string
import asyncio
import os
from time import time
from typing import Union
from random import randint
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from pytgcalls.exceptions import NoActiveGroupCall
import config
from SHASHA_DRUGZ import (
    app, YouTube, Apple, Resso, SoundCloud, Spotify, Telegram, Instagram, Carbon,
)
from SHASHA_DRUGZ.core.call import SHASHA
from SHASHA_DRUGZ.misc import SUDOERS, db
from SHASHA_DRUGZ.utils.database import (
    get_loop, set_loop, is_music_playing, music_on, music_off, is_active_chat,
    is_nonadmin_chat, add_served_chat, add_served_user, get_assistant, add_active_video_chat, set_cmode,
)
from SHASHA_DRUGZ.utils.decorators import AdminRightsCheck
from SHASHA_DRUGZ.utils.decorators.language import languageCB, language
from SHASHA_DRUGZ.utils.decorators.play import PlayWrapper
from SHASHA_DRUGZ.utils.decorators.admins import AdminActual
from SHASHA_DRUGZ.utils.inline import (
    close_markup, speed_markup, stream_markup, stream_markup2, aq_markup,
    queuemarkup, panel_markup_4, botplaylist_markup, livestream_markup, playlist_markup, slider_markup, track_markup,
)
from SHASHA_DRUGZ.utils.stream.autoclear import auto_clean
from SHASHA_DRUGZ.utils.stream.stream import ensure_compatible
from SHASHA_DRUGZ.utils.thumbnails import get_thumb
from SHASHA_DRUGZ.utils.channelplay import get_channeplayCB
from SHASHA_DRUGZ.utils.formatters import formats
from SHASHA_DRUGZ.utils.logger import play_logs
from SHASHA_DRUGZ.utils.extraction import extract_user
from SHASHA_DRUGZ.utils.exceptions import AssistantErr
from SHASHA_DRUGZ.utils.pastebin import SHASHABin
from SHASHA_DRUGZ.utils.stream.queue import put_queue, put_queue_index
from SHASHA_DRUGZ.utils import seconds_to_min, time_to_seconds
from youtubesearchpython.__future__ import VideosSearch
from config import BANNED_USERS, adminlist, lyrical

ALL_VIDEO_EXTS = {
    "mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "mpeg",
    "mpg", "3gp", "3g2", "ogv", "ts", "mxf", "asf", "divx",
    "rv", "h264", "hevc", "m2ts", "vob", "m4v",
}
ALL_AUDIO_EXTS = {
    "mp3", "m4a", "aac", "ogg", "opus", "flac", "wav", "wma",
    "aiff", "aif", "amr", "awb", "ape", "dsd", "tta", "wv",
    "spx", "mid", "midi", "ra", "au",
}
ALL_MEDIA_EXTS = ALL_VIDEO_EXTS | ALL_AUDIO_EXTS

checker = []

@Client.on_message(filters.command(["channelplay"]) & filters.group & ~BANNED_USERS)
@AdminActual
@language
async def playmode_(client, message: Message, _):
    if len(message.command) < 2: return await message.reply_text(_["cplay_1"].format(message.chat.title))
    query = message.text.split(None, 2)[1].lower().strip()
    if (str(query)).lower() == "disable":
        await set_cmode(message.chat.id, None)
        return await message.reply_text(_["cplay_7"])
    elif str(query) == "linked":
        chat = await client.get_chat(message.chat.id)
        if chat.linked_chat:
            chat_id = chat.linked_chat.id
            await set_cmode(message.chat.id, chat_id)
            return await message.reply_text(_["cplay_3"].format(chat.linked_chat.title, chat.linked_chat.id))
        else: return await message.reply_text(_["cplay_2"])
    else:
        try: chat = await client.get_chat(query)
        except: return await message.reply_text(_["cplay_4"])
        if chat.type != ChatType.CHANNEL: return await message.reply_text(_["cplay_5"])
        try:
            async for user in client.get_chat_members(chat.id, filter=ChatMembersFilter.ADMINISTRATORS):
                if user.status == ChatMemberStatus.OWNER:
                    cusn = user.user.username
                    crid = user.user.id
        except: return await message.reply_text(_["cplay_4"])
        if crid != message.from_user.id: return await message.reply_text(_["cplay_6"].format(chat.title, cusn))
        await set_cmode(message.chat.id, chat.id)
        return await message.reply_text(_["cplay_3"].format(chat.title, chat.id))

@Client.on_message(filters.command(["loop", "cloop"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def admins(cli, message: Message, _, chat_id):
    usage = _["admin_17"]
    if len(message.command) != 2: return await message.reply_text(usage)
    state = message.text.split(None, 1)[1].strip()
    if state.isnumeric():
        state = int(state)
        if 1 <= state <= 10:
            got = await get_loop(chat_id)
            if got != 0: state = got + state
            if int(state) > 10: state = 10
            await set_loop(chat_id, state)
            return await message.reply_text(text=_["admin_18"].format(state, message.from_user.mention), reply_markup=close_markup(_))
        else: return await message.reply_text(_["admin_17"])
    elif state.lower() == "enable":
        await set_loop(chat_id, 10)
        return await message.reply_text(text=_["admin_18"].format(state, message.from_user.mention), reply_markup=close_markup(_))
    elif state.lower() == "disable":
        await set_loop(chat_id, 0)
        return await message.reply_text(_["admin_19"].format(message.from_user.mention), reply_markup=close_markup(_))
    else: return await message.reply_text(usage)

@Client.on_message(filters.command(["resume", "cresume"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def resume_com(cli, message: Message, _, chat_id):
    if await is_music_playing(chat_id): return await message.reply_text(_["admin_3"])
    await music_on(chat_id)
    await SHASHA.resume_stream(chat_id)
    buttons_resume = [[InlineKeyboardButton(text="sᴋɪᴘ", callback_data=f"ADMIN Skip|{chat_id}"), InlineKeyboardButton(text="sᴛᴏᴘ", callback_data=f"ADMIN Stop|{chat_id}")], [InlineKeyboardButton(text="ᴘᴀᴜsᴇ", callback_data=f"ADMIN Pause|{chat_id}")]]
    await message.reply_text(_["admin_4"].format(message.from_user.mention), reply_markup=InlineKeyboardMarkup(buttons_resume))

@Client.on_message(filters.command(["pause", "cpause"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def pause_admin(cli, message: Message, _, chat_id):
    if not await is_music_playing(chat_id): return await message.reply_text(_["admin_1"])
    await music_off(chat_id)
    await SHASHA.pause_stream(chat_id)
    buttons = [[InlineKeyboardButton(text="ʀᴇsᴜᴍᴇ", callback_data=f"ADMIN Resume|{chat_id}"), InlineKeyboardButton(text="ʀᴇᴘʟᴀʏ", callback_data=f"ADMIN Replay|{chat_id}")]]
    await message.reply_text(_["admin_2"].format(message.from_user.mention), reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_message(filters.command(["cspeed", "speed", "cslow", "slow", "playback", "cplayback"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def playback(cli, message: Message, _, chat_id):
    playing = db.get(chat_id)
    if not playing: return await message.reply_text(text=_["queue_2"])
    duration_seconds = int(playing[0]["seconds"])
    if duration_seconds == 0: return await message.reply_text(text=_["admin_27"])
    file_path = playing[0]["file"]
    if "downloads" not in file_path: return await message.reply_text(text=_["admin_27"])
    upl = speed_markup(_, chat_id)
    return await message.reply_text(text=_["admin_28"].format(cli.me.mention), reply_markup=upl)

@Client.on_callback_query(filters.regex("SpeedUP") & ~BANNED_USERS)
@languageCB
async def del_back_playlist(client, callback_query, _):
    callback_data = callback_query.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    chat, speed = callback_request.split("|")
    chat_id = int(chat)
    if not await is_active_chat(chat_id): return await callback_query.answer(_["general_5"], show_alert=True)
    is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
    if not is_non_admin:
        if callback_query.from_user.id not in SUDOERS:
            admins = adminlist.get(callback_query.message.chat.id)
            if not admins: return await callback_query.answer(_["admin_13"], show_alert=True)
            else:
                if callback_query.from_user.id not in admins: return await callback_query.answer(_["admin_14"], show_alert=True)
    playing = db.get(chat_id)
    if not playing: return await callback_query.answer(_["queue_2"], show_alert=True)
    duration_seconds = int(playing[0]["seconds"])
    if duration_seconds == 0: return await callback_query.answer(_["admin_27"], show_alert=True)
    file_path = playing[0]["file"]
    if "downloads" not in file_path: return await callback_query.answer(_["admin_27"], show_alert=True)
    checkspeed = playing[0].get("speed")
    if checkspeed:
        if str(checkspeed) == str(speed):
            if str(speed) == str("1.0"): return await callback_query.answer(_["admin_29"], show_alert=True)
    else:
        if str(speed) == str("1.0"): return await callback_query.answer(_["admin_29"], show_alert=True)
    if chat_id in checker: return await callback_query.answer(_["admin_30"], show_alert=True)
    else: checker.append(chat_id)
    try: await callback_query.answer(_["admin_31"])
    except: pass
    mystic = await callback_query.message.reply_text(text=_["admin_32"].format(callback_query.from_user.mention))
    try: await SHASHA.speedup_stream(chat_id, file_path, speed, playing)
    except:
        if chat_id in checker: checker.remove(chat_id)
        return await callback_query.message.reply_text(text=_["admin_33"], reply_markup=close_markup(_))
    if chat_id in checker: checker.remove(chat_id)
    await callback_query.message.reply_text(text=_["admin_34"].format(speed, callback_query.from_user.mention), reply_markup=close_markup(_))

@Client.on_message(filters.command(["end", "cend"], prefixes=["end", "/", "!", "%", ",", "", ".", "@", "#"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def stop_music(cli, message: Message, _, chat_id):
    if not len(message.command) == 1: return
    await SHASHA.stop_stream(chat_id)
    await set_loop(chat_id, 0)
    await message.reply_text(_["admin_5"].format(message.from_user.mention), reply_markup=close_markup(_))

@Client.on_message(filters.command(["skip", "cskip", "next", "cnext"], prefixes=["skip", "/", "!", "%", ",", ".", "@", "#"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def skip(cli, message: Message, _, chat_id):
    if not len(message.command) < 2:
        loop = await get_loop(chat_id)
        if loop != 0: return await message.reply_text(_["admin_8"])
        state = message.text.split(None, 1)[1].strip()
        if state.isnumeric():
            state = int(state)
            check = db.get(chat_id)
            if check:
                count = len(check)
                if count > 2:
                    count = int(count - 1)
                    if 1 <= state <= count:
                        for x in range(state):
                            popped = None
                            try: popped = check.pop(0)
                            except: return await message.reply_text(_["admin_12"])
                            if popped: await auto_clean(popped)
                            if not check:
                                try:
                                    await message.reply_text(text=_["admin_6"].format(message.from_user.mention, message.chat.title), reply_markup=close_markup(_))
                                    await SHASHA.stop_stream(chat_id)
                                except: return
                                break
                    else: return await message.reply_text(_["admin_11"].format(count))
                else: return await message.reply_text(_["admin_10"])
            else: return await message.reply_text(_["queue_2"])
        else: return await message.reply_text(_["admin_9"])
    else:
        check = db.get(chat_id)
        popped = None
        try:
            popped = check.pop(0)
            if popped: await auto_clean(popped)
            if not check:
                await message.reply_text(text=_["admin_6"].format(message.from_user.mention, message.chat.title), reply_markup=close_markup(_))
                try: return await SHASHA.stop_stream(chat_id)
                except: return
        except:
            try:
                await message.reply_text(text=_["admin_6"].format(message.from_user.mention, message.chat.title), reply_markup=close_markup(_))
                return await SHASHA.stop_stream(chat_id)
            except: return

    queued = check[0]["file"]
    title = (check[0]["title"]).title()
    user = check[0]["by"]
    streamtype = check[0]["streamtype"]
    videoid = check[0]["vidid"]
    status = True if str(streamtype) == "video" else None
    db[chat_id][0]["played"] = 0
    exis = (check[0]).get("old_dur")
    if exis:
        db[chat_id][0]["dur"] = exis
        db[chat_id][0]["seconds"] = check[0]["old_second"]
        db[chat_id][0]["speed_path"] = None
        db[chat_id][0]["speed"] = 1.0

    if "live_" in queued:
        n, link = await YouTube.video(videoid, True)
        if n == 0: return await message.reply_text(_["admin_7"].format(title))
        try: image = await YouTube.thumbnail(videoid, True)
        except: image = None
        try: await SHASHA.skip_stream(chat_id, link, video=status, image=image)
        except: return await message.reply_text(_["call_6"])
        button = stream_markup2(_, chat_id)
        img = await get_thumb(videoid)
        run = await message.reply_photo(photo=img, caption=_["stream_1"].format(f"https://t.me/{cli.me.username}?start=info_{videoid}", title[:23], check[0]["dur"], user), reply_markup=InlineKeyboardMarkup(button))
        db[chat_id][0]["mystic"] = run
        db[chat_id][0]["markup"] = "tg"

    elif "vid_" in queued:
        mystic = await message.reply_text(_["call_7"], disable_web_page_preview=True)
        try: file_path, direct = await YouTube.download(videoid, mystic, videoid=True, video=status)
        except: return await mystic.edit_text(_["call_6"])
        try: image = await YouTube.thumbnail(videoid, True)
        except: image = None
        try: await SHASHA.skip_stream(chat_id, file_path, video=status, image=image)
        except: return await mystic.edit_text(_["call_6"])
        button = stream_markup(_, videoid, chat_id)
        img = await get_thumb(videoid)
        run = await message.reply_photo(photo=img, caption=_["stream_1"].format(f"https://t.me/{cli.me.username}?start=info_{videoid}", title[:23], check[0]["dur"], user), reply_markup=InlineKeyboardMarkup(button))
        db[chat_id][0]["mystic"] = run
        db[chat_id][0]["markup"] = "stream"
        await mystic.delete()

    elif "index_" in queued:
        try: await SHASHA.skip_stream(chat_id, videoid, video=status)
        except: return await message.reply_text(_["call_6"])
        button = stream_markup2(_, chat_id)
        run = await message.reply_photo(photo=config.STREAM_IMG_URL, caption=_["stream_2"].format(user), reply_markup=InlineKeyboardMarkup(button))
        db[chat_id][0]["mystic"] = run
        db[chat_id][0]["markup"] = "tg"

    else:
        if videoid == "telegram": image = None
        elif videoid == "soundcloud": image = None
        else:
            try: image = await YouTube.thumbnail(videoid, True)
            except: image = None
        try: await SHASHA.skip_stream(chat_id, queued, video=status, image=image)
        except: return await message.reply_text(_["call_6"])
        if videoid == "telegram":
            button = stream_markup2(_, chat_id)
            run = await message.reply_photo(photo=config.TELEGRAM_AUDIO_URL if str(streamtype) == "audio" else config.TELEGRAM_VIDEO_URL, caption=_["stream_1"].format(config.SUPPORT_CHAT, title[:23], check[0]["dur"], user), reply_markup=InlineKeyboardMarkup(button))
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
        elif videoid == "soundcloud":
            button = stream_markup2(_, chat_id)
            run = await message.reply_photo(photo=config.SOUNCLOUD_IMG_URL if str(streamtype) == "audio" else config.TELEGRAM_VIDEO_URL, caption=_["stream_1"].format(config.SUPPORT_CHAT, title[:23], check[0]["dur"], user), reply_markup=InlineKeyboardMarkup(button))
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
        else:
            button = stream_markup(_, videoid, chat_id)
            img = await get_thumb(videoid)
            run = await message.reply_photo(photo=img, caption=_["stream_1"].format(f"https://t.me/{cli.me.username}?start=info_{videoid}", title[:23], check[0]["dur"], user), reply_markup=InlineKeyboardMarkup(button))
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"

@Client.on_message(filters.command(["seek", "cseek", "seekback", "cseekback"]) & filters.group & ~BANNED_USERS)
@AdminRightsCheck
async def seek_comm(cli, message: Message, _, chat_id):
    if len(message.command) == 1: return await message.reply_text(_["admin_20"])
    query = message.text.split(None, 1)[1].strip()
    if not query.isnumeric(): return await message.reply_text(_["admin_21"])
    playing = db.get(chat_id)
    if not playing: return await message.reply_text(_["queue_2"])
    duration_seconds = int(playing[0]["seconds"])
    if duration_seconds == 0: return await message.reply_text(_["admin_22"])
    file_path = playing[0]["file"]
    duration_played = int(playing[0]["played"])
    duration_to_skip = int(query)
    duration = playing[0]["dur"]
    if message.command[0][-2] == "c":
        if (duration_played - duration_to_skip) <= 10: return await message.reply_text(text=_["admin_23"].format(seconds_to_min(duration_played), duration), reply_markup=close_markup(_))
        to_seek = duration_played - duration_to_skip + 1
    else:
        if (duration_seconds - (duration_played + duration_to_skip)) <= 10: return await message.reply_text(text=_["admin_23"].format(seconds_to_min(duration_played), duration), reply_markup=close_markup(_))
        to_seek = duration_played + duration_to_skip + 1
    mystic = await message.reply_text(_["admin_24"])
    if "vid_" in file_path:
        n, file_path = await YouTube.video(playing[0]["vidid"], True)
        if n == 0: return await message.reply_text(_["admin_22"])
    check = (playing[0]).get("speed_path")
    if check: file_path = check
    if "index_" in file_path: file_path = playing[0]["vidid"]
    try: await SHASHA.seek_stream(chat_id, file_path, seconds_to_min(to_seek), duration, playing[0]["streamtype"])
    except: return await mystic.edit_text(_["admin_26"], reply_markup=close_markup(_))
    if message.command[0][-2] == "c": db[chat_id][0]["played"] -= duration_to_skip
    else: db[chat_id][0]["played"] += duration_to_skip
    await mystic.edit_text(text=_["admin_25"].format(seconds_to_min(to_seek), message.from_user.mention), reply_markup=close_markup(_))

@Client.on_message(filters.command(["play", "vplay", "cplay", "cvplay", "playforce", "vplayforce", "cplayforce", "cvplayforce"], prefixes=["/", "!", "%", "", ".", "@", "#"]) & filters.group & ~BANNED_USERS)
@PlayWrapper
async def play_commnd(client, message: Message, _, chat_id, video, channel, playmode, url, fplay):
    await add_served_chat(message.chat.id)
    mystic = await message.reply_text(_["play_2"].format(channel) if channel else _["play_1"])
    plist_id, slider, plist_type, spotify = None, None, None, None
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    audio_telegram = ((message.reply_to_message.audio or message.reply_to_message.voice) if message.reply_to_message else None)
    video_telegram = ((message.reply_to_message.video or message.reply_to_message.document) if message.reply_to_message else None)

    if audio_telegram:
        if audio_telegram.file_size > 104857600: return await mystic.edit_text(_["play_5"])
        duration_min = seconds_to_min(audio_telegram.duration)
        if (audio_telegram.duration) > config.DURATION_LIMIT: return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, client.me.mention))
        file_path = await Telegram.get_filepath(audio=audio_telegram)
        if await Telegram.download(_, message, mystic, file_path):
            message_link = await Telegram.get_link(message)
            file_name = await Telegram.get_filename(audio_telegram, audio=True)
            dur = await Telegram.get_duration(audio_telegram, file_path)
            details = {"title": file_name, "link": message_link, "path": file_path, "dur": dur}
            try: await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, streamtype="telegram", forceplay=fplay)
            except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
            return await mystic.delete()
        return

    elif video_telegram:
        if message.reply_to_message.document:
            try:
                fname = video_telegram.file_name or ""
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                mime = (video_telegram.mime_type or "").lower()
                is_media = (ext in ALL_MEDIA_EXTS or mime.startswith("video/") or mime.startswith("audio/"))
                if not is_media: return await mystic.edit_text(_["play_7"].format("mp4 | mkv | avi | mov | wmv | flv | webm | mpeg | 3gp | ts | m4v | mp3 | m4a | aac | ogg | opus | flac | wav"))
            except Exception: return await mystic.edit_text(_["play_7"].format("mp4 | mkv | avi | mov | wmv | flv | webm | mpeg | 3gp | ts | m4v | mp3 | m4a | aac | ogg | opus | flac | wav"))
        if video_telegram.file_size > config.TG_VIDEO_FILESIZE_LIMIT: return await mystic.edit_text(_["play_8"])
        file_path = await Telegram.get_filepath(video=video_telegram)
        if await Telegram.download(_, message, mystic, file_path):
            message_link = await Telegram.get_link(message)
            file_name = await Telegram.get_filename(video_telegram)
            dur = await Telegram.get_duration(video_telegram, file_path)
            details = {"title": file_name, "link": message_link, "path": file_path, "dur": dur}
            try: await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, video=True, streamtype="telegram", forceplay=fplay)
            except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
            return await mystic.delete()
        return

    elif url:
        if await YouTube.exists(url):
            if "playlist" in url:
                try: details = await YouTube.playlist(url, config.PLAYLIST_FETCH_LIMIT, message.from_user.id)
                except Exception: return await mystic.edit_text(_["play_3"])
                streamtype, plist_type, img, cap = "playlist", "yt", config.PLAYLIST_IMG_URL, _["play_10"]
                plist_id = (url.split("=")[1]).split("&")[0] if "&" in url else url.split("=")[1]
            elif "https://youtu.be" in url:
                videoid = url.split("/")[-1].split("?")[0]
                details, track_id = await YouTube.track(f"https://www.youtube.com/watch?v={videoid}")
                streamtype, img, cap = "youtube", details["thumb"], _["play_11"].format(details["title"], details["duration_min"])
            elif "youtube.com/@" in url:
                try:
                    video_urls = fetch_channel_videos(url)
                    for video_url in video_urls:
                        details, track_id = await YouTube.track(video_url)
                        await queue_video_for_playback(video_url, details, track_id, "playlist", details["thumb"], _["play_10"].format(details["title"], details["duration_min"]))
                    await mystic.edit_text("All videos from the channel have been added to the queue.")
                except Exception: await mystic.edit_text(_["play_3"])
            else:
                try: details, track_id = await YouTube.track(url)
                except Exception: return await mystic.edit_text(_["play_3"])
                streamtype, img, cap = "youtube", details["thumb"], _["play_11"].format(details["title"], details["duration_min"])
        elif await Spotify.valid(url):
            spotify = True
            if not config.SPOTIFY_CLIENT_ID and not config.SPOTIFY_CLIENT_SECRET: return await mystic.edit_text("» sᴘᴏᴛɪғʏ ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ʏᴇᴛ.\n\nᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.")
            if "track" in url:
                try: details, track_id = await Spotify.track(url)
                except: return await mystic.edit_text(_["play_3"])
                streamtype, img, cap = "youtube", details["thumb"], _["play_10"].format(details["title"], details["duration_min"])
            elif "playlist" in url:
                try: details, plist_id = await Spotify.playlist(url)
                except Exception: return await mystic.edit_text(_["play_3"])
                streamtype, plist_type, img, cap = "playlist", "spplay", config.SPOTIFY_PLAYLIST_IMG_URL, _["play_11"].format(client.me.mention, message.from_user.mention)
            elif "album" in url:
                try: details, plist_id = await Spotify.album(url)
                except: return await mystic.edit_text(_["play_3"])
                streamtype, plist_type, img, cap = "playlist", "spalbum", config.SPOTIFY_ALBUM_IMG_URL, _["play_11"].format(client.me.mention, message.from_user.mention)
            elif "artist" in url:
                try: details, plist_id = await Spotify.artist(url)
                except: return await mystic.edit_text(_["play_3"])
                streamtype, plist_type, img, cap = "playlist", "spartist", config.SPOTIFY_ARTIST_IMG_URL, _["play_11"].format(message.from_user.first_name)
            else: return await mystic.edit_text(_["play_15"])
        elif await Apple.valid(url):
            if "album" in url:
                try: details, track_id = await Apple.track(url)
                except: return await mystic.edit_text(_["play_3"])
                streamtype, img, cap = "youtube", details["thumb"], _["play_10"].format(details["title"], details["duration_min"])
            elif "playlist" in url:
                spotify = True
                try: details, plist_id = await Apple.playlist(url)
                except: return await mystic.edit_text(_["play_3"])
                streamtype, plist_type, cap, img = "playlist", "apple", _["play_12"].format(client.me.mention, message.from_user.mention), url
            else: return await mystic.edit_text(_["play_3"])
        elif await Resso.valid(url):
            try: details, track_id = await Resso.track(url)
            except: return await mystic.edit_text(_["play_3"])
            streamtype, img, cap = "youtube", details["thumb"], _["play_10"].format(details["title"], details["duration_min"])
        elif await SoundCloud.valid(url):
            try: details, track_path = await SoundCloud.download(url)
            except: return await mystic.edit_text(_["play_3"])
            if details["duration_sec"] > config.DURATION_LIMIT: return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, client.me.mention))
            try: await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, streamtype="soundcloud", forceplay=fplay)
            except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
            return await mystic.delete()
        elif await Instagram.valid(url):
            try: details, track_id = await Instagram.track(url)
            except Exception: return await mystic.edit_text(_["play_3"])
            streamtype, img, cap = "instagram", details.get("thumb") or config.STREAM_IMG_URL, _["play_11"].format(details["title"], details["duration_min"])
        else:
            try: await SHASHA.stream_call(url)
            except NoActiveGroupCall:
                await mystic.edit_text(_["black_9"])
                return await client.send_message(chat_id=config.LOGGER_ID, text=_["play_17"])
            except Exception as e: return await mystic.edit_text(_["general_2"].format(type(e).__name__))
            await mystic.edit_text(_["str_2"])
            try: await stream(_, mystic, message.from_user.id, url, chat_id, message.from_user.first_name, message.chat.id, video=video, streamtype="index", forceplay=fplay)
            except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
            return await play_logs(message, streamtype="M3u8 or Index Link")

    else:
        if len(message.command) < 2: return await mystic.edit_text(_["play_18"], reply_markup=InlineKeyboardMarkup(botplaylist_markup(_)))
        slider = True
        query = message.text.split(None, 1)[1].replace("-v", "")
        try: details, track_id = await YouTube.track(query)
        except: return await mystic.edit_text(_["play_3"])
        streamtype = "youtube"

    if str(playmode) == "Direct":
        if not plist_type:
            if details["duration_min"]:
                if time_to_seconds(details["duration_min"]) > config.DURATION_LIMIT:
                    return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, client.me.mention))
            else:
                return await mystic.edit_text(_["play_13"], reply_markup=InlineKeyboardMarkup(livestream_markup(_, track_id, user_id, "v" if video else "a", "c" if channel else "g", "f" if fplay else "d")))
        try: await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, video=video, streamtype=streamtype, spotify=spotify, forceplay=fplay)
        except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
        await mystic.delete()
        return await play_logs(message, streamtype=streamtype)
    else:
        if plist_type:
            ran_hash = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
            lyrical[ran_hash] = plist_id
            await mystic.delete()
            await message.reply_photo(photo=img, caption=cap, reply_markup=InlineKeyboardMarkup(playlist_markup(_, ran_hash, message.from_user.id, plist_type, "c" if channel else "g", "f" if fplay else "d")))
            return await play_logs(message, streamtype=f"Playlist : {plist_type}")
        else:
            if slider:
                await mystic.delete()
                await message.reply_photo(photo=details["thumb"], caption=_["play_10"].format(details["title"].title(), details["duration_min"]), reply_markup=InlineKeyboardMarkup(slider_markup(_, track_id, message.from_user.id, query, 0, "c" if channel else "g", "f" if fplay else "d")))
                return await play_logs(message, streamtype="Searched on Youtube")
            else:
                await mystic.delete()
                thumb = await get_thumb(track_id)
                await message.reply_photo(photo=thumb, caption=cap, reply_markup=InlineKeyboardMarkup(track_markup(_, track_id, message.from_user.id, "c" if channel else "g", "f" if fplay else "d")))
                return await play_logs(message, streamtype="URL Searched Inline")

@Client.on_callback_query(filters.regex("MusicStream") & ~BANNED_USERS)
@languageCB
async def play_music(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    vidid, user_id, mode, cplay, fplay = callback_request.split("|")
    if CallbackQuery.from_user.id != int(user_id):
        try: return await CallbackQuery.answer(_["playcb_1"], show_alert=True)
        except: return
    try: chat_id, channel = await get_channeplayCB(_, cplay, CallbackQuery)
    except: return
    user_name = CallbackQuery.from_user.first_name
    try:
        await CallbackQuery.message.delete()
        await CallbackQuery.answer()
    except: pass
    mystic = await CallbackQuery.message.reply_text(_["play_2"].format(channel) if channel else _["play_1"])
    try: details, track_id = await YouTube.track(vidid, True)
    except: return await mystic.edit_text(_["play_3"])

    if details["duration_min"]:
        if time_to_seconds(details["duration_min"]) > config.DURATION_LIMIT: return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, client.me.mention))
    else: return await mystic.edit_text(_["play_13"], reply_markup=InlineKeyboardMarkup(livestream_markup(_, track_id, CallbackQuery.from_user.id, mode, "c" if cplay == "c" else "g", "f" if fplay else "d")))

    try: await stream(_, mystic, CallbackQuery.from_user.id, details, chat_id, user_name, CallbackQuery.message.chat.id, True if mode == "v" else None, streamtype="youtube", forceplay=True if fplay == "f" else None)
    except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
    return await mystic.delete()

@Client.on_callback_query(filters.regex("SHASHAmousAdmin") & ~BANNED_USERS)
async def SHASHAmous_check(client, CallbackQuery):
    try: await CallbackQuery.answer("» ʀᴇᴠᴇʀᴛ ʙᴀᴄᴋ ᴛᴏ ᴜsᴇʀ ᴀᴄᴄᴏᴜɴᴛ :\n\nᴏᴘᴇɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs.\n-> ᴀᴅᴍɪɴɪsᴛʀᴀᴛᴏʀs\n-> ᴄʟɪᴄᴋ ᴏɴ ʏᴏᴜʀ ɴᴀᴍᴇ\n-> ᴜɴᴄʜᴇᴄᴋ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.", show_alert=True)
    except: pass

@Client.on_callback_query(filters.regex("SHASHAPlaylists") & ~BANNED_USERS)
@languageCB
async def play_playlists_command(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    (videoid, user_id, ptype, mode, cplay, fplay,) = callback_request.split("|")
    if CallbackQuery.from_user.id != int(user_id):
        try: return await CallbackQuery.answer(_["playcb_1"], show_alert=True)
        except: return
    try: chat_id, channel = await get_channeplayCB(_, cplay, CallbackQuery)
    except: return
    user_name = CallbackQuery.from_user.first_name
    await CallbackQuery.message.delete()
    try: await CallbackQuery.answer()
    except: pass
    mystic = await CallbackQuery.message.reply_text(_["play_2"].format(channel) if channel else _["play_1"])
    videoid = lyrical.get(videoid)
    video = True if mode == "v" else None
    ffplay = True if fplay == "f" else None
    spotify = True
    if ptype == "yt":
        spotify = False
        try: result = await YouTube.playlist(videoid, config.PLAYLIST_FETCH_LIMIT, CallbackQuery.from_user.id, True)
        except: return await mystic.edit_text(_["play_3"])
    if ptype == "spplay":
        try: result, spotify_id = await Spotify.playlist(videoid)
        except: return await mystic.edit_text(_["play_3"])
    if ptype == "spalbum":
        try: result, spotify_id = await Spotify.album(videoid)
        except: return await mystic.edit_text(_["play_3"])
    if ptype == "spartist":
        try: result, spotify_id = await Spotify.artist(videoid)
        except: return await mystic.edit_text(_["play_3"])
    if ptype == "apple":
        try: result, apple_id = await Apple.playlist(videoid, True)
        except: return await mystic.edit_text(_["play_3"])
    try: await stream(_, mystic, user_id, result, chat_id, user_name, CallbackQuery.message.chat.id, video, streamtype="playlist", spotify=spotify, forceplay=ffplay)
    except Exception as e: return await mystic.edit_text(e if type(e).__name__ == "AssistantErr" else _["general_2"].format(type(e).__name__))
    return await mystic.delete()

@Client.on_callback_query(filters.regex("slider") & ~BANNED_USERS)
@languageCB
async def slider_queries(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    (what, rtype, query, user_id, cplay, fplay,) = callback_request.split("|")
    if CallbackQuery.from_user.id != int(user_id):
        try: return await CallbackQuery.answer(_["playcb_1"], show_alert=True)
        except: return
    what, rtype = str(what), int(rtype)
    if what == "F":
        query_type = 0 if rtype == 9 else int(rtype + 1)
        try: await CallbackQuery.answer(_["playcb_2"])
        except: pass
        title, duration_min, thumbnail, vidid = await YouTube.slider(query, query_type)
        buttons = slider_markup(_, vidid, user_id, query, query_type, cplay, fplay)
        med = InputMediaPhoto(media=thumbnail, caption=_["play_10"].format(title.title(), duration_min))

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_22"
__help__ = """
🎶 ᴘʟᴀʏ
🔻 /play ➠ ᴀᴜᴅɪᴏ
🔻 /vplay ➠ ᴠɪᴅᴇᴏ
🔻 /cplay ➠ ᴄʜᴀɴɴᴇʟ ᴀᴜᴅɪᴏ
🔻 /cvplay ➠ ᴄʜᴀɴɴᴇʟ ᴠɪᴅᴇᴏ
🔻 /playforce ➠ ꜰᴏʀᴄᴇ & ꜱᴋɪᴘ
🔻 /vplayforce ➠ ᴠɪᴅᴇᴏ ꜰᴏʀᴄᴇ
🔻 /cplayforce ➠ ᴄʜᴀɴɴᴇʟ ᴀᴜᴅɪᴏ ꜰᴏʀᴄᴇ
🔻 /cvplayforce ➠ ᴄʜᴀɴɴᴇʟ ᴠɪᴅᴇᴏ ꜰᴏʀᴄᴇ
⏸ ᴘᴀᴜꜱᴇ/ʀᴇꜱᴜᴍᴇ
🔻 /pause / /resume
🔻 /cpause / /cresume
⏹ ꜱᴛᴏᴘ
🔻 /end / /cend
⏭ ꜱᴋɪᴘ/ɴᴇxᴛ
🔻 /skip / /next
🔻 /cskip / /cnext
🔁 ʟᴏᴏᴘ
🔻 /loop 1-10 / enable / disable
🔻 /cloop
⏩ ꜱᴘᴇᴇᴅ
🔻 /speed / /cspeed
🔻 /slow / /cslow
🔻 /playback / /cplayback
📢 ᴄʜᴀɴɴᴇʟ ᴘʟᴀʏ
🔻 /channelplay [channel username/id or linked or disable]
"""
MOD_TYPE = "MUSIC"
MOD_NAME = "MUSIC-BOT"
MOD_PRICE = "250"
