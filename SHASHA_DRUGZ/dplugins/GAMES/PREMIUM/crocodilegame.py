# ================================================================
#   CROCODILE GAME MODULE  —  SHASHA_DRUGZ  v3.0
#   File: SHASHA_DRUGZ/plugins/GAMES/crocodile.py
#
#   FLOW
#   ────
#   1. /crocodile → "🐊 Wanna be a HOST?" button appears
#   2. Anyone taps it → becomes host, round starts
#   3. Host buttons (popup-only — word never shown in group):
#        👁 Show Word  → alert popup (host only sees word)
#        🔀 Next Word  → new word in popup (host only)
#        ⏭ Skip Round → host / admin
#        🛑 Stop Game  → starter / admin
#   4. All group members type guesses freely — no /join needed
#   5. Correct guess → image card + caption (word, stats, title,
#      earnings, rank) sent to group for the FIRST time
#   6. Host earns EXPLAINER coins every successful round
#
#   TITLE SYSTEM  (based on total coins earned)
#   ─────────────────────────────────────────────
#   Titles are shown on stats page AND leaderboard.
#   Two parallel tracks: Guesser track (coins) + Host track (words_explained)
#   The higher of the two titles is shown.
#
#   HANDLER GROUPS:
#     group=-1  → check_guess (before chatbot/reactionbot)
#     group=0   → /commands (default)
# ================================================================

import asyncio
import os
import random
import re as _re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import get_collection

# ================================================================
# ASSETS
# ================================================================
_TEMPLATE  = "SHASHA_DRUGZ/assets/shasha/fastlywrite.png"
_FONT_PATH = "SHASHA_DRUGZ/assets/Sprintura Demo.otf"
_executor  = ThreadPoolExecutor(max_workers=4)

# ================================================================
# MONGODB
# ================================================================
score_col = get_collection("crocodile_scores")
meta_col  = get_collection("crocodile_meta")

# ================================================================
# TITLE SYSTEM
# ================================================================
# Each entry: (min_coins, title_emoji, title_name)
# Ordered lowest → highest. get_title() picks the last one that fits.
# ─────────────────────────────────────────────────────────────────
#  GUESSER TITLES  (based on total coins)
GUESSER_TITLES = [
    (0,      "🐣",  "ꜰʀᴇsʜ ʙɪʀᴅ"),
    (100,    "🐊",  "ᴄʀᴏᴄᴏ ɴᴇᴡʙɪᴇ"),
    (300,    "🔫",  "sɪʟᴇɴᴛ ᴋɪʟʟᴇʀ"),
    (600,    "🧠",  "ᴡᴏʀᴅ ʜᴜɴᴛᴇʀ"),
    (1000,   "⚡",  "ǫᴜɪᴄᴋ ᴍɪɴᴅ"),
    (2000,   "🎯",  "sʜᴀʀᴘ sʜᴏᴏᴛᴇʀ"),
    (3500,   "🔥",  "ʜᴏᴛ sᴛʀᴇᴀᴋ"),
    (5000,   "💎",  "ᴅɪᴀᴍᴏɴᴅ ɢᴜᴇssᴇʀ"),
    (8000,   "🦁",  "ᴡᴏʀᴅ ʟɪᴏɴ"),
    (12000,  "👑",  "ᴄʀᴏᴄᴏ ᴋɪɴɢ"),
    (18000,  "🌟",  "ʟᴇɢᴇɴᴅ"),
    (25000,  "💫",  "ᴍʏᴛʜɪᴄ"),
    (35000,  "🚀",  "ɢᴀʟᴀxʏ ʙʀᴀɪɴ"),
    (50000,  "🏆",  "ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ"),
]

#  HOST TITLES  (based on words_explained)
HOST_TITLES = [
    (0,    "🎤",  "sʜʏ ᴛᴀʟᴋᴇʀ"),
    (5,    "💬",  "ᴄᴀsᴜᴀʟ ʜɪɴᴛᴇʀ"),
    (15,   "🗣️",  "ᴄʜᴀᴛᴛʏ ʜᴏsᴛ"),
    (30,   "🎭",  "sᴋɪʟʟᴇᴅ ɴᴀʀʀᴀᴛᴏʀ"),
    (50,   "🌊",  "ꜰʟᴜᴇɴᴛ ᴇxᴘʟᴀɪɴᴇʀ"),
    (80,   "⚔️",  "sᴛʀᴀᴛᴇɢɪᴄ ʜᴏsᴛ"),
    (120,  "🎓",  "ᴍᴀsᴛᴇʀ ᴇxᴘʟᴀɪɴᴇʀ"),
    (180,  "🧙",  "ᴡᴏʀᴅ ᴡɪᴢᴀʀᴅ"),
    (260,  "🦅",  "ᴇᴀɢʟᴇ ᴇʏᴇ ʜᴏsᴛ"),
    (360,  "👑",  "ᴄʀᴏᴄᴏ ʜᴏsᴛ ᴋɪɴɢ"),
    (500,  "🌟",  "ʟᴇɢᴇɴᴅᴀʀʏ ʜᴏsᴛ"),
    (700,  "💫",  "ᴍʏᴛʜɪᴄ ɴᴀʀʀᴀᴛᴏʀ"),
    (1000, "🏆",  "ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ ʜᴏsᴛ"),
]


def get_guesser_title(coins: int) -> tuple[str, str]:
    """Return (emoji, title_name) for a given coin total."""
    result = GUESSER_TITLES[0][1], GUESSER_TITLES[0][2]
    for min_c, emoji, name in GUESSER_TITLES:
        if coins >= min_c:
            result = emoji, name
    return result


def get_host_title(words_explained: int) -> tuple[str, str]:
    """Return (emoji, title_name) for words_explained count."""
    result = HOST_TITLES[0][1], HOST_TITLES[0][2]
    for min_w, emoji, name in HOST_TITLES:
        if words_explained >= min_w:
            result = emoji, name
    return result


