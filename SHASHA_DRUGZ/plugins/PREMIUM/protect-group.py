# protect-group.py
# ╔══════════════════════════════════════════════════════════════════╗
# ║  BLOCKWORD MODULE — Pyrogram + MongoDB                          ║
# ╚══════════════════════════════════════════════════════════════════╝
import re
import asyncio
import traceback
import unicodedata
from datetime import datetime, timedelta
from SHASHA_DRUGZ import app
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
from pyrogram.handlers import MessageHandler, EditedMessageHandler
from pyrogram.types import (
    Message, CallbackQuery, ChatPermissions,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB_URI, ADMINS_ID

#print("BW] ✅ protect-group.py LOADED — blockword module active")

# ── Mongo ──────────────────────────────────────────────────────────
_mongo          = AsyncIOMotorClient(MONGO_DB_URI)
_db             = _mongo["BLOCKWORD_DB"]
settings_col    = _db["bw_settings"]
group_words_col = _db["bw_group_words"]
owner_words_col = _db["bw_owner_words"]
warns_col       = _db["bw_warns"]

# ══════════════════════════════════════════════════════════════════
# NORMALISATION  (used only for custom /addword words)
# ══════════════════════════════════════════════════════════════════
_LEET = {
    "0":"o","1":"i","3":"e","4":"a","5":"s",
    "6":"g","7":"t","8":"b","@":"a","$":"s",
    "!":"i","+":"t","(":"c",")":"o",
}
_ZW  = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")
_SEP = re.compile(r"[\s.\-_,|\\/*]+")

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    text = _ZW.sub("", text)
    text = "".join(_LEET.get(c, c) for c in text)
    text = _SEP.sub("", text)
    return text

# ══════════════════════════════════════════════════════════════════
# REGEX PATTERN LIST — compiled once at startup
# ══════════════════════════════════════════════════════════════════
_RAW_PATTERNS = [
    # ── Drugs ──────────────────────────────────────────────────────
    r"\bcocain[e]?\b", r"\bcoke\b", r"\bheroin\b", r"\bmeth\b",
    r"\bcrack\b", r"\bweed\b", r"\bganja\b", r"\bopium\b",
    r"\bfentanyl\b", r"\bmdma\b", r"\becstasy\b", r"\blsd\b",
    r"\bkratom\b", r"\bsmack\b", r"\bdrugz?\b", r"\bsnort\b",
    r"\bspice\b", r"\bshrooms?\b", r"\bpcp\b", r"\bxanax\b",
    r"\boxy(contin)?\b", r"\bpercocet\b", r"\bdealin[g]?\b",
    # ── Weapons ────────────────────────────────────────────────────
    r"\bgunz?\b", r"\bpistol\b", r"\brifle\b", r"\bak-?47\b",
    r"\bbomb\b", r"\bgrenade\b", r"\bexplosives?\b",
    r"\bammo\b", r"\bbullets?\b", r"\bweapons?\b", r"\bknife\b",
    r"\bmachete\b", r"\bshotgun\b", r"\bsemiauto\b", r"\bsilencer\b",
    # ── Pornography ────────────────────────────────────────────────
    r"\bpornz?\b", r"\bpornhub\b", r"\bxvideos\b", r"\bxnxx\b",
    r"\bnudez?\b", r"\bnudes\b", r"\bsex\b", r"\bsexual\b",
    r"\bonlyfans\b", r"\bcamgirl\b", r"\bstrip(per)?\b",
    r"\bf+u+c+k+\b", r"\bfuk\b", r"\bfuq\b", r"\bfck\b",
    r"\bpornstar\b", r"\bbooty\b", r"\bboobs?\b",
    # ── Terrorism / Extremism ──────────────────────────────────────
    r"\bisis\b", r"\bisil\b", r"\bal[\s\-]?qaeda\b",
    r"\bterror(ist)?\b", r"\bjihad\b", r"\bsuicide[\s\-]?bomb\b",
    r"\bbeheading\b", r"\bextremis[tm]\b", r"\bradicali[sz]\b",
    # ── Violence / Threats ─────────────────────────────────────────
    r"\bkill\s+you\b", r"\bi[\s]?will[\s]?kill\b", r"\bmurder\b",
    r"\bstab\b", r"\bshoot\s+you\b", r"\bthreat(en)?\b",
    r"\brapist?\b", r"\brake\b",
    # ── Child Safety ───────────────────────────────────────────────
    r"\bpedophil[e]?\b", r"\bpedophilia\b", r"\bchild[\s\-]?porn\b",
    r"\bminor[\s\-]?sex\b", r"\blolita\b", r"\bcsam\b",
    # ── English Profanity ──────────────────────────────────────────
    r"\bshit\b", r"\bass(hole)?\b", r"\bbitch\b", r"\bcunt\b",
    r"\bdick\b", r"\bpussy\b", r"\bwhore\b", r"\bslut\b",
    r"\bbastard\b", r"\bdamn\b", r"\bcrap\b", r"\bprick\b",
    r"\bdouche\b", r"\bjerkoff\b", r"\bwanker\b",
    # ── Tamil ──────────────────────────────────────────────────────
    r"\bthevdiya\b", r"\bpundai\b", r"\bootha\b", r"\bsootha\b",
    r"\bkuthi\b", r"\bmyre\b", r"\bnaaye?\b", r"\bkazhuthai\b",
    r"\bnaayi\b", r"\bthayoli\b", r"\bpottai\b", r"\bkundi\b",
    r"\bsullu\b", r"\bsunni\b", r"\bnool\b",
    r"\bthambi[\s\-]?otha\b",
    # ── Hindi ──────────────────────────────────────────────────────
    r"\bchutiya\b", r"\bbehenchod\b", r"\bmadarchod\b",
    r"\bgandu\b", r"\blauda\b", r"\brandi\b", r"\bsaala\b",
    r"\bharamzada\b", r"\bharami\b", r"\bbhosad\b", r"\bchod\b",
    r"\bbhenchod\b", r"\bmaa[\s]?ki\b", r"\bbehen[\s]?ke\b", r"\bgaand\b",
]
_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE | re.UNICODE), p)
    for p in _RAW_PATTERNS
]

