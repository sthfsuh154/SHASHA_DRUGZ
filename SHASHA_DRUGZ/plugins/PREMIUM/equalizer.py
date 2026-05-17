import os
import asyncio
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import ChatAdminRequired
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.types.input_stream.quality import HighQualityAudio
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.call import SHASHA as call_py
from motor.motor_asyncio import AsyncIOMotorClient

# ----------------------------- Mongo DB Setup -----------------------------
try:
    from config import MONGO_DB_URI as MONGO_URL
    from SHASHA_DRUGZ.misc import SUDOERS
except ImportError:
    MONGO_URL = os.environ.get(
        "MONGO_URL",
        "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority"
    )

# Create MongoDB client and database
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["SHASHA_DRUGZ"]

# Collections
GROUP_EQ_DB = db["GROUP_EQUALIZER"]
USER_EQ_DB  = db["USER_EQUALIZER"]

# ----------------------------- Constants & Presets -----------------------------
BASE_AUDIO_ENGINE = "dynaudnorm,alimiter=limit=0.9"

EQ_PRESETS = {
    "normal": "",
    "bass": "bass=g=8",
    "extreme_bass": "bass=g=15",
    "vocal": "equalizer=f=1000:t=q:w=1:g=5",
    "classical": "equalizer=f=2500:t=q:w=1:g=4",
    "pop": "equalizer=f=1500:t=q:w=1:g=6",
    "rock": "equalizer=f=3000:t=q:w=1:g=6",
    "jazz": "equalizer=f=500:t=q:w=1:g=5",
    "edm": "bass=g=10,treble=g=6",
    "party": "bass=g=12,treble=g=8",
    "night": "volume=0.6",
    "soft": "volume=0.8",
    "flat": "",
    "triple_bass": "bass=g=20",
    "deep_sub": "bass=g=25",
    "soft_bass": "bass=g=5",
    "bass_clean": "bass=g=6,highpass=f=200",
    "clear_voice": "equalizer=f=2000:t=q:w=1:g=8",
    "dialogue": "equalizer=f=3000:t=q:w=1:g=10",
    "karaoke": "pan=stereo|c0=c0-c1|c1=c1-c0",
    "nightcore": "asetrate=48000*1.25,atempo=1.1",
    "slow_reverb": "atempo=0.8,aecho=0.8:0.9:1000:0.3",
    "echo": "aecho=0.8:0.9:1000:0.3",
    "reverb": "aecho=0.8:0.9:1000:0.4",
    "8d": "apulsator=hz=0.09,stereotools=mlev=1",
    "chipmunk": "asetrate=48000*1.4,atempo=1.2",
    "deep_voice": "asetrate=48000*0.8,atempo=0.9"
}

MIN_VOL = 0
MAX_VOL = 200

# ----------------------------- Helper Functions for Filter Parsing -----------------------------
def parse_filter(filter_string: str):
    if not filter_string:
        return {}
    parts = filter_string.split(",")
    result = {}
    for part in parts:
        match = re.match(r"([a-zA-Z0-9_]+)=(.+)", part)
        if match:
            name, params = match.groups()
            result[name] = params
        else:
            result[part] = ""
    return result

def build_filter(components: dict):
    if not components:
        return ""
    return ",".join(f"{k}={v}" for k, v in components.items() if v != "")

def merge_with_preset(current_components: dict, preset_filter: str):
    return parse_filter(preset_filter)

# ----------------------------- Database Helpers -----------------------------
async def save_group_eq(chat_id: int, filter_string: str, auto_bpm: bool = False, dynamic_eq: bool = False):
    await GROUP_EQ_DB.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "filter": filter_string,
            "auto_bpm": auto_bpm,
            "dynamic_eq": dynamic_eq
        }},
        upsert=True
    )

async def get_group_eq(chat_id: int):
    data = await GROUP_EQ_DB.find_one({"chat_id": chat_id})
    if data:
        return data.get("filter", ""), data.get("auto_bpm", False), data.get("dynamic_eq", False)
    return "", False, False