def get_display_title(coins: int, words_explained: int) -> str:
    """
    Pick the 'better-looking' title to display.
    Grand Master always wins; otherwise whichever track is higher tier.
    """
    ge, gn = get_guesser_title(coins)
    he, hn = get_host_title(words_explained)

    # Determine tier index for each
    g_tier = 0
    for i, (min_c, _, _) in enumerate(GUESSER_TITLES):
        if coins >= min_c:
            g_tier = i
    h_tier = 0
    for i, (min_w, _, _) in enumerate(HOST_TITLES):
        if words_explained >= min_w:
            h_tier = i

    # Normalise tiers (guesser list is longer, scale host tier)
    h_scaled = h_tier * len(GUESSER_TITLES) / max(len(HOST_TITLES), 1)

    if h_scaled >= g_tier:
        return f"{he} {hn}"
    return f"{ge} {gn}"


# ================================================================
# WORD LIST
# ================================================================
WORDS = [
    # animals
    "tiger", "elephant", "penguin", "giraffe", "dolphin", "cheetah", "kangaroo",
    "gorilla", "crocodile", "flamingo", "octopus", "chameleon", "peacock",
    "porcupine", "hedgehog", "parrot", "chimpanzee", "rhinoceros", "hippopotamus",
    "meerkat", "wolverine", "platypus", "narwhal", "axolotl", "capybara",
    # food & drinks
    "pizza", "burger", "sushi", "pancake", "chocolate", "strawberry", "pineapple",
    "avocado", "popcorn", "milkshake", "sandwich", "omelette", "barbecue",
    "dumpling", "burrito", "croissant", "lasagna", "cheesecake", "ramen", "taco",
    "waffle", "pretzel", "tiramisu", "macaron", "churros",
    # technology
    "computer", "smartphone", "keyboard", "internet", "satellite", "microchip",
    "bluetooth", "headphones", "television", "calculator", "microscope",
    "telescope", "robot", "battery", "projector", "hoverboard", "drone",
    "smartwatch", "hologram", "supercomputer",
    # nature
    "volcano", "rainbow", "waterfall", "avalanche", "hurricane", "thunder",
    "glacier", "earthquake", "tornado", "tsunami", "desert", "jungle", "meadow",
    "canyon", "coral", "aurora", "stalactite", "whirlpool", "mangrove", "tundra",
    # sports & games
    "football", "basketball", "badminton", "gymnastics", "skateboard", "parachute",
    "swimming", "archery", "wrestling", "marathon", "karate", "volleyball",
    "cricket", "surfing", "bobsled", "fencing", "curling", "polo", "lacrosse",
    # transport
    "airplane", "helicopter", "spaceship", "motorcycle", "bicycle", "ambulance",
    "hovercraft", "sailboat", "rickshaw", "monorail", "gondola", "bulldozer",
    "tractor", "zeppelin", "catamaran", "hydrofoil", "segway",
    # everyday objects
    "umbrella", "backpack", "compass", "lantern", "blanket", "thermometer",
    "binoculars", "dictionary", "envelope", "scissors", "hourglass", "periscope",
    "boomerang", "hammock", "kaleidoscope", "abacus", "sundial",
    # professions
    "doctor", "architect", "astronaut", "firefighter", "detective", "photographer",
    "chef", "scientist", "journalist", "librarian", "mechanic", "surgeon",
    "carpenter", "locksmith", "taxidermist", "sommelier", "cartographer",
    # places
    "hospital", "library", "museum", "stadium", "lighthouse", "cathedral",
    "marketplace", "laboratory", "observatory", "aquarium", "planetarium",
    "waterpark", "bookstore", "igloo", "skyscraper", "colosseum", "pagoda",
    # actions / concepts
    "dancing", "painting", "singing", "dreaming", "laughing", "cooking",
    "writing", "reading", "climbing", "sleeping", "thinking", "building",
    "exploring", "juggling", "meditating", "skydiving", "hibernating",
]

# ================================================================
# GAME STATE  (in-memory, per chat)
# ================================================================
games: dict[int, dict] = {}

# ================================================================
# REWARDS CONFIG
# ================================================================
BASE_COINS       = 50
FAST_BONUS       = 20      # ≤ 10 s
EXPLAINER_COINS  = 30
EXPLAINER_XP     = 15
GUESSER_XP       = 25
STREAK_THRESHOLD = 3
STREAK_BONUS     = 15

# ================================================================
# IMAGE GENERATOR  (only called on correct guess)
# ================================================================
def _generate_word_image(word: str) -> str | None:
    try:
        img           = Image.open(_TEMPLATE).convert("RGBA")
        width, height = img.size
        draw          = ImageDraw.Draw(img)
        ta_start = int(width * 0.55)
        ta_width = width - ta_start - 50

        font_size = 550
        font = None
        while font_size > 80:
            try:
                font = ImageFont.truetype(_FONT_PATH, font_size)
            except Exception:
                font = ImageFont.load_default()
                break
            bbox = draw.textbbox((0, 0), word.upper(), font=font)
            if (bbox[2] - bbox[0]) < ta_width:
                break
            font_size -= 30
        if font is None:
            font = ImageFont.load_default()

        display = word.upper()
        bbox    = draw.textbbox((0, 0), display, font=font)
        tw, th  = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = ta_start + (ta_width - tw) // 2
        y = (height - th) // 2

        first = display[0]
        rest  = display[1:]
        bf    = draw.textbbox((0, 0), first, font=font)
        fw    = bf[2] - bf[0]
        draw.text((x,      y), first, font=font, fill=(255, 0,   0),   stroke_width=8, stroke_fill=(0, 0, 0))
        draw.text((x + fw, y), rest,  font=font, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))

        footer = "POWERD BY  | @HeartBeat_Offi"
        try:
            ff = ImageFont.truetype(_FONT_PATH, 20)
        except Exception:
            ff = ImageFont.load_default()
        bff = draw.textbbox((0, 0), footer, font=ff)
        fx  = ta_start + (ta_width - (bff[2] - bff[0])) // 2
        fy  = y + th + 40
        draw.text((fx, fy), footer, font=ff, fill=(220, 220, 220))

        path = f"/tmp/croco_{random.randint(10000, 99999)}.png"
        img.save(path)
        return path
    except Exception as e:
        print(f"[crocodile] image gen error: {e}")
        return None