def _check_words(raw: str):
    for pattern, label in _COMPILED:
        m = pattern.search(raw)
        if m:
            #print(f"[BW] REGEX HIT: pattern='{label}' matched='{m.group()}' in '{raw[:80]}'")
            return m.group()
    return None

def _check_custom(raw: str, wordlist: list):
    n = _norm(raw)
    for w in wordlist:
        nw = _norm(w)
        if nw and nw in n:
            #print(f"[BW] CUSTOM HIT: '{nw}' in '{n[:80]}'")
            return w
    return None

# ══════════════════════════════════════════════════════════════════
# DB HELPERS
# ══════════════════════════════════════════════════════════════════
async def _get_settings(cid: int) -> dict:
    d = await settings_col.find_one({"chat_id": cid})
    if not d:
        # FIX 1: Default enabled=True for ALL new groups
        return {"enabled": True, "warn_limit": 3, "action": "mute"}
    return {
        "enabled":    d.get("enabled",    True),
        "warn_limit": d.get("warn_limit", 3),
        "action":     d.get("action",     "mute"),
    }

async def _set(cid: int, key: str, val):
    await settings_col.update_one({"chat_id": cid}, {"$set": {key: val}}, upsert=True)

async def _group_words(cid: int) -> list:
    d = await group_words_col.find_one({"chat_id": cid})
    return d.get("words", []) if d else []

async def _save_group_words(cid: int, words: list):
    await group_words_col.update_one({"chat_id": cid}, {"$set": {"words": words}}, upsert=True)

async def _owner_words() -> list:
    d = await owner_words_col.find_one({"_id": "global"})
    return d.get("words", []) if d else []

async def _save_owner_words(words: list):
    await owner_words_col.update_one({"_id": "global"}, {"$set": {"words": words}}, upsert=True)

# FIX 3: All warn data is stored in MongoDB — survives bot restarts
async def _add_warn(cid: int, uid: int) -> int:
    await warns_col.update_one(
        {"chat_id": cid, "user_id": uid}, {"$inc": {"count": 1}}, upsert=True
    )
    d = await warns_col.find_one({"chat_id": cid, "user_id": uid})
    return d["count"]

async def _reset_warn(cid: int, uid: int):
    await warns_col.delete_one({"chat_id": cid, "user_id": uid})