async def apply_eq(chat_id: int, filter_string: str):
    final_filter = BASE_AUDIO_ENGINE
    if filter_string:
        final_filter = f"{BASE_AUDIO_ENGINE},{filter_string}"
    current = call_py.get_call(chat_id)
    if not current:
        return False
    await call_py.change_stream(
        chat_id,
        AudioPiped(
            current.input_filename,
            audio_parameters=HighQualityAudio(),
            ffmpeg_parameters=f"-af {final_filter}"
        )
    )
    _, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    await save_group_eq(chat_id, filter_string, auto_bpm, dynamic_eq)
    return True

# ----------------------------- Dynamic & Auto BPM Tasks -----------------------------
dynamic_tasks = {}
autobpm_tasks = {}

async def dynamic_eq_loop(chat_id: int):
    cycle = [
        "bass=g=8",
        "treble=g=6",
        "bass=g=6,treble=g=4",
        "equalizer=f=1000:t=q:w=1:g=5"
    ]
    idx = 0
    while True:
        try:
            if not call_py.get_call(chat_id):
                break
            _, _, dynamic_eq = await get_group_eq(chat_id)
            if not dynamic_eq:
                break
            await apply_eq(chat_id, cycle[idx % len(cycle)])
            idx += 1
            await asyncio.sleep(30)
        except Exception as e:
            logging.error(f"Dynamic EQ error in {chat_id}: {e}")
            break
    dynamic_tasks.pop(chat_id, None)

async def auto_bpm_loop(chat_id: int):
    modes = ["bass=g=12", "treble=g=8,equalizer=f=3000:t=q:w=1:g=4"]
    idx = 0
    while True:
        try:
            if not call_py.get_call(chat_id):
                break
            _, auto_bpm, _ = await get_group_eq(chat_id)
            if not auto_bpm:
                break
            await apply_eq(chat_id, modes[idx % 2])
            idx += 1
            await asyncio.sleep(15)
        except Exception as e:
            logging.error(f"Auto BPM error in {chat_id}: {e}")
            break
    autobpm_tasks.pop(chat_id, None)

def start_dynamic(chat_id: int):
    if chat_id in dynamic_tasks:
        return
    task = asyncio.create_task(dynamic_eq_loop(chat_id))
    dynamic_tasks[chat_id] = task

def start_auto_bpm(chat_id: int):
    if chat_id in autobpm_tasks:
        return
    task = asyncio.create_task(auto_bpm_loop(chat_id))
    autobpm_tasks[chat_id] = task

def stop_dynamic(chat_id: int):
    if chat_id in dynamic_tasks:
        dynamic_tasks[chat_id].cancel()
        del dynamic_tasks[chat_id]

def stop_auto_bpm(chat_id: int):
    if chat_id in autobpm_tasks:
        autobpm_tasks[chat_id].cancel()
        del autobpm_tasks[chat_id]

def stop_all_loops(chat_id: int):
    stop_dynamic(chat_id)
    stop_auto_bpm(chat_id)

# ----------------------------- UI Markups -----------------------------
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎚 ᴘʀᴇsᴇᴛs", callback_data="eq_presets")],
        [InlineKeyboardButton("🔊 ʙᴀss +", callback_data="eq_bass_plus"),
         InlineKeyboardButton("🔉 ʙᴀss -", callback_data="eq_bass_minus")],
        [InlineKeyboardButton("🔈 ᴠᴏʟ -", callback_data="eq_vol_minus"),
         InlineKeyboardButton("🔊 ᴠᴏʟ +", callback_data="eq_vol_plus")],
        [InlineKeyboardButton("🌀 ᴅʏɴᴀᴍɪᴄ ᴇǫ", callback_data="eq_toggle_dynamic")],
        [InlineKeyboardButton("🎛 ʀᴇsᴇᴛ ᴇǫ", callback_data="eq_reset")]
    ])