async def _make_image(word: str) -> str | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _generate_word_image, word)


# ================================================================
# DATABASE HELPERS
# ================================================================
def _period_keys() -> dict:
    n = datetime.utcnow()
    return {
        "today":   n.strftime("%Y-%m-%d"),
        "weekly":  f"{n.year}-W{n.isocalendar()[1]:02d}",
        "monthly": n.strftime("%Y-%m"),
    }


async def _add_score(
    chat_id: int, user, role: str,
    coins: int, xp: int, elapsed: float, word: str,
) -> dict:
    """Add score and return the updated document."""
    wpm = round((len(word) / 5) / (elapsed / 60), 2) if elapsed > 0 else 0.0
    now = datetime.utcnow()
    doc = await score_col.find_one({"chat_id": chat_id, "user_id": user.id})
    if not doc:
        new_doc = {
            "chat_id":         chat_id,
            "user_id":         user.id,
            "name":            user.first_name,
            "coins":           coins,
            "xp":              xp,
            "today":           coins,
            "weekly":          coins,
            "monthly":         coins,
            "words_guessed":   1 if role == "guesser"   else 0,
            "words_explained": 1 if role == "explainer" else 0,
            "best_speed":      wpm if role == "guesser" else 0.0,
            "streak":          0,
            "updated":         now,
        }
        await score_col.insert_one(new_doc)
        return new_doc
    else:
        upd = {
            "$inc": {
                "coins": coins, "xp": xp,
                "today": coins, "weekly": coins, "monthly": coins,
            },
            "$set": {"name": user.first_name, "updated": now},
        }
        if role == "guesser":
            upd["$inc"]["words_guessed"] = 1
            if wpm > doc.get("best_speed", 0):
                upd["$set"]["best_speed"] = wpm
        else:
            upd["$inc"]["words_explained"] = 1
        await score_col.update_one({"_id": doc["_id"]}, upd)
        # Return updated values (merge manually for speed)
        updated = dict(doc)
        for k, v in upd["$inc"].items():
            updated[k] = updated.get(k, 0) + v
        updated.update(upd.get("$set", {}))
        return updated


async def _get_rank(chat_id: int, user_id: int) -> int:
    doc = await score_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        return 0
    return await score_col.count_documents(
        {"chat_id": chat_id, "coins": {"$gt": doc.get("coins", 0)}}
    ) + 1


async def _get_top(chat_id: int, field: str) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines, i = [], 0
    async for u in score_col.find({"chat_id": chat_id}).sort(field, -1).limit(10):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        speed = u.get("best_speed", 0.0)
        val   = u.get(field, 0)
        title = get_display_title(u.get("coins", 0), u.get("words_explained", 0))
        lines.append(
            f"{medal} **{u['name']}**  {title}\n"
            f"    💰 {val} ᴄᴏɪɴs  ⚡{speed:.1f} ᴡᴘᴍ"
        )
        i += 1
    return "\n".join(lines) if lines else "ɴᴏ ᴘʟᴀʏᴇʀs ʏᴇᴛ."


async def _reset_daily_weekly_monthly():
    while True:
        try:
            pk    = _period_keys()
            rmeta = await meta_col.find_one({"_id": "reset_meta"}) or {}
            if rmeta.get("day") != pk["today"]:
                await score_col.update_many({}, {"$set": {"today": 0}})
                await meta_col.update_one(
                    {"_id": "reset_meta"}, {"$set": {"day": pk["today"]}}, upsert=True
                )
            if rmeta.get("week") != pk["weekly"]:
                await score_col.update_many({}, {"$set": {"weekly": 0}})
                await meta_col.update_one(
                    {"_id": "reset_meta"}, {"$set": {"week": pk["weekly"]}}, upsert=True
                )
            if rmeta.get("month") != pk["monthly"]:
                await score_col.update_many({}, {"$set": {"monthly": 0}})
                await meta_col.update_one(
                    {"_id": "reset_meta"}, {"$set": {"month": pk["monthly"]}}, upsert=True
                )
        except Exception as e:
            print(f"[crocodile] reset_scores: {e}")
        await asyncio.sleep(3600)


try:
    asyncio.get_event_loop().create_task(_reset_daily_weekly_monthly())
except Exception:
    pass


# ================================================================
# NEXT TITLE PREVIEW HELPER
# ================================================================
def _next_guesser_title(coins: int) -> str | None:
    for min_c, emoji, name in GUESSER_TITLES:
        if coins < min_c:
            return f"{emoji} {name} ᴀᴛ {min_c} ᴄᴏɪɴs"
    return None


def _next_host_title(words_explained: int) -> str | None:
    for min_w, emoji, name in HOST_TITLES:
        if words_explained < min_w:
            return f"{emoji} {name} ᴀᴛ {min_w} ᴡᴏʀᴅs"
    return None


# ================================================================
# INLINE KEYBOARDS
# ================================================================
def _become_host_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🐊 Wanna be a HOST?", callback_data=f"croco_behost_{chat_id}"),
    ]])


def _host_round_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👁 Show Word",  callback_data=f"croco_showword_{chat_id}"),
            InlineKeyboardButton("🔀 Next Word",  callback_data=f"croco_nextword_{chat_id}"),
        ],
        [
            InlineKeyboardButton("⏭ Skip Round", callback_data=f"croco_skip_{chat_id}"),
            InlineKeyboardButton("🛑 Stop Game",  callback_data=f"croco_stop_{chat_id}"),
        ],
    ])


def _top_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 ᴍʏ ʀᴀɴᴋ",  callback_data=f"croco_myrank_{chat_id}"),
            InlineKeyboardButton("🌍 ᴀʟʟ ᴛɪᴍᴇ",  callback_data=f"croco_global_{chat_id}"),
        ],
        [
            InlineKeyboardButton("📅 ᴛᴏᴅᴀʏ",   callback_data=f"croco_today_{chat_id}"),
            InlineKeyboardButton("📆 ᴡᴇᴇᴋʟʏ",  callback_data=f"croco_weekly_{chat_id}"),
            InlineKeyboardButton("🗓 ᴍᴏɴᴛʜʟʏ", callback_data=f"croco_monthly_{chat_id}"),
        ],
    ])