async def _get_warn_count(cid: int, uid: int) -> int:
    d = await warns_col.find_one({"chat_id": cid, "user_id": uid})
    return d["count"] if d else 0

# ══════════════════════════════════════════════════════════════════
# MUTE STATE HELPERS (stored in DB for persistence)
# ══════════════════════════════════════════════════════════════════
mute_state_col = _db["bw_mute_states"]

async def _is_muted(cid: int, uid: int) -> bool:
    d = await mute_state_col.find_one({"chat_id": cid, "user_id": uid})
    return bool(d.get("muted", False)) if d else False

async def _set_muted(cid: int, uid: int, muted: bool):
    await mute_state_col.update_one(
        {"chat_id": cid, "user_id": uid}, {"$set": {"muted": muted}}, upsert=True
    )

ban_state_col = _db["bw_ban_states"]

async def _is_banned(cid: int, uid: int) -> bool:
    d = await ban_state_col.find_one({"chat_id": cid, "user_id": uid})
    return bool(d.get("banned", False)) if d else False

async def _set_banned(cid: int, uid: int, banned: bool):
    await ban_state_col.update_one(
        {"chat_id": cid, "user_id": uid}, {"$set": {"banned": banned}}, upsert=True
    )

# ══════════════════════════════════════════════════════════════════
# PERMISSION HELPERS
# ══════════════════════════════════════════════════════════════════
async def _is_admin(client: Client, cid: int, uid: int) -> bool:
    if uid in ADMINS_ID:
        return True
    try:
        m = await client.get_chat_member(cid, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception as e:
        print(f"[BW] _is_admin error uid={uid}: {e}")
        return False

async def _is_owner(client: Client, cid: int, uid: int) -> bool:
    if uid in ADMINS_ID:
        return True
    try:
        m = await client.get_chat_member(cid, uid)
        return m.status == ChatMemberStatus.OWNER
    except Exception as e:
        print(f"[BW] _is_owner error uid={uid}: {e}")
        return False

async def _group_owner(client: Client, cid: int):
    try:
        async for m in client.get_chat_members(cid, filter=ChatMembersFilter.ADMINISTRATORS):
            if m.status == ChatMemberStatus.OWNER:
                return m
    except Exception as e:
        print(f"[BW] _group_owner error: {e}")
    return None

async def _admin_mentions(client: Client, cid: int) -> str:
    tags = []
    try:
        async for m in client.get_chat_members(cid, filter=ChatMembersFilter.ADMINISTRATORS):
            if m.user and not m.user.is_bot:
                tags.append(m.user.mention)
    except Exception as e:
        print(f"[BW] _admin_mentions error: {e}")
    return " ".join(tags) if tags else "_(no admins)_"

# ══════════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════════
def _kb_dashboard(enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🛡 Status: {'✅ ON' if enabled else '❌ OFF'}", callback_data="bw_status_info"
        )],
        [
            InlineKeyboardButton("🔴 Disable" if enabled else "🟢 Enable", callback_data="bw_toggle"),
            InlineKeyboardButton("📋 Word List", callback_data="bw_listwords"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="bw_settings_menu"),
            InlineKeyboardButton("❓ Help",      callback_data="bw_help"),
        ],
    ])

def _kb_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Warn Limit", callback_data="bw_set_warnlimit"),
            InlineKeyboardButton("🔨 Punishment",  callback_data="bw_set_punishment"),
        ],
        [InlineKeyboardButton("« Back", callback_data="bw_main")],
    ])

def _kb_punish() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔇 Mute", callback_data="bw_action_mute"),
            InlineKeyboardButton("🚫 Ban",  callback_data="bw_action_ban"),
            InlineKeyboardButton("👢 Kick", callback_data="bw_action_kick"),
        ],
        [InlineKeyboardButton("« Back", callback_data="bw_settings_menu")],
    ])

def _kb_back(cb="bw_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=cb)]])

def _kb_words() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Refresh", callback_data="bw_listwords"),
        InlineKeyboardButton("« Back",     callback_data="bw_main"),
    ]])