def preset_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ʙᴀss ʙᴏᴏsᴛ", callback_data="eq_bass"),
         InlineKeyboardButton("ᴇxᴛʀᴇᴍᴇ ʙᴀss", callback_data="eq_extreme_bass")],
        [InlineKeyboardButton("ᴠᴏᴄᴀʟ ʙᴏᴏsᴛ", callback_data="eq_vocal"),
         InlineKeyboardButton("ʀᴏᴄᴋ", callback_data="eq_rock")],
        [InlineKeyboardButton("ᴇᴅᴍ", callback_data="eq_edm"),
         InlineKeyboardButton("ᴊᴀᴢᴢ", callback_data="eq_jazz")],
        [InlineKeyboardButton("ɴɪɢʜᴛᴄᴏʀᴇ", callback_data="eq_nightcore"),
         InlineKeyboardButton("sʟᴏᴡ + ʀᴇᴠᴇʀʙ", callback_data="eq_slow_reverb")],
        [InlineKeyboardButton("🎛 ʙᴀᴄᴋ", callback_data="eq_back")]
    ])

# ----------------------------- Live Status Helper -----------------------------
async def get_status_text(chat_id: int):
    filter_string, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    comp = parse_filter(filter_string)
    bass = comp.get("bass", "g=0")
    treble = comp.get("treble", "g=0")
    volume = comp.get("volume", "1.0")
    try:
        vol_percent = int(float(volume) * 100)
    except:
        vol_percent = 100
    effects = []
    for effect in ["echo", "reverb", "aecho", "apulsator", "pan"]:
        if effect in comp:
            effects.append(effect)
    status = f"<blockquote>**🎛 sʜᴀsʜᴀ ᴘʀᴇᴍɪᴜᴍ ᴇǫᴜᴀʟɪᴢᴇʀ**</blockquote>\n"
    status += f"<blockquote>🔊 **ʙᴀss:** `{bass}`\n"
    status += f"🎵 **ᴛʀᴇʙʟᴇ:** `{treble}`\n"
    status += f"🔉 **ᴠᴏʟᴜᴍᴇ:** `{vol_percent}%`\n"
    status += f"🔄 **ᴀᴜᴛᴏ ʙᴘᴍ:** `{'ON' if auto_bpm else 'OFF'}`\n"
    status += f"🌀 **ᴅʏɴᴀᴍɪᴄ ᴇǫ:** `{'ON' if dynamic_eq else 'OFF'}`\n</blockquote>"
    if effects:
        status += f"<blockquote>🎶 **ᴇғғᴇᴄᴛs:** `{', '.join(effects)}`</blockquote>\n"
    return status

# ----------------------------- Command Handlers -----------------------------
@app.on_message(filters.command(["equalizer", "eq"]) & filters.group)
async def equalizer_cmd(_, message):
    chat_id = message.chat.id
    status = await get_status_text(chat_id)
    await message.reply(status, reply_markup=main_menu())


@app.on_message(filters.command("resetequalizer") & filters.group)
async def reset_eq(_, message):
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        if not member.privileges.can_manage_voice_chats:
            raise ChatAdminRequired
    except:
        await message.reply("<blockquote>❌ ᴏɴʟʏ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs ᴄᴀɴ ʀᴇsᴇᴛ ᴛʜᴇ ᴇǫᴜᴀʟɪᴢᴇʀ.</blockquote>")
        return
    chat_id = message.chat.id
    stop_all_loops(chat_id)
    await apply_eq(chat_id, "")
    await GROUP_EQ_DB.delete_one({"chat_id": chat_id})
    await message.reply("<blockquote>✅ ᴇǫᴜᴀʟɪᴢᴇʀ ғᴜʟʟʏ ʀᴇsᴇᴛ ғᴏʀ ᴛʜɪs ɢʀᴏᴜᴘ.</blockquote>")