# ================================================================
# ADMIN CHECK
# ================================================================
async def _is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


# ================================================================
# ROUND ENGINE
# ================================================================
async def _round_timer(chat_id: int, word: str, round_num: int):
    ROUND_TIME = 300  # seconds
    await asyncio.sleep(ROUND_TIME)
    game = games.get(chat_id)
    if not game:
        return
    if game.get("word") == word and game.get("round") == round_num:
        game["word"] = None
        try:
            await app.send_message(
                chat_id,
                f"⏭ **ᴛɪᴍᴇ ᴜᴘ!**\n"
                f"ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs  **{word.upper()}**\n\n"
                f"🐊 ɴᴇxᴛ ʀᴏᴜɴᴅ — ᴡʜᴏ ᴡᴀɴᴛs ᴛᴏ ʜᴏsᴛ?",
                reply_markup=_become_host_kb(chat_id),
            )
        except Exception as e:
            print(f"[crocodile] timer msg error: {e}")


def _pick_word() -> str:
    return random.choice(WORDS)


async def _start_round(chat_id: int, host_uid: int, host_mention: str):
    game = games.get(chat_id)
    if not game:
        return

    if game.get("task") and not game["task"].done():
        game["task"].cancel()

    word               = _pick_word()
    game["word"]       = word
    game["host"]       = host_uid
    game["start_time"] = time.time()
    game["round"]      = game.get("round", 0) + 1

    try:
        msg = await app.send_message(
            chat_id,
            f"<blockquote>🐊 **ʀᴏᴜɴᴅ {game['round']} — ʟᴇᴛ's ɢᴏ!**</blockquote>\n"
            f"<blockquote>"
            f"🎤 **ʜᴏsᴛ:** {host_mention}\n"
            f"⏱ **60 sᴇᴄᴏɴᴅs** ᴛᴏ ɢᴜᴇss!\n\n"
            f"👁 ʜᴏsᴛ: ᴛᴀᴘ **Show Word** ᴛᴏ sᴇᴇ ʏᴏᴜʀ sᴇᴄʀᴇᴛ ᴡᴏʀᴅ.\n"
            f"🎤 ᴇxᴘʟᴀɪɴ ᴠɪᴀ ᴠᴄ ᴏʀ ᴛʏᴘᴇ ʜɪɴᴛs (ɴᴏ sᴘᴇʟʟɪɴɢ!).\n"
            f"✍️ ᴇᴠᴇʀʏᴏɴᴇ ᴇʟsᴇ: ᴛʏᴘᴇ ʏᴏᴜʀ ɢᴜᴇss!</blockquote>",
            reply_markup=_host_round_kb(chat_id),
        )
        game["round_msg_id"] = msg.id
    except Exception as e:
        print(f"[crocodile] start_round msg error: {e}")

    task = asyncio.create_task(_round_timer(chat_id, word, game["round"]))
    game["task"] = task


# ================================================================
# COMMANDS
# ================================================================

@Client.on_message(filters.command("crocodile") & filters.group)
async def cmd_crocodile(_, m: Message):
    chat_id = m.chat.id
    if chat_id in games:
        return await m.reply(
            "⚠️ **ɢᴀᴍᴇ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!**\n"
            "ᴜsᴇ /crocodilestop ᴛᴏ ᴇɴᴅ ɪᴛ ꜰɪʀsᴛ."
        )

    games[chat_id] = {
        "host":         None,
        "word":         None,
        "start_time":   time.time(),
        "round":        0,
        "task":         None,
        "round_msg_id": None,
        "streak":       {},
        "started_by":   m.from_user.id,
    }

    await meta_col.update_one(
        {"_id": "chats"}, {"$addToSet": {"ids": chat_id}}, upsert=True
    )

    await m.reply(
        f"<blockquote>🐊 **ᴄʀᴏᴄᴏᴅɪʟᴇ ɢᴀᴍᴇ sᴛᴀʀᴛᴇᴅ!**</blockquote>\n"
        f"<blockquote>"
        f"👤 **sᴛᴀʀᴛᴇᴅ ʙʏ:** {m.from_user.mention}\n\n"
        f"📋 **ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:**\n"
        f"1️⃣ sᴏᴍᴇᴏɴᴇ ᴛᴀᴘs **🐊 Wanna be a HOST?**\n"
        f"2️⃣ ʜᴏsᴛ ᴛᴀᴘs **👁 Show Word** ᴛᴏ sᴇᴇ sᴇᴄʀᴇᴛ ᴡᴏʀᴅ (ᴘʀɪᴠᴀᴛᴇ ᴀʟᴇʀᴛ)\n"
        f"3️⃣ ʜᴏsᴛ ᴇxᴘʟᴀɪɴs ᴠɪᴀ 🎤 ᴠᴄ ᴏʀ ᴛʏᴘᴇs ʜɪɴᴛs\n"
        f"4️⃣ ᴇᴠᴇʀʏᴏɴᴇ ᴛʏᴘᴇs ᴛʜᴇɪʀ ɢᴜᴇss — ɴᴏ /join ɴᴇᴇᴅᴇᴅ!\n"
        f"5️⃣ ꜰɪʀsᴛ ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇss ᴡɪɴs ᴄᴏɪɴs + xᴘ + ᴛɪᴛʟᴇ!\n\n"
        f"👇 ᴛᴀᴘ ʙᴇʟᴏᴡ ᴛᴏ ʙᴇᴄᴏᴍᴇ ᴛʜᴇ ꜰɪʀsᴛ ʜᴏsᴛ:</blockquote>",
        reply_markup=_become_host_kb(chat_id),
    )


@Client.on_message(filters.command("crocodilestop") & filters.group)
async def cmd_stop(_, m: Message):
    chat_id = m.chat.id
    if chat_id not in games:
        return await m.reply("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.")

    uid  = m.from_user.id
    game = games[chat_id]

    if uid != game.get("started_by") and not await _is_admin(chat_id, uid):
        return await m.reply("❌ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ sᴛᴀʀᴛᴇʀ ᴏʀ ᴀɴ ᴀᴅᴍɪɴ ᴄᴀɴ sᴛᴏᴘ.")

    word = game.get("word") or "?"
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    games.pop(chat_id, None)

    await m.reply(
        f"🛑 **ɢᴀᴍᴇ sᴛᴏᴘᴘᴇᴅ!**\n"
        f"🔤 ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: **{word.upper()}**\n"
        f"ᴜsᴇ /crocodile ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ."
    )