# FIX 2: Warn message keyboard — Mute/Unmute toggle, Ban/Unban toggle, Kick
def _kb_warn_actions(cid: int, uid: int, muted: bool = False, banned: bool = False) -> InlineKeyboardMarkup:
    mute_label = "🔊 Unmute" if muted else "🔇 Mute"
    mute_cb    = f"bw_unmute_{cid}_{uid}" if muted else f"bw_mute_{cid}_{uid}"
    ban_label  = "✅ Unban" if banned else "🚫 Ban"
    ban_cb     = f"bw_unban_{cid}_{uid}" if banned else f"bw_ban_{cid}_{uid}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(mute_label,  callback_data=mute_cb),
            InlineKeyboardButton(ban_label,   callback_data=ban_cb),
            InlineKeyboardButton("👢 Kick",   callback_data=f"bw_kick_{cid}_{uid}"),
        ],
        [
            InlineKeyboardButton("📋 Word List", callback_data="bw_listwords"),
            InlineKeyboardButton("⚙️ Settings",  callback_data="bw_settings_menu"),
        ],
    ])

# ══════════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════════
@app.on_message(filters.command("blockword") & filters.group)
async def cmd_blockword(client: Client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")
    s    = await _get_settings(message.chat.id)
    args = message.command[1:]
    if args and args[0].lower() in ("on", "off"):
        en = args[0].lower() == "on"
        await _set(message.chat.id, "enabled", en)
        return await message.reply(
            "✅ BlockWord **enabled**." if en else "❌ BlockWord **disabled**.",
            reply_markup=_kb_dashboard(en),
        )
    en = s["enabled"]
    await message.reply(
        f"🛡 **BlockWord Dashboard**\n\n"
        f"Status     : {'✅ Active' if en else '❌ Inactive'}\n"
        f"Warn Limit : `{s['warn_limit']}`\n"
        f"Punishment : `{s['action'].title()}`",
        reply_markup=_kb_dashboard(en),
    )

@app.on_message(filters.command("addword") & filters.group)
async def cmd_addword(client: Client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")
    if len(message.command) < 2:
        return await message.reply("**Usage:** `/addword <word>`")
    word  = _norm(message.text.split(None, 1)[1].strip())
    words = await _group_words(message.chat.id)
    if word in words:
        return await message.reply(f"⚠️ `{word}` already in blocklist.")
    words.append(word)
    await _save_group_words(message.chat.id, words)
    await message.reply(f"✅ `{word}` added to this group's blocklist.")

@app.on_message(filters.command("removeword") & filters.group)
async def cmd_removeword(client: Client, message: Message):
    if not await _is_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Group owner only.")
    if len(message.command) < 2:
        return await message.reply("**Usage:** `/removeword <word>`")
    word  = _norm(message.text.split(None, 1)[1].strip())
    words = await _group_words(message.chat.id)
    if word not in words:
        return await message.reply(f"⚠️ `{word}` not found.")
    words.remove(word)
    await _save_group_words(message.chat.id, words)
    await message.reply(f"🗑 `{word}` removed.")

@app.on_message(filters.command("blockwords") & filters.group)
async def cmd_blockwords(client: Client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")
    gw  = await _group_words(message.chat.id)
    ow  = await _owner_words()
    txt = "📋 **Blocked Words**\n\n"
    txt += ("**📌 Group:**\n" + "\n".join(f"  • `{w}`" for w in gw) + "\n\n") if gw else "**📌 Group:** _None_\n\n"
    txt += ("**🌍 Global:**\n" + "\n".join(f"  • `{w}`" for w in ow)) if ow else "**🌍 Global:** _None_"
    await message.reply(txt, reply_markup=_kb_words())

@app.on_message(filters.command("ownerblockword"))
async def cmd_ownerblockword(client: Client, message: Message):
    if message.from_user.id not in ADMINS_ID:
        return await message.reply("❌ Bot owner only.")
    if len(message.command) < 2:
        return await message.reply("**Usage:** `/ownerblockword <word>`")
    word  = _norm(message.text.split(None, 1)[1].strip())
    words = await _owner_words()
    if word in words:
        return await message.reply(f"⚠️ `{word}` already global.")
    words.append(word)
    await _save_owner_words(words)
    await message.reply(f"🌍 `{word}` added globally.")

@app.on_message(filters.command("ownerrmword"))
async def cmd_ownerrmword(client: Client, message: Message):
    if message.from_user.id not in ADMINS_ID:
        return await message.reply("❌ Bot owner only.")
    if len(message.command) < 2:
        return await message.reply("**Usage:** `/ownerrmword <word>`")
    word  = _norm(message.text.split(None, 1)[1].strip())
    words = await _owner_words()
    if word not in words:
        return await message.reply(f"⚠️ `{word}` not found.")
    words.remove(word)
    await _save_owner_words(words)
    await message.reply(f"🗑 `{word}` removed globally.")

@app.on_message(filters.command("rmallwords"))
async def cmd_rmallwords(client: Client, message: Message):
    if message.from_user.id not in ADMINS_ID:
        return await message.reply("❌ Bot owner only.")
    await _save_owner_words([])
    await message.reply("🧹 All global words cleared.")

@app.on_message(filters.command("setwarnlimit") & filters.group)
async def cmd_setwarnlimit(client: Client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("**Usage:** `/setwarnlimit <n>`")
    n = int(message.command[1])
    if n < 1:
        return await message.reply("⚠️ Must be ≥ 1.")
    await _set(message.chat.id, "warn_limit", n)
    await message.reply(f"✅ Warn limit → **{n}**.")

@app.on_message(filters.command("setpunishment") & filters.group)
async def cmd_setpunishment(client: Client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")
    if len(message.command) < 2 or message.command[1].lower() not in ("mute", "ban", "kick"):
        return await message.reply("Choose:", reply_markup=_kb_punish())
    a = message.command[1].lower()
    await _set(message.chat.id, "action", a)
    await message.reply(f"✅ Punishment → **{a.title()}**.")

@app.on_message(filters.command("bwtest") & filters.group)
async def cmd_bwtest(client: Client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return
    if len(message.command) < 2:
        return await message.reply("Usage: `/bwtest <word>`")
    test = message.text.split(None, 1)[1].strip()
    hit  = _check_words(test)
    if not hit:
        hit = _check_custom(test, await _owner_words())
    if not hit:
        hit = _check_custom(test, await _group_words(message.chat.id))
    await message.reply(
        f"🔬 **Detection Test**\n\n"
        f"Input  : `{test}`\n"
        f"Norm   : `{_norm(test)}`\n"
        f"Result : `{'✅ HIT → ' + hit if hit else '❌ NO MATCH'}`"
    )

# ══════════════════════════════════════════════════════════════════
# CORE ENFORCEMENT LOGIC
# ══════════════════════════════════════════════════════════════════
async def _enforce(client: Client, message: Message):
    try:
        # Must be a group message
        if not message.chat or message.chat.id >= 0:
            return
        raw = message.text or message.caption or ""
        if not raw.strip():
            return
        # Skip commands
        if raw.lstrip().startswith(("/", "!")):
            return

        cid = message.chat.id
        s   = await _get_settings(cid)
        if not s["enabled"]:
            #print(f"[BW] SKIP: disabled chat={cid}")
            return

        user = message.from_user
        if not user:
            return
        # Bot owners always exempt
        if user.id in ADMINS_ID:
            return

        #print(f"[BW] _enforce CALLED uid={user.id} chat={cid} text={raw[:60]!r}")

        # Resolve role
        is_admin = False
        is_owner = False
        try:
            mem = await client.get_chat_member(cid, user.id)
            if mem.status == ChatMemberStatus.OWNER:
                is_owner = True
                is_admin = True
            elif mem.status == ChatMemberStatus.ADMINISTRATOR:
                is_admin = True
        except Exception as e:
            print(f"[BW] ROLE CHECK FAILED uid={user.id}: {e}")

        # Detection
        hit = _check_words(raw)
        if not hit:
            hit = _check_custom(raw, await _owner_words())
        if not hit:
            hit = _check_custom(raw, await _group_words(cid))

        #print(f"[BW] RESULT uid={user.id} hit={hit!r}")
        if not hit:
            return

        # Delete offending message
        try:
            await message.delete()
            #print(f"[BW] DELETED uid={user.id}")
        except Exception as e:
            print(f"[BW] DELETE FAILED: {e}")

        # ── PATH A: admin / owner violated ──────────────────────
        if is_admin:
            if is_owner:
                tags = await _admin_mentions(client, cid)
                await client.send_message(
                    cid,
                    f"⚠️ **Owner Violation**\n\n"
                    f"👑 Owner   : {user.mention} used a blocked word!\n"
                    f"🔤 Matched : `{hit}`\n\n"
                    f"👮 Admins  : {tags} — please review.",
                )
            else:
                owner    = await _group_owner(client, cid)
                omention = owner.user.mention if owner else "_(owner not found)_"
                await client.send_message(
                    cid,
                    f"⚠️ **Admin Violation**\n\n"
                    f"👤 Admin   : {user.mention} used a blocked word!\n"
                    f"🔤 Matched : `{hit}`\n\n"
                    f"👑 Owner   : {omention} — please review this admin.",
                )
            return

        # ── PATH B: regular user violated ───────────────────────
        warn_count = await _add_warn(cid, user.id)
        warn_limit = s["warn_limit"]
        admins     = await _admin_mentions(client, cid)

        # Check current mute/ban state for button labels
        muted  = await _is_muted(cid, user.id)
        banned = await _is_banned(cid, user.id)

        report = (
            f"🚨 **Violation Detected**\n\n"
            f"👤 User    : {user.mention}\n"
            f"🔤 Matched : `{hit}`\n"
            f"⚠️ Warns   : `{warn_count}/{warn_limit}`\n\n"
            f"👮 Admins  : {admins}"
        )

        if warn_count < warn_limit:
            # FIX 2: Send with Mute/Unmute, Ban/Unban, Kick buttons
            await client.send_message(
                cid,
                report,
                reply_markup=_kb_warn_actions(cid, user.id, muted=muted, banned=banned),
            )
            return

        # Warn limit reached → punish automatically
        action = s["action"]
        try:
            if action == "ban":
                await client.ban_chat_member(cid, user.id)
                await _set_banned(cid, user.id, True)
                atxt = "🚫 **Banned**"
            elif action == "kick":
                await client.ban_chat_member(cid, user.id)
                await client.unban_chat_member(cid, user.id)
                atxt = "👢 **Kicked**"
            else:  # mute (default)
                until = datetime.utcnow() + timedelta(hours=1)
                await client.restrict_chat_member(
                    cid, user.id, ChatPermissions(), until_date=until
                )
                await _set_muted(cid, user.id, True)
                atxt = "🔇 **Muted** (1 h)"
            #print(f"[BW] PUNISHED uid={user.id} action={action}")
        except Exception as e:
            atxt = f"⚠️ Action failed: `{e}`"
            print(f"[BW] PUNISH FAILED uid={user.id}: {e}")

        await _reset_warn(cid, user.id)
        await client.send_message(
            cid,
            f"{report}\n\n"
            f"🔨 Action  : {atxt}\n"
            f"📌 Reason  : warn limit `{warn_limit}` reached.",
            reply_markup=_kb_warn_actions(cid, user.id, muted=(action == "mute"), banned=(action == "ban")),
        )

    except Exception as e:
        print(f"[BW] _enforce EXCEPTION: {e}")
        traceback.print_exc()

# ══════════════════════════════════════════════════════════════════
# REGISTER HANDLERS VIA add_handler() — NOT decorators
# ══════════════════════════════════════════════════════════════════
_bw_filter = (
    filters.group
    & ~filters.bot
    & ~filters.service
    & (filters.text | filters.caption)
)

app.add_handler(MessageHandler(_enforce, _bw_filter), group=-2)
app.add_handler(EditedMessageHandler(_enforce, _bw_filter), group=-2)
#print("BW] ✅ Enforcement handlers registered via add_handler(group=-2)")

# ══════════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ══════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^bw_"))
async def cb_blockword(client: Client, query: CallbackQuery):
    cid      = query.message.chat.id
    uid      = query.from_user.id
    data     = query.data
    is_admin = await _is_admin(client, cid, uid)
    is_bot   = uid in ADMINS_ID

    # ── FIX 2: Inline action buttons on warn messages ───────────
    # Mute
    if data.startswith("bw_mute_"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        parts    = data.split("_")
        tcid, tuid = int(parts[2]), int(parts[3])
        try:
            until = datetime.utcnow() + timedelta(hours=1)
            await client.restrict_chat_member(
                tcid, tuid, ChatPermissions(), until_date=until
            )
            await _set_muted(tcid, tuid, True)
            banned = await _is_banned(tcid, tuid)
            await query.message.edit_reply_markup(
                _kb_warn_actions(tcid, tuid, muted=True, banned=banned)
            )
            await query.answer("🔇 User muted for 1 hour!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Failed: {e}", show_alert=True)
        return

    # Unmute
    if data.startswith("bw_unmute_"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        parts    = data.split("_")
        tcid, tuid = int(parts[2]), int(parts[3])
        try:
            await client.restrict_chat_member(
                tcid, tuid,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                )
            )
            await _set_muted(tcid, tuid, False)
            banned = await _is_banned(tcid, tuid)
            await query.message.edit_reply_markup(
                _kb_warn_actions(tcid, tuid, muted=False, banned=banned)
            )
            await query.answer("🔊 User unmuted!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Failed: {e}", show_alert=True)
        return

    # Ban
    if data.startswith("bw_ban_"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        parts    = data.split("_")
        tcid, tuid = int(parts[2]), int(parts[3])
        try:
            await client.ban_chat_member(tcid, tuid)
            await _set_banned(tcid, tuid, True)
            muted = await _is_muted(tcid, tuid)
            await query.message.edit_reply_markup(
                _kb_warn_actions(tcid, tuid, muted=muted, banned=True)
            )
            await query.answer("🚫 User banned!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Failed: {e}", show_alert=True)
        return

    # Unban
    if data.startswith("bw_unban_"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        parts    = data.split("_")
        tcid, tuid = int(parts[2]), int(parts[3])
        try:
            await client.unban_chat_member(tcid, tuid)
            await _set_banned(tcid, tuid, False)
            muted = await _is_muted(tcid, tuid)
            await query.message.edit_reply_markup(
                _kb_warn_actions(tcid, tuid, muted=muted, banned=False)
            )
            await query.answer("✅ User unbanned!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Failed: {e}", show_alert=True)
        return

    # Kick
    if data.startswith("bw_kick_"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        parts    = data.split("_")
        tcid, tuid = int(parts[2]), int(parts[3])
        try:
            await client.ban_chat_member(tcid, tuid)
            await client.unban_chat_member(tcid, tuid)
            await query.answer("👢 User kicked!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Failed: {e}", show_alert=True)
        return

    # ── Standard dashboard callbacks ─────────────────────────────
    if data == "bw_noop":
        return await query.answer("ℹ️ No action.")

    if data == "bw_status_info":
        s = await _get_settings(cid)
        return await query.answer(
            f"{'ON ✅' if s['enabled'] else 'OFF ❌'}  |  "
            f"Warn: {s['warn_limit']}  |  {s['action'].title()}",
            show_alert=True,
        )

    if data == "bw_toggle":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        s  = await _get_settings(cid)
        en = not s["enabled"]
        await _set(cid, "enabled", en)
        await query.message.edit_text(
            f"🛡 **BlockWord Dashboard**\n\n"
            f"Status     : {'✅ Active' if en else '❌ Inactive'}\n"
            f"Warn Limit : `{s['warn_limit']}`\n"
            f"Punishment : `{s['action'].title()}`",
            reply_markup=_kb_dashboard(en),
        )
        return await query.answer(f"{'✅ Enabled' if en else '❌ Disabled'}!")

    if data == "bw_main":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        s  = await _get_settings(cid)
        en = s["enabled"]
        await query.message.edit_text(
            f"🛡 **BlockWord Dashboard**\n\n"
            f"Status     : {'✅ Active' if en else '❌ Inactive'}\n"
            f"Warn Limit : `{s['warn_limit']}`\n"
            f"Punishment : `{s['action'].title()}`",
            reply_markup=_kb_dashboard(en),
        )
        return await query.answer()

    if data == "bw_listwords":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        gw  = await _group_words(cid)
        ow  = await _owner_words()
        txt = "📋 **Blocked Words**\n\n"
        txt += ("**📌 Group:**\n" + "\n".join(f"  • `{w}`" for w in gw) + "\n\n") if gw else "**📌 Group:** _None_\n\n"
        txt += ("**🌍 Global:**\n" + "\n".join(f"  • `{w}`" for w in ow)) if ow else "**🌍 Global:** _None_"
        await query.message.edit_text(txt, reply_markup=_kb_words())
        return await query.answer()

    if data == "bw_owner_listwords":
        if not is_bot:
            return await query.answer("❌ Bot owner only!", show_alert=True)
        words = await _owner_words()
        txt   = "🌍 **Global Words:**\n" + ("\n".join(f"  • `{w}`" for w in words) if words else "_None_")
        await query.message.edit_text(txt, reply_markup=_kb_back("bw_main"))
        return await query.answer()

    if data == "bw_settings_menu":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        s = await _get_settings(cid)
        await query.message.edit_text(
            f"⚙️ **Settings**\n\nWarn Limit : `{s['warn_limit']}`\nPunishment : `{s['action'].title()}`",
            reply_markup=_kb_settings(),
        )
        return await query.answer()

    if data == "bw_set_warnlimit":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        await query.message.edit_text(
            "Send `/setwarnlimit <n>`  e.g. `/setwarnlimit 3`",
            reply_markup=_kb_back("bw_settings_menu"),
        )
        return await query.answer()

    if data == "bw_set_punishment":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        await query.message.edit_text("🔨 **Choose Punishment:**", reply_markup=_kb_punish())
        return await query.answer()

    if data in ("bw_action_mute", "bw_action_ban", "bw_action_kick"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        action = data.replace("bw_action_", "")
        await _set(cid, "action", action)
        await query.message.edit_text(
            f"✅ Punishment → **{action.title()}**.",
            reply_markup=_kb_back("bw_settings_menu"),
        )
        return await query.answer(f"→ {action.title()}")

    if data == "bw_addword_hint":
        return await query.answer("Send /addword <word>", show_alert=True)

    if data == "bw_help":
        await query.message.edit_text(
            "🛡 **BlockWord Help**\n\n"
            "**👮 Admin:**\n"
            "• `/blockword` — Dashboard\n"
            "• `/blockword on|off` — Toggle\n"
            "• `/addword <word>` — Add group word\n"
            "• `/blockwords` — List words\n"
            "• `/setwarnlimit <n>` — Warn limit\n"
            "• `/setpunishment` — Set action\n"
            "• `/bwtest <word>` — Test detection\n\n"
            "**👑 Group Owner:**\n"
            "• `/removeword <word>` — Remove word\n\n"
            "**🤖 Bot Owner:**\n"
            "• `/ownerblockword <word>` — Global word\n"
            "• `/ownerrmword <word>` — Remove global\n"
            "• `/rmallwords` — Clear all global\n\n"
            "**ℹ️ Detection:**\n"
            "• Regex with word-boundary matching\n"
            "• Custom words: leet-proof normalisation\n"
            "• Edited messages also scanned\n"
            "• Registered via add_handler — StopPropagation-proof\n"
            "• Admin violates → owner tagged\n"
            "• User violates → all admins tagged\n"
            "• Warn message has Mute/Unmute, Ban/Unban, Kick buttons\n"
            "• All data persists in MongoDB across restarts\n",
            reply_markup=_kb_back("bw_main"),
        )
        return await query.answer()


__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_88"
__help__ = """
👮 **Admin Commands:**
🔻 /blockword — ᴏᴘᴇɴ ᴅᴀsʜʙᴏᴀʀᴅ
🔻 /blockword on|off — ᴛᴏɢɢʟᴇ
🔻 /addword <word> — ᴀᴅᴅ ᴡᴏʀᴅ
🔻 /blockwords — ʟɪsᴛ ᴡᴏʀᴅs
🔻 /setwarnlimit <n> — ᴡᴀʀɴ ʟɪᴍɪᴛ
🔻 /setpunishment — ᴘᴜɴɪsʜᴍᴇɴᴛ
🔻 /bwtest <word> — ᴛᴇsᴛ ᴅᴇᴛᴇᴄᴛɪᴏɴ
👑 **Group Owner:**
🔻 /removeword <word> — ʀᴇᴍᴏᴠᴇ ᴡᴏʀᴅ
🤖 **Bot Owner:**
🔻 /ownerblockword <word> — ɢʟᴏʙᴀʟ ᴡᴏʀᴅ
🔻 /ownerrmword <word> — ʀᴇᴍᴏᴠᴇ ɢʟᴏʙᴀʟ
🔻 /rmallwords — ᴄʟᴇᴀʀ ᴀʟʟ
"""