@app.on_message(filters.command(["vol", "volume"]) & filters.group)
async def volume_cmd(_, message):
    if len(message.command) < 2:
        return await message.reply("<blockquote>ᴜsᴀɢᴇ: `/vol 150` (0‑200)</blockquote>")
    try:
        vol = int(message.command[1])
        if vol < MIN_VOL or vol > MAX_VOL:
            raise ValueError
    except:
        return await message.reply(
            f"<blockquote>❌ ᴠᴏʟᴜᴍᴇ ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ ʙᴇᴛᴡᴇᴇɴ {MIN_VOL} ᴀɴᴅ {MAX_VOL}.</blockquote>"
        )
    chat_id = message.chat.id
    current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    comp = parse_filter(current_filter)
    gain = vol / 100.0
    comp["volume"] = str(gain)
    new_filter = build_filter(comp)
    ok = await apply_eq(chat_id, new_filter)
    if not ok:
        return await message.reply("<blockquote>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴠᴏɪᴄᴇ ᴄᴀʟʟ ғᴏᴜɴᴅ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.</blockquote>")
    await message.reply(f"<blockquote>🔊 ᴠᴏʟᴜᴍᴇ sᴇᴛ ᴛᴏ **{vol}%**</blockquote>")


@app.on_message(filters.command("bass") & filters.group)
async def bass_cmd(_, message):
    chat_id = message.chat.id
    current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    comp = parse_filter(current_filter)
    if len(message.command) == 1:
        comp["bass"] = "g=8"
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        return await message.reply("<blockquote>🔊 ʙᴀss ʙᴏᴏsᴛᴇᴅ (ᴅᴇғᴀᴜʟᴛ ʟᴇᴠᴇʟ 8)</blockquote>")
    try:
        gain = int(message.command[1])
        if gain < 0 or gain > 30:
            raise ValueError
    except:
        return await message.reply("<blockquote>ʙᴀss ɢᴀɪɴ ᴍᴜsᴛ ʙᴇ 0‑30 (e.g., `/bass 12`)</blockquote>")
    comp["bass"] = f"g={gain}"
    new_filter = build_filter(comp)
    await apply_eq(chat_id, new_filter)
    await message.reply(f"<blockquote>🔊 ʙᴀss sᴇᴛ ᴛᴏ **{gain}**</blockquote>")


@app.on_message(filters.command("treble") & filters.group)
async def treble_cmd(_, message):
    chat_id = message.chat.id
    current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    comp = parse_filter(current_filter)
    if len(message.command) == 1:
        comp["treble"] = "g=6"
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        return await message.reply("<blockquote>🎵 ᴛʀᴇʙʟᴇ ʙᴏᴏsᴛᴇᴅ (ᴅᴇғᴀᴜʟᴛ ʟᴇᴠᴇʟ 6)</blockquote>")
    try:
        gain = int(message.command[1])
        if gain < 0 or gain > 20:
            raise ValueError
    except:
        return await message.reply("<blockquote>ᴛʀᴇʙʟᴇ ɢᴀɪɴ ᴍᴜsᴛ ʙᴇ 0‑20 (e.g., `/treble 8`)</blockquote>")
    comp["treble"] = f"g={gain}"
    new_filter = build_filter(comp)
    await apply_eq(chat_id, new_filter)
    await message.reply(f"<blockquote>🎵 ᴛʀᴇʙʟᴇ sᴇᴛ ᴛᴏ **{gain}**</blockquote>")


@app.on_message(filters.command(list(EQ_PRESETS.keys())) & filters.group)
async def preset_cmd(_, message):
    cmd = message.command[0].lower()
    if cmd in EQ_PRESETS:
        chat_id = message.chat.id
        preset_filter = EQ_PRESETS[cmd]
        comp = parse_filter(preset_filter)
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await message.reply(f"<blockquote>✅ ᴘʀᴇsᴇᴛ **{cmd.capitalize()}** ᴀᴘᴘʟɪᴇᴅ.</blockquote>")


@app.on_message(filters.command("autobpm") & filters.group)
async def autobpm_toggle_cmd(_, message):
    chat_id = message.chat.id
    current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    new_state = not auto_bpm
    await save_group_eq(chat_id, current_filter, new_state, dynamic_eq)
    if new_state:
        start_auto_bpm(chat_id)
        await message.reply("✅ Auto BPM mode **enabled** (simulated).")
    else:
        stop_auto_bpm(chat_id)
        await message.reply("❌ Auto BPM mode **disabled**.")