@Client.on_message(filters.command("crocodilestats") & filters.group)
async def cmd_stats(_, m: Message):
    chat_id = m.chat.id
    uid     = m.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await m.reply(
            "📊 ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!\nᴜsᴇ /crocodile ᴛᴏ sᴛᴀʀᴛ ᴀ ɢᴀᴍᴇ."
        )

    coins     = data.get("coins", 0)
    xp        = data.get("xp", 0)
    words_exp = data.get("words_explained", 0)
    words_g   = data.get("words_guessed", 0)
    speed     = data.get("best_speed", 0.0)
    rank      = await _get_rank(chat_id, uid)

    # Titles
    ge, gn    = get_guesser_title(coins)
    he, hn    = get_host_title(words_exp)
    display   = get_display_title(coins, words_exp)

    # Next title previews
    next_g = _next_guesser_title(coins)
    next_h = _next_host_title(words_exp)

    next_block = ""
    if next_g:
        next_block += f"\n🎯 ɴᴇxᴛ ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇ: {next_g}"
    if next_h:
        next_block += f"\n🎯 ɴᴇxᴛ ʜᴏsᴛ ᴛɪᴛʟᴇ: {next_h}"

    await m.reply(
        f"<blockquote>📊 **sᴛᴀᴛs** — {m.from_user.mention}</blockquote>\n"
        f"<blockquote>"
        f"{'━'*22}\n"
        f"🏅 **ʀᴀɴᴋ:**             #{rank}\n"
        f"🎖 **ᴛɪᴛʟᴇ:**            {display}\n"
        f"{'━'*22}\n"
        f"💰 **ᴛᴏᴛᴀʟ ᴄᴏɪɴs:**     {coins}\n"
        f"⭐ **ᴛᴏᴛᴀʟ xᴘ:**        {xp}\n"
        f"📅 **ᴛᴏᴅᴀʏ:**            {data.get('today', 0)}\n"
        f"📆 **ᴡᴇᴇᴋʟʏ:**           {data.get('weekly', 0)}\n"
        f"🗓 **ᴍᴏɴᴛʜʟʏ:**          {data.get('monthly', 0)}\n"
        f"{'━'*22}\n"
        f"✅ **ᴡᴏʀᴅs ɢᴜᴇssᴇᴅ:**    {words_g}\n"
        f"🎤 **ᴡᴏʀᴅs ᴇxᴘʟᴀɪɴᴇᴅ:** {words_exp}\n"
        f"⚡ **ʙᴇsᴛ sᴘᴇᴇᴅ:**       {speed:.2f} ᴡᴘᴍ\n"
        f"{'━'*22}\n"
        f"{ge} **ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇ:** {gn}\n"
        f"{he} **ʜᴏsᴛ ᴛɪᴛʟᴇ:**    {hn}"
        f"{next_block}</blockquote>"
    )


@Client.on_message(filters.command("crocodiletop") & filters.group)
async def cmd_top(_, m: Message):
    chat_id = m.chat.id
    top     = await _get_top(chat_id, "coins")
    await m.reply(
        f"<blockquote>🏆 **ᴄʀᴏᴄᴏᴅɪʟᴇ ᴛᴏᴘ 10** — ᴛʜɪs ɢʀᴏᴜᴘ</blockquote>\n"
        f"<blockquote>{top}</blockquote>",
        reply_markup=_top_kb(chat_id),
    )


_RULES_TEXT = (
    "<blockquote>🐊 **ᴄʀᴏᴄᴏᴅɪʟᴇ ɢᴀᴍᴇ ʀᴜʟᴇs**</blockquote>\n"
    "<blockquote>"
    "1️⃣  sᴏᴍᴇᴏɴᴇ ᴠᴏʟᴜɴᴛᴇᴇʀs ᴀs **ʜᴏsᴛ** ʙʏ ᴛᴀᴘᴘɪɴɢ ᴛʜᴇ ʙᴜᴛᴛᴏɴ.\n"
    "2️⃣  ʜᴏsᴛ ᴛᴀᴘs **👁 Show Word** ᴛᴏ sᴇᴇ ᴛʜᴇ sᴇᴄʀᴇᴛ ᴡᴏʀᴅ (ᴘʀɪᴠᴀᴛᴇ ᴀʟᴇʀᴛ).\n"
    "3️⃣  ʜᴏsᴛ ᴇxᴘʟᴀɪɴs ᴠɪᴀ 🎤 ᴠᴄ ᴏʀ ᴛʏᴘᴇs ʜɪɴᴛs.\n"
    "4️⃣  **❌ ᴄᴀɴɴᴏᴛ** sᴀʏ ᴏʀ sᴘᴇʟʟ ᴛʜᴇ ᴡᴏʀᴅ.\n"
    "5️⃣  ᴇᴠᴇʀʏᴏɴᴇ ᴇʟsᴇ ᴊᴜsᴛ ᴛʏᴘᴇs ᴛʜᴇɪʀ ɢᴜᴇss — ɴᴏ /join ɴᴇᴇᴅᴇᴅ.\n"
    "6️⃣  **ꜰɪʀsᴛ ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇss** → ᴡɪɴs ᴄᴏɪɴs + xᴘ + ᴡᴏʀᴅ ɪᴍᴀɢᴇ ꜱᴇɴᴛ ᴛᴏ ɢʀᴏᴜᴘ.\n"
    "7️⃣  **ʜᴏsᴛ** ᴇᴀʀɴs ʙᴏɴᴜs ᴄᴏɪɴs ᴇᴠᴇʀʏ sᴜᴄᴄᴇssꜰᴜʟ ʀᴏᴜɴᴅ.\n"
    "8️⃣  60 sᴇᴄᴏɴᴅs ᴘᴇʀ ʀᴏᴜɴᴅ — ᴀᴜᴛᴏ sᴋɪᴘ ᴀꜰᴛᴇʀ.\n"
    "9️⃣  **🔥 sᴛʀᴇᴀᴋ ʙᴏɴᴜs** ᴇᴠᴇʀʏ 3 ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇssᴇs ɪɴ ᴀ ʀᴏᴡ!\n\n"
    f"💰 ɢᴜᴇssᴇʀ: **{BASE_COINS}** ᴄᴏɪɴs  |  ⚡ ꜰᴀsᴛ (≤10s): +**{FAST_BONUS}**\n"
    f"🎤 ʜᴏsᴛ ʙᴏɴᴜs: **{EXPLAINER_COINS}** ᴄᴏɪɴs  |  🔥 sᴛʀᴇᴀᴋ: +**{STREAK_BONUS}**\n\n"
    "🏅 **ᴛɪᴛʟᴇ sʏsᴛᴇᴍ:**\n"
    "ᴇᴀʀɴ ᴄᴏɪɴs → ᴜɴʟᴏᴄᴋ ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇs\n"
    "ʜᴏsᴛ ᴡᴏʀᴅs → ᴜɴʟᴏᴄᴋ ʜᴏsᴛ ᴛɪᴛʟᴇs\n"
    "🏆 ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ ɪs ᴛʜᴇ ᴜʟᴛɪᴍᴀᴛᴇ ᴛɪᴛʟᴇ!</blockquote>"
)


@Client.on_message(filters.command(["crocodilerules", "crocodilerule"]) & filters.group)
async def cmd_rules(_, m: Message):
    await m.reply(_RULES_TEXT)


@Client.on_message(filters.command("crocodilehelp") & filters.group)
async def cmd_help(_, m: Message):
    # Build title progression display
    g_lines = "\n".join(
        f"  {e} **{n}** — {c} ᴄᴏɪɴs"
        for c, e, n in GUESSER_TITLES
    )
    h_lines = "\n".join(
        f"  {e} **{n}** — {w} ᴡᴏʀᴅs"
        for w, e, n in HOST_TITLES
    )
    await m.reply(
        "<blockquote>🐊 **ᴄʀᴏᴄᴏᴅɪʟᴇ ɢᴀᴍᴇ — ʜᴇʟᴘ**</blockquote>\n"
        "<blockquote>"
        "▶️ **/crocodile** — sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ\n"
        "🛑 **/crocodilestop** — sᴛᴏᴘ ɢᴀᴍᴇ\n"
        "📊 **/crocodilestats** — ʏᴏᴜʀ sᴛᴀᴛs & ᴛɪᴛʟᴇ\n"
        "🏆 **/crocodiletop** — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n"
        "📜 **/crocodilerules** — ɢᴀᴍᴇ ʀᴜʟᴇs\n"
        "❓ **/crocodilehelp** — ᴛʜɪs ᴍᴇɴᴜ</blockquote>\n\n"
        f"<blockquote>🎖 **ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇs** (ʙʏ ᴄᴏɪɴs)\n{g_lines}</blockquote>\n\n"
        f"<blockquote>🎤 **ʜᴏsᴛ ᴛɪᴛʟᴇs** (ʙʏ ᴡᴏʀᴅs ᴇxᴘʟᴀɪɴᴇᴅ)\n{h_lines}</blockquote>"
    )