@app.on_message(filters.command("dynamiceq") & filters.group)
async def dynamiceq_toggle_cmd(_, message):
    chat_id = message.chat.id
    current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
    new_state = not dynamic_eq
    await save_group_eq(chat_id, current_filter, auto_bpm, new_state)
    if new_state:
        start_dynamic(chat_id)
        await message.reply("<blockquote>✅ ᴅʏɴᴀᴍɪᴄ ᴇǫ ᴍᴏᴅᴇ **ᴇɴᴀʙʟᴇᴅ** (ᴄʏᴄʟɪɴɢ ᴘʀᴇsᴇᴛs).</blockquote>")
    else:
        stop_dynamic(chat_id)
        await message.reply("<blockquote>❌ ᴅʏɴᴀᴍɪᴄ ᴇǫ ᴍᴏᴅᴇ **ᴅɪsᴀʙʟᴇᴅ**.</blockquote>")

# ----------------------------- Callback Handlers -----------------------------
@app.on_callback_query(filters.regex("^eq_"))
async def eq_callback(_, query: CallbackQuery):
    data = query.data.replace("eq_", "")
    chat_id = query.message.chat.id

    if data == "presets":
        await query.message.edit_text("<blockquote>🎚 **sᴇʟᴇᴄᴛ ᴘʀᴇsᴇᴛ:**</blockquote>", reply_markup=preset_menu())
        return

    if data == "back":
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "reset":
        stop_all_loops(chat_id)
        await apply_eq(chat_id, "")
        await query.answer("ᴇǫ ʀᴇsᴇᴛ ✅")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "bass_plus":
        current_filter, _, _ = await get_group_eq(chat_id)
        comp = parse_filter(current_filter)
        current_bass = comp.get("bass", "g=0")
        try:
            val = int(current_bass.split("=")[-1]) if "=" in current_bass else 0
        except:
            val = 0
        new_val = min(val + 2, 30)
        comp["bass"] = f"g={new_val}"
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer(f"Bass increased to {new_val}")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "bass_minus":
        current_filter, _, _ = await get_group_eq(chat_id)
        comp = parse_filter(current_filter)
        current_bass = comp.get("bass", "g=0")
        try:
            val = int(current_bass.split("=")[-1]) if "=" in current_bass else 0
        except:
            val = 0
        new_val = max(val - 2, 0)
        comp["bass"] = f"g={new_val}" if new_val > 0 else ""
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer(f"Bass reduced to {new_val}")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "vol_plus":
        current_filter, _, _ = await get_group_eq(chat_id)
        comp = parse_filter(current_filter)
        try:
            current_vol = int(float(comp.get("volume", "1.0")) * 100)
        except:
            current_vol = 100
        new_vol = min(current_vol + 10, MAX_VOL)
        comp["volume"] = str(new_vol / 100.0)
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer(f"Volume increased to {new_vol}%")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "vol_minus":
        current_filter, _, _ = await get_group_eq(chat_id)
        comp = parse_filter(current_filter)
        try:
            current_vol = int(float(comp.get("volume", "1.0")) * 100)
        except:
            current_vol = 100
        new_vol = max(current_vol - 10, MIN_VOL)
        comp["volume"] = str(new_vol / 100.0)
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer(f"Volume decreased to {new_vol}%")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "dj":
        comp = {"bass": "g=10", "treble": "g=10"}
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer("DJ Mode Activated 🎧")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "multiband":
        multiband = (
            "equalizer=f=60:t=q:w=1:g=5,"
            "equalizer=f=170:t=q:w=1:g=4,"
            "equalizer=f=310:t=q:w=1:g=3,"
            "equalizer=f=600:t=q:w=1:g=2,"
            "equalizer=f=1000:t=q:w=1:g=2,"
            "equalizer=f=3000:t=q:w=1:g=3,"
            "equalizer=f=6000:t=q:w=1:g=4,"
            "equalizer=f=12000:t=q:w=1:g=5"
        )
        comp = parse_filter(multiband)
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer("10‑Band EQ Applied 🎛")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "toggle_autobpm":
        current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
        new_state = not auto_bpm
        await save_group_eq(chat_id, current_filter, new_state, dynamic_eq)
        if new_state:
            start_auto_bpm(chat_id)
            await query.answer("Auto BPM enabled")
        else:
            stop_auto_bpm(chat_id)
            await query.answer("Auto BPM disabled")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data == "toggle_dynamic":
        current_filter, auto_bpm, dynamic_eq = await get_group_eq(chat_id)
        new_state = not dynamic_eq
        await save_group_eq(chat_id, current_filter, auto_bpm, new_state)
        if new_state:
            start_dynamic(chat_id)
            await query.answer("Dynamic EQ enabled")
        else:
            stop_dynamic(chat_id)
            await query.answer("Dynamic EQ disabled")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

    if data in EQ_PRESETS:
        preset_filter = EQ_PRESETS[data]
        comp = parse_filter(preset_filter)
        new_filter = build_filter(comp)
        await apply_eq(chat_id, new_filter)
        await query.answer(f"{data.replace('_', ' ').title()} Applied ✅")
        status = await get_status_text(chat_id)
        await query.message.edit_text(status, reply_markup=main_menu())
        return