# ================================================================
# GUESS HANDLER  —  group=-1  (runs before chatbot/reactionbot)
# ================================================================
@Client.on_message(
    filters.incoming
    & filters.text
    & filters.group
    & ~filters.command(
        ["crocodile", "crocodilestop", "crocodilerules", "crocodilerule",
         "crocodilestats", "crocodiletop", "crocodilehelp"]
    )
    & ~filters.via_bot,
    group=-1,
)
async def check_guess(_, m: Message):
    chat_id = m.chat.id

    if chat_id not in games:
        m.continue_propagation()
        return

    game = games[chat_id]
    word = game.get("word")

    if not word:
        m.continue_propagation()
        return

    # Host cannot guess their own word
    if m.from_user and m.from_user.id == game.get("host"):
        m.continue_propagation()
        return

    typed = (m.text or "").strip().lower()
    if typed != word.lower():
        m.continue_propagation()
        return

    # ── CORRECT GUESS ─────────────────────────────────────────────
    elapsed = time.time() - game["start_time"]
    uid     = m.from_user.id

    # Cancel timer and immediately mark as between rounds
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    game["word"] = None

    # Coin + XP calculation
    coins       = BASE_COINS
    xp          = GUESSER_XP
    bonus_lines = []

    if elapsed <= 10:
        coins += FAST_BONUS
        bonus_lines.append(f"⚡ ꜰᴀsᴛ ʙᴏɴᴜs: +**{FAST_BONUS}** ᴄᴏɪɴs")

    streak = game["streak"]
    streak[uid] = streak.get(uid, 0) + 1
    if streak[uid] % STREAK_THRESHOLD == 0:
        coins += STREAK_BONUS
        bonus_lines.append(f"🔥 sᴛʀᴇᴀᴋ x**{streak[uid]}**: +**{STREAK_BONUS}** ᴄᴏɪɴs")

    wpm        = round((len(word) / 5) / (elapsed / 60), 2) if elapsed > 0 else 0.0
    mins, secs = divmod(int(elapsed), 60)

    # Save guesser score and get updated doc
    updated_doc = await _add_score(chat_id, m.from_user, "guesser", coins, xp, elapsed, word)

    # Rank & title after earning
    rank           = await _get_rank(chat_id, uid)
    new_coins      = updated_doc.get("coins", coins)
    new_words_g    = updated_doc.get("words_guessed", 1)
    new_words_exp  = updated_doc.get("words_explained", 0)
    display_title  = get_display_title(new_coins, new_words_exp)
    ge, gn         = get_guesser_title(new_coins)

    # Check for title upgrade
    old_coins  = new_coins - coins
    old_ge, _  = get_guesser_title(old_coins)
    title_upgraded = old_ge != ge

    # Reward host
    host_uid     = game.get("host")
    host_mention = ""
    host_title   = ""
    if host_uid and host_uid != uid:
        try:
            host_user      = await app.get_users(host_uid)
            host_mention   = host_user.mention
            host_doc       = await _add_score(
                chat_id, host_user, "explainer",
                EXPLAINER_COINS, EXPLAINER_XP, elapsed, word,
            )
            h_words_exp    = host_doc.get("words_explained", 1)
            h_coins        = host_doc.get("coins", EXPLAINER_COINS)
            host_title     = get_display_title(h_coins, h_words_exp)
        except Exception as e:
            print(f"[crocodile] host reward error: {e}")

    # Build caption
    bonus_block = ("\n" + "\n".join(bonus_lines)) if bonus_lines else ""
    host_line   = (
        f"\n\n🎤 **ʜᴏsᴛ:** {host_mention}  {host_title}\n"
        f"   +**{EXPLAINER_COINS}** ᴄᴏɪɴs  ⭐ +**{EXPLAINER_XP}** xᴘ"
        if host_mention else ""
    )
    title_line = f"\n🎖 **ᴛɪᴛʟᴇ ᴜᴘɢʀᴀᴅᴇ!**  {ge} {gn} 🎉" if title_upgraded else f"\n🎖 {display_title}"

    caption = (
        f"<blockquote>🎉 **ᴄᴏʀʀᴇᴄᴛ!**  {m.from_user.mention}</blockquote>\n"
        f"<blockquote>"
        f"🔤 **ᴡᴏʀᴅ:**   {word.upper()}\n"
        f"⏱ **ᴛɪᴍᴇ:**   {mins}ᴍ {secs}s\n"
        f"⚡ **sᴘᴇᴇᴅ:** {wpm:.2f} ᴡᴘᴍ\n"
        f"🏅 **ʀᴀɴᴋ:**   #{rank}\n"
        f"💰 +**{coins}** ᴄᴏɪɴs  ⭐ +**{xp}** xᴘ"
        f"{bonus_block}"
        f"{title_line}"
        f"{host_line}</blockquote>"
    )

    # Generate and send word image (ONLY at this moment — correct guess)
    img_path = await _make_image(word)
    try:
        if img_path and os.path.exists(img_path):
            await m.reply_photo(img_path, caption=caption)
        else:
            await m.reply(caption)
    except Exception as e:
        print(f"[crocodile] send win photo error: {e}")
        try:
            await m.reply(caption)
        except Exception:
            pass
    finally:
        if img_path:
            try:
                os.remove(img_path)
            except Exception:
                pass

    # Post next-host button
    await asyncio.sleep(4)
    if chat_id in games:
        try:
            await app.send_message(
                chat_id,
                f"🐊 ʀᴏᴜɴᴅ **{game['round']}** ᴅᴏɴᴇ!\n"
                f"ᴡʜᴏ ᴡᴀɴᴛs ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ʜᴏsᴛ?",
                reply_markup=_become_host_kb(chat_id),
            )
        except Exception as e:
            print(f"[crocodile] next host btn error: {e}")


# ================================================================
# CALLBACK QUERIES
# ================================================================

@Client.on_callback_query(filters.regex(r"^croco_behost_(-?\d+)$"))
async def cb_be_host(_, q):
    chat_id = int(q.data.split("_")[2])
    if chat_id not in games:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    game = games[chat_id]
    if game.get("word"):
        return await q.answer("⚠️ ᴀ ʀᴏᴜɴᴅ ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇss!", show_alert=True)

    uid     = q.from_user.id
    mention = q.from_user.mention

    # Show host title in ack
    data = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    he, hn = get_host_title(data.get("words_explained", 0) if data else 0)
    await q.answer(f"✅ ʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴛʜᴇ ʜᴏsᴛ! {he}", show_alert=False)

    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _start_round(chat_id, uid, mention)


@Client.on_callback_query(filters.regex(r"^croco_showword_(-?\d+)$"))
async def cb_show_word(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)

    if not game or not game.get("word"):
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴏᴜɴᴅ.", show_alert=True)
    if q.from_user.id != game.get("host"):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ʜᴏsᴛ ᴄᴀɴ sᴇᴇ ᴛʜᴇ ᴡᴏʀᴅ.", show_alert=True)

    await q.answer(
        f"🔤 ʏᴏᴜʀ ᴡᴏʀᴅ:\n\n{game['word'].upper()}\n\n"
        f"❌ ᴅᴏɴ'ᴛ sᴘᴇʟʟ ɪᴛ!\n✅ ᴇxᴘʟᴀɪɴ ᴠɪᴀ ᴠᴄ ᴏʀ ʜɪɴᴛs.",
        show_alert=True,
    )


@Client.on_callback_query(filters.regex(r"^croco_nextword_(-?\d+)$"))
async def cb_next_word(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)

    if not game or not game.get("word"):
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴏᴜɴᴅ.", show_alert=True)
    if q.from_user.id != game.get("host"):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ʜᴏsᴛ ᴄᴀɴ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴡᴏʀᴅ.", show_alert=True)

    new_word           = _pick_word()
    game["word"]       = new_word
    game["start_time"] = time.time()

    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    task = asyncio.create_task(_round_timer(chat_id, new_word, game["round"]))
    game["task"] = task

    await q.answer(
        f"🔀 ɴᴇᴡ ᴡᴏʀᴅ:\n\n{new_word.upper()}\n\n"
        f"❌ ᴅᴏɴ'ᴛ sᴘᴇʟʟ ɪᴛ!\n✅ ᴇxᴘʟᴀɪɴ ᴠɪᴀ ᴠᴄ ᴏʀ ʜɪɴᴛs.",
        show_alert=True,
    )


@Client.on_callback_query(filters.regex(r"^croco_skip_(-?\d+)$"))
async def cb_skip(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)

    if not game:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)

    uid = q.from_user.id
    if uid != game.get("host") and not await _is_admin(chat_id, uid):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ʜᴏsᴛ ᴏʀ ᴀɴ ᴀᴅᴍɪɴ ᴄᴀɴ sᴋɪᴘ.", show_alert=True)

    word = game.get("word", "?")
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    game["word"] = None

    await q.answer("⏭ ʀᴏᴜɴᴅ sᴋɪᴘᴘᴇᴅ!")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await app.send_message(
            chat_id,
            f"⏭ **sᴋɪᴘᴘᴇᴅ!**  ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs **{word.upper()}**\n\n"
            f"🐊 ᴡʜᴏ ᴡᴀɴᴛs ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ʜᴏsᴛ?",
            reply_markup=_become_host_kb(chat_id),
        )
    except Exception as e:
        print(f"[crocodile] skip msg error: {e}")


@Client.on_callback_query(filters.regex(r"^croco_stop_(-?\d+)$"))
async def cb_stop(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)

    if not game:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)

    uid = q.from_user.id
    if uid != game.get("started_by") and not await _is_admin(chat_id, uid):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ sᴛᴀʀᴛᴇʀ ᴏʀ ᴀɴ ᴀᴅᴍɪɴ ᴄᴀɴ sᴛᴏᴘ.", show_alert=True)

    word = game.get("word", "?")
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    games.pop(chat_id, None)

    await q.answer("🛑 ɢᴀᴍᴇ sᴛᴏᴘᴘᴇᴅ!")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await app.send_message(
            chat_id,
            f"🛑 **ɢᴀᴍᴇ sᴛᴏᴘᴘᴇᴅ ʙʏ** {q.from_user.mention}\n"
            f"🔤 ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: **{word.upper()}**\n\n"
            f"ᴜsᴇ /crocodile ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ!"
        )
    except Exception as e:
        print(f"[crocodile] stop msg error: {e}")


@Client.on_callback_query(filters.regex(r"^croco_(global|today|weekly|monthly)_(-?\d+)$"))
async def cb_leaderboard(_, q):
    m2      = _re.match(r"^croco_(global|today|weekly|monthly)_(-?\d+)$", q.data)
    mode    = m2.group(1)
    chat_id = int(m2.group(2))
    FIELD_MAP = {
        "global":  ("coins",   "🌍 **ᴀʟʟ-ᴛɪᴍᴇ ᴛᴏᴘ 10**"),
        "today":   ("today",   "📅 **ᴛᴏᴅᴀʏ's ᴛᴏᴘ 10**"),
        "weekly":  ("weekly",  "📆 **ᴡᴇᴇᴋʟʏ ᴛᴏᴘ 10**"),
        "monthly": ("monthly", "🗓 **ᴍᴏɴᴛʜʟʏ ᴛᴏᴘ 10**"),
    }
    field, title = FIELD_MAP[mode]
    top          = await _get_top(chat_id, field)
    await q.answer()
    try:
        await q.message.edit_text(
            f"<blockquote>{title}</blockquote>\n<blockquote>{top}</blockquote>",
            reply_markup=_top_kb(chat_id),
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^croco_myrank_(-?\d+)$"))
async def cb_myrank(_, q):
    chat_id = int(q.data.split("_")[2])
    uid     = q.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await q.answer("ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!", show_alert=True)

    coins     = data.get("coins", 0)
    words_exp = data.get("words_explained", 0)
    rank      = await _get_rank(chat_id, uid)
    display   = get_display_title(coins, words_exp)
    ge, gn    = get_guesser_title(coins)
    he, hn    = get_host_title(words_exp)
    speed     = data.get("best_speed", 0.0)

    next_g = _next_guesser_title(coins)
    next_h = _next_host_title(words_exp)
    next_block = ""
    if next_g:
        next_block += f"\n🎯 ɴᴇxᴛ ɢ: {next_g}"
    if next_h:
        next_block += f"\n🎯 ɴᴇxᴛ ʜ: {next_h}"

    await q.answer()
    try:
        await q.message.edit_text(
            f"<blockquote>📊 **ᴍʏ sᴛᴀᴛs** — {q.from_user.mention}</blockquote>\n"
            f"<blockquote>"
            f"🏅 **ʀᴀɴᴋ:**   #{rank}\n"
            f"🎖 **ᴛɪᴛʟᴇ:**  {display}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 **ᴄᴏɪɴs:**  {coins}\n"
            f"⭐ **xᴘ:**     {data.get('xp', 0)}\n"
            f"📅 **ᴛᴏᴅᴀʏ:** {data.get('today', 0)}\n"
            f"📆 **ᴡᴇᴇᴋ:**  {data.get('weekly', 0)}\n"
            f"🗓 **ᴍᴏɴᴛʜ:** {data.get('monthly', 0)}\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ **ɢᴜᴇssᴇᴅ:**   {data.get('words_guessed', 0)}\n"
            f"🎤 **ʜᴏsᴛᴇᴅ:**    {words_exp}\n"
            f"⚡ **sᴘᴇᴇᴅ:**     {speed:.2f} ᴡᴘᴍ\n"
            f"━━━━━━━━━━━━━━\n"
            f"{ge} **{gn}**\n"
            f"{he} **{hn}**"
            f"{next_block}</blockquote>",
            reply_markup=_top_kb(chat_id),
        )
    except Exception:
        pass


# ================================================================
# MODULE META
# ================================================================
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_82"
__help__     = """
🔻 /crocodile ➠ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴄʀᴏᴄᴏᴅɪʟᴇ ɢᴀᴍᴇ
🔻 /crocodilestop ➠ sᴛᴏᴘ ɢᴀᴍᴇ (sᴛᴀʀᴛᴇʀ / ᴀᴅᴍɪɴ)
🔻 /crocodilestats ➠ ʏᴏᴜʀ sᴛᴀᴛs + ᴛɪᴛʟᴇ
🔻 /crocodiletop ➠ ɢʀᴏᴜᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ ᴡɪᴛʜ ᴛɪᴛʟᴇs
🔻 /crocodilerules ➠ ɢᴀᴍᴇ ʀᴜʟᴇs
🔻 /crocodilehelp ➠ ꜰᴜʟʟ ʜᴇʟᴘ + ᴛɪᴛʟᴇ ᴘʀᴏɢʀᴇssɪᴏɴ
"""

MOD_TYPE = "GAMES"
MOD_NAME = "Cricket-Game"
MOD_PRICE = "350"