# ----------------------------- Cleanup on Call End -----------------------------
async def cleanup_on_call_end(_, chat_id: int):
    stop_all_loops(chat_id)

# Register the cleanup function on all available PyTgCalls clients
for client in [call_py.one, call_py.two, call_py.three, call_py.four, call_py.five]:
    if client:
        client.on_kicked()(cleanup_on_call_end)
        client.on_closed_voice_chat()(cleanup_on_call_end)

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_41"
__help__ = """
🔻 /equalizer | /eq ➠ ᴏᴘᴇɴꜱ ᴛʜᴇ ᴇQᴜᴀʟɪᴢᴇʀ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ.
🔻 /resetequalizer ➠ ʀᴇꜱᴇᴛꜱ ᴛʜᴇ ᴇQᴜᴀʟɪᴢᴇʀ ꜰᴜʟʟʏ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
🔻 /vol 0-200 | /volume 0-200 ➠ ꜱᴇᴛꜱ ᴛʜᴇ ᴘʟᴀʏʙᴀᴄᴋ ᴠᴏʟᴜᴍᴇ.
🔻 /bass 0-30 ➠ ꜱᴇᴛꜱ ᴄᴜꜱᴛᴏᴍ ʙᴀꜱꜱ ʟᴇᴠᴇʟ.
🔻 /treble ➠ ʙᴏᴏꜱᴛꜱ ᴛʀᴇʙʟᴇ ᴛᴏ ᴅᴇꜰᴀᴜʟᴛ ʟᴇᴠᴇʟ.
🔻 /treble 0-20 ➠ ꜱᴇᴛꜱ ᴄᴜꜱᴛᴏᴍ ᴛʀᴇʙʟᴇ ʟᴇᴠᴇʟ.
🔻 /autobpm ➠ ᴛᴏɢɢʟᴇꜱ ᴀᴜᴛᴏ ʙᴘᴍ ᴍᴏᴅᴇ (ᴏɴ / ᴏꜰꜰ).
🔻 /dynamiceq ➠ ᴛᴏɢɢʟᴇꜱ ᴅʏɴᴀᴍɪᴄ ᴇQ ᴍᴏᴅᴇ.
🔻 /normal ➠ ʀᴇꜱᴇᴛꜱ ᴇQ ᴛᴏ ꜰʟᴀᴛ ᴍᴏᴅᴇ.
🔻 /bass ➠ ᴇɴᴀʙʟᴇꜱ ʙᴀꜱꜱ ʙᴏᴏꜱᴛ.
🔻 /extreme_bass ➠ ᴇɴᴀʙʟᴇꜱ ᴇxᴛʀᴇᴍᴇ ʙᴀꜱꜱ.
🔻 /vocal ➠ ʙᴏᴏꜱᴛꜱ ᴠᴏᴄᴀʟ ᴄʟᴀʀɪᴛʏ.
🔻 /classical ➠ ᴄʟᴀꜱꜱɪᴄᴀʟ ᴍᴜꜱɪᴄ ᴇQ ᴘʀᴇꜱᴇᴛ.
🔻 /pop ➠ ᴘᴏᴘ ᴍᴜꜱɪᴄ ᴇQ ᴘʀᴇꜱᴇᴛ.
🔻 /rock ➠ ʀᴏᴄᴋ ᴍᴜꜱɪᴄ ᴇQ ᴘʀᴇꜱᴇᴛ.
🔻 /jazz ➠ ᴊᴀᴢᴢ ᴍᴜꜱɪᴄ ᴇQ ᴘʀᴇꜱᴇᴛ.
🔻 /edm ➠ ᴇᴅᴍ ᴍᴜꜱɪᴄ ᴇQ ᴘʀᴇꜱᴇᴛ.
🔻 /party ➠ ʜɪɢʜ ʙᴀꜱꜱ & ᴛʀᴇʙʟᴇ ᴘᴀʀᴛʏ ᴍᴏᴅᴇ.
🔻 /night ➠ ʟᴏᴡ ᴠᴏʟᴜᴍᴇ ɴɪɢʜᴛ ᴍᴏᴅᴇ.
🔻 /soft ➠ ꜱᴏꜰᴛ ᴀᴜᴅɪᴏ ᴇQ.
🔻 /flat ➠ ᴅɪꜱᴀʙʟᴇꜱ ᴀʟʟ ᴇQ ᴇꜰꜰᴇᴄᴛꜱ.
🔻 /triple_bass ➠ ᴜʟᴛʀᴀ ʙᴀꜱꜱ ᴍᴏᴅᴇ.
🔻 /deep_sub ➠ ᴅᴇᴇᴘ ꜱᴜʙ-ʙᴀꜱꜱ ᴇɴʜᴀɴᴄᴇᴍᴇɴᴛ.
🔻 /soft_bass ➠ ʟɪɢʜᴛ ʙᴀꜱꜱ ʙᴏᴏꜱᴛ.
🔻 /bass_clean ➠ ᴄʟᴇᴀɴ ʙᴀꜱꜱ ᴡɪᴛʜ ʟᴏᴡ ɴᴏɪꜱᴇ.
🔻 /clear_voice ➠ ᴄʟᴇᴀʀ ᴠᴏɪᴄᴇ ᴇɴʜᴀɴᴄᴇᴍᴇɴᴛ.
🔻 /dialogue ➠ ᴅɪᴀʟᴏɢᴜᴇ ꜰᴏᴄᴜꜱ ᴍᴏᴅᴇ.
🔻 /karaoke ➠ ᴠᴏᴄᴀʟ ʀᴇᴍᴏᴠᴀʟ (ᴋᴀʀᴀᴏᴋᴇ ᴍᴏᴅᴇ).
🔻 /nightcore ➠ ꜰᴀꜱᴛ & ᴘɪᴛᴄʜᴇᴅ ɴɪɢʜᴛᴄᴏʀᴇ ᴍᴏᴅᴇ.
🔻 /slow_reverb ➠ ꜱʟᴏᴡ ᴀᴜᴅɪᴏ ᴡɪᴛʜ ʀᴇᴠᴇʀʙ.
🔻 /echo ➠ ᴇᴄʜᴏ ᴀᴜᴅɪᴏ ᴇꜰꜰᴇᴄᴛ.
🔻 /reverb ➠ ʀᴇᴠᴇʀʙ ᴀᴜᴅɪᴏ ᴇꜰꜰᴇᴄᴛ.
🔻 /8d ➠ 8ᴅ ꜱᴘᴀᴛɪᴀʟ ᴀᴜᴅɪᴏ ᴇꜰꜰᴇᴄᴛ.
🔻 /chipmunk ➠ ʜɪɢʜ-ᴘɪᴛᴄʜ ᴠᴏɪᴄᴇ ᴇꜰꜰᴇᴄᴛ.
🔻 /deep_voice ➠ ᴅᴇᴇᴘ ᴠᴏɪᴄᴇ ᴇꜰꜰᴇᴄᴛ.
"""
