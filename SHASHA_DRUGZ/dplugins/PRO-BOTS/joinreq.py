import os
import asyncio
import datetime
import html as _html
from typing import Optional, Dict, Any, List
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatJoinRequest,
    Message,
    User,
    ChatPermissions,
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
# SHASHA_DRUGZ app
from SHASHA_DRUGZ import app
# MongoDB
import motor.motor_asyncio
from pymongo import ReturnDocument
MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority",
)
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is required by joinreq.py")
mongo = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = mongo.get_database("ghosttreq_db")
settings_coll = db.get_collection("join_request_settings")
# Temporary in-memory states
PENDING_REASON_PROMPTS: Dict[int, Dict[str, Any]] = {}

IST_OFFSET = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def ts() -> str:
    now_ist = datetime.datetime.now(IST_OFFSET)
    return now_ist.strftime("%Y-%m-%d %I:%M:%S %p IST")

def to_ist_str(dt: datetime.datetime) -> str:
    """Convert a UTC or timezone-aware datetime to IST string with AM/PM."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    ist_dt = dt.astimezone(IST_OFFSET)
    return ist_dt.strftime("%Y-%m-%d %I:%M:%S %p IST")

def tf(v: bool) -> str:
    return "🍏 Eɴᴀʙʟᴇᴅ" if v else "🍎 Dɪsᴀʙʟᴇᴅ"

def mention_html(user: User) -> str:
    name = _html.escape(user.first_name or "User")
    return f"<a href='tg://user?id={user.id}'>{name}</a>"

def group_mention_html(chat_title: str, chat_id: int) -> str:
    escaped = _html.escape(chat_title or str(chat_id))
    return f"<a href='tg://resolve?domain=c/{abs(chat_id)}'>{escaped}</a>"

def user_full_mention(user: User) -> str:
    """Returns mention with username appended if available."""
    name = _html.escape(f"{user.first_name or ''} {user.last_name or ''}".strip() or "User")
    link = f"<a href='tg://user?id={user.id}'>{name}</a>"
    if user.username:
        return f"{link} (@{_html.escape(user.username)})"
    return link

# -------------------------
# DB helpers
# -------------------------
async def get_settings(chat_id: int) -> dict:
    doc = await settings_coll.find_one({"chat_id": chat_id})
    if not doc:
        doc = {
            "chat_id": chat_id,
            "enabled": False,
            "auto_approve": False,
            "log_chat_id": None,
        }
        await settings_coll.insert_one(doc)
    return doc

async def set_settings(chat_id: int, patch: dict) -> dict:
    doc = await settings_coll.find_one_and_update(
        {"chat_id": chat_id},
        {"$set": patch},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc

# -------------------------
# Permission checks
# -------------------------
async def is_group_owner(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except RPCError:
        return False

async def is_group_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except RPCError:
        return False

async def send_log(client, log_chat_id: Optional[int], text: str, **kwargs):
    if not log_chat_id:
        return
    try:
        await client.send_message(log_chat_id, text, **kwargs)
    except RPCError:
        pass

# -------------------------
# UI helpers
# -------------------------
def make_request_buttons(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🍏 Aᴘᴘʀᴏᴠᴇ", callback_data=f"jr:approve:{chat_id}:{user_id}"),
                InlineKeyboardButton("🍎 Dɪsᴍɪss", callback_data=f"jr:decline_prompt:{chat_id}:{user_id}"),
            ],
            [
                InlineKeyboardButton("🤐 Mᴜᴛᴇ", callback_data=f"jr:mute:{chat_id}:{user_id}"),
                InlineKeyboardButton("🔨 Bᴀɴ", callback_data=f"jr:ban:{chat_id}:{user_id}"),
            ],
            [
                InlineKeyboardButton("🔻 Dɪsᴍɪss Wɪᴛʜ Rᴇᴀsᴏɴ 🔻", callback_data=f"jr:decline_reason:{chat_id}:{user_id}"),
            ],
        ]
    )

def make_owner_settings_kb(chat_id: int, enabled: bool, auto: bool, log_id: Optional[int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🍎 Dɪsᴀʙʟᴇ" if enabled else "🍏 Eɴᴀʙʟᴇ", callback_data=f"jr:toggle_enabled:{chat_id}"),
                InlineKeyboardButton("🍎 Aᴜᴛᴏ" if auto else "🍏 Mᴀɴᴜᴀʟ", callback_data=f"jr:toggle_auto:{chat_id}"),
            ],
            [
                InlineKeyboardButton("Sᴇᴛ Lᴏɢ-Gʀᴏᴜᴘ", callback_data=f"jr:set_log:{chat_id}"),
                InlineKeyboardButton("Cʟᴇᴀʀ Lᴏɢ", callback_data=f"jr:clear_log:{chat_id}"),
            ],
            [
                InlineKeyboardButton("🔻 Aᴘᴘʀᴏᴠᴇ Aʟʟ Pᴇɴᴅɪɴɢs 🔻", callback_data=f"jr:approve_all:{chat_id}"),
            ],
        ]
    )

def nice_user_details(user: User) -> str:
    uname = f"@{user.username}" if user.username else "—"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not name:
        name = "No name"
    return f"<b>{_html.escape(name)}</b> ({_html.escape(uname)})\nID: <code>{user.id}</code>"

# -------------------------
# Mute and Ban helpers
# -------------------------
async def mute_user(client, chat_id: int, user_id: int, admin: User) -> bool:
    try:
        await client.approve_chat_join_request(chat_id, user_id)
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_send_polls=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
        )
        await client.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
        )
        return True
    except RPCError as e:
        print(f"[joinreq] Error muting user: {e}")
        return False

async def ban_user(client, chat_id: int, user_id: int, admin: User) -> bool:
    try:
        await client.approve_chat_join_request(chat_id, user_id)
        await client.ban_chat_member(chat_id=chat_id, user_id=user_id)
        return True
    except RPCError as e:
        print(f"[joinreq] Error banning user: {e}")
        return False

# -------------------------
# Background cleanup task
# -------------------------
async def reason_cleanup_task():
    while True:
        now = datetime.datetime.utcnow()
        to_del = [
            k for k, v in list(PENDING_REASON_PROMPTS.items())
            if v.get("expires_at") and now > v["expires_at"]
        ]
        for k in to_del:
            PENDING_REASON_PROMPTS.pop(k, None)
        await asyncio.sleep(30)

# ---- Start the cleanup task when the module is imported ----
_cleanup_started = False

@Client.on_message(filters.command("_jr_init_internal_") & filters.private, group=-9999)
async def _noop_init(client, message: Message):
    pass

async def _ensure_cleanup_task():
    global _cleanup_started
    if not _cleanup_started:
        _cleanup_started = True
        asyncio.get_event_loop().create_task(reason_cleanup_task())

_task_launched = False

async def _lazy_start_cleanup():
    global _task_launched
    if not _task_launched:
        _task_launched = True
        asyncio.get_event_loop().create_task(reason_cleanup_task())
        #print("joinreq] Cleanup task started.")

# -------------------------
# Commands & Menu
# -------------------------
@Client.on_message(filters.command(["joinreq", "joinrequest"]) & filters.group, group=10)
async def cmd_jr_menu(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_group_owner(client, chat_id, user_id):
        await message.reply_text("⚠️ Only the group *owner* can open join-request settings.")
        return
    s = await get_settings(chat_id)
    enabled = tf(s.get("enabled", False))
    auto_approve = tf(s.get("auto_approve", False))
    log_chat = s.get("log_chat_id")
    kb = make_owner_settings_kb(
        chat_id,
        s.get("enabled", False),
        s.get("auto_approve", False),
        s.get("log_chat_id"),
    )
    text = (
        f"<blockquote>🚀 Jᴏɪɴ Rᴇǫᴜᴇsᴛ Mᴇɴᴜ\n <b>{_html.escape(message.chat.title or str(chat_id))}</b></blockquote>\n"
        f"<blockquote>▪️ Rᴇǫ Tᴏ Jᴏɪɴ    : <code>{enabled}</code>\n"
        f"▪️ Aᴘᴘʀᴏᴠᴇ Mᴏᴅᴇ: <code>{auto_approve}</code>\n"
        f"▪️ Lᴏɢ Gʀᴏᴜᴘ    : <code>{log_chat}</code></blockquote>\n"
    )
    await message.reply_text(text, reply_markup=kb)

# -------------------------
# Approve All Shortcut
# -------------------------
@Client.on_message(filters.command("approveall") & filters.group, group=10)
async def cmd_approve_all(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_group_admin(client, chat_id, user_id):
        await message.reply_text("Only group admins can use this.")
        return
    try:
        ok = await client.approve_all_chat_join_requests(chat_id)
        if ok:
            await message.reply_text("✅ All pending join requests approved.")
            s = await get_settings(chat_id)
            await send_log(
                client,
                s.get("log_chat_id"),
                f"{ts()} — ✅ Approve ALL executed by {mention_html(message.from_user)}.",
            )
        else:
            await message.reply_text("❌ Failed (no permission?).")
    except RPCError as e:
        await message.reply_text(f"❌ Error: {e}")

# -------------------------
# Settings Callbacks  (group=10)
# -------------------------
@Client.on_callback_query(
    filters.regex(r"^jr:(toggle_enabled|toggle_auto|set_log|clear_log|approve_all|view_pending):-?\d+$"),
    group=10,
)
async def jr_owner_cb(client, cq: CallbackQuery):
    data = cq.data
    parts = data.split(":")
    action = parts[1]
    chat_id = int(parts[2])
    caller = cq.from_user
    if not await is_group_owner(client, chat_id, caller.id):
        await cq.answer("Only the group owner can use this menu.", show_alert=True)
        return
    s = await get_settings(chat_id)
    if action == "toggle_enabled":
        new = not s.get("enabled", False)
        await set_settings(chat_id, {"enabled": new})
        await cq.answer("Toggled enabled.", show_alert=False)
        await cq.edit_message_text(
            f"✅ Enabled set to <code>{new}</code> for chat <b>{chat_id}</b>.\nUse /joinreq to reopen.",
        )
    elif action == "toggle_auto":
        new = not s.get("auto_approve", False)
        await set_settings(chat_id, {"auto_approve": new})
        await cq.answer("Toggled auto-approve.", show_alert=False)
        await cq.edit_message_text(
            f"✅ Auto-approve set to <code>{new}</code> for chat <b>{chat_id}</b>.\nUse /joinreq to reopen.",
        )
    elif action == "set_log":
        await cq.answer("Check your private messages.", show_alert=True)
        cancel_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="jr:cancel_log_prompt")]]
        )
        try:
            await client.send_message(
                caller.id,
                f"Please reply to this message with the target log chat id "
                f"(e.g. -1001234567890) or @username to set as log for chat <b>{chat_id}</b>.\n\n"
                f"Format: <code>-100groupid -100logid</code>",
                reply_markup=cancel_kb,
            )
        except RPCError:
            await cq.answer("Could not send private message. Start the bot in PM first.", show_alert=True)
    elif action == "clear_log":
        await set_settings(chat_id, {"log_chat_id": None})
        await cq.answer("Log cleared.", show_alert=False)
        await cq.edit_message_text(f"✅ Cleared log chat for <b>{chat_id}</b>.")
    elif action == "approve_all":
        try:
            ok = await client.approve_all_chat_join_requests(chat_id)
            if ok:
                await cq.answer("All pending requests approved.", show_alert=True)
                s = await get_settings(chat_id)
                await send_log(
                    client,
                    s.get("log_chat_id"),
                    f"{ts()} — ✅ Approve ALL executed by owner {mention_html(caller)} for chat <code>{chat_id}</code>.",
                )
                await cq.edit_message_text("✅ Approved all pending join requests.")
            else:
                await cq.answer("Failed (no permission?).", show_alert=True)
        except RPCError as e:
            await cq.answer(f"Error: {e}", show_alert=True)
    elif action == "view_pending":
        try:
            reqs = []
            async for r in client.get_chat_join_requests(chat_id):
                reqs.append(r)
            if not reqs:
                await cq.answer("No pending requests.", show_alert=True)
                await cq.edit_message_text("No pending join requests.")
                return
            lines = []
            for r in reqs[:20]:
                user = r.from_user
                uname = f"@{user.username}" if user.username else "—"
                lines.append(
                    f"{_html.escape(user.first_name or 'NoName')} "
                    f"{_html.escape(user.last_name or '')} "
                    f"{uname} — <code>{user.id}</code>"
                )
            text = "Pending (preview up to 20):\n\n" + "\n".join(lines)
            await cq.answer("Fetched pending requests.", show_alert=False)
            await cq.edit_message_text(text)
        except RPCError as e:
            await cq.answer(f"Error: {e}", show_alert=True)

# -------------------------
# Cancel log prompt callback  (group=10)
# -------------------------
@Client.on_callback_query(filters.regex(r"^jr:cancel_log_prompt$"), group=10)
async def jr_cancel_cb(client, cq: CallbackQuery):
    await cq.answer("Operation Cancelled.")
    await cq.message.delete()

# -------------------------
# Admin action callbacks  (group=10)
# -------------------------
@Client.on_callback_query(
    filters.regex(r"^jr:(approve|decline_prompt|decline_reason|view|mute|ban):-?\d+:\d+$"),
    group=10,
)
async def jr_admin_cb(client, cq: CallbackQuery):
    data = cq.data
    parts = data.split(":")
    action = parts[1]
    chat_id = int(parts[2])
    user_id = int(parts[3])
    caller = cq.from_user
    if not await is_group_admin(client, chat_id, caller.id):
        await cq.answer("Only group admins can perform this action.", show_alert=True)
        return
    # Verify bot is admin in the group
    me = await client.get_me()
    try:
        me_member = await client.get_chat_member(chat_id, me.id)
        if me_member.status != ChatMemberStatus.ADMINISTRATOR:
            await cq.answer("I must be admin in the group to perform approvals.", show_alert=True)
            return
    except RPCError:
        await cq.answer("Unable to verify my admin status.", show_alert=True)
        return
    s = await get_settings(chat_id)
    if action == "approve":
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            await cq.edit_message_text(
                f"<blockquote>🍏 Aᴘᴘʀᴏᴠᴇᴅ Bʏ \n{mention_html(caller)}</blockquote>\n"
                f"<blockquote>✨ Usᴇʀ: <code>{user_id}</code></blockquote>",
            )
            await send_log(
                client,
                s.get("log_chat_id"),
                f"<blockquote>{ts()} — 🚀 Rᴇǫᴜᴇsᴛ Aᴘᴘʀᴏᴠᴇᴅ Iɴ \n <b>{chat_id}</b>\n"
                f"✨ Usᴇʀ: <code>{user_id}</code></blockquote>\n"
                f"<blockquote>Bʏ: {mention_html(caller)}</blockquote>",
            )
            try:
                await client.send_message(
                    user_id,
                    f"💥 Your join request to <b>{_html.escape(str(chat_id))}</b> was approved by {mention_html(caller)}.",
                )
            except RPCError:
                pass
            await cq.answer("User approved.", show_alert=False)
        except RPCError as e:
            await cq.answer(f"Failed to approve: {e}", show_alert=True)

    elif action == "decline_prompt":
        try:
            await client.decline_chat_join_request(chat_id, user_id)
            await cq.edit_message_text(
                f"🍎 Dᴇᴄʟɪɴᴇᴅ Bʏ \n{mention_html(caller)}\nUser: <code>{user_id}</code>",
            )
            await send_log(
                client,
                s.get("log_chat_id"),
                f"<blockquote>{ts()} — 🚀 Rᴇǫᴜᴇsᴛ Dᴇᴄʟɪɴᴇᴅ Iɴ <b>{chat_id}</b>\n"
                f"✨ Usᴇʀ: <code>{user_id}</code></blockquote>\n"
                f"<blockquote>Bʏ: {mention_html(caller)}</blockquote>",
            )
            # Notify user via PM
            try:
                await client.send_message(
                    user_id,
                    f"💥 Your join request to <b>{_html.escape(str(chat_id))}</b> was declined by {mention_html(caller)}.",
                )
            except RPCError:
                pass
            # Also post decline notice to the group
            try:
                await client.send_message(
                    chat_id,
                    f"<blockquote>🍎 Jᴏɪɴ Rᴇǫᴜᴇsᴛ Dᴇᴄʟɪɴᴇᴅ\n"
                    f"Usᴇʀ: <code>{user_id}</code>\n"
                    f"Bʏ: {mention_html(caller)}</blockquote>",
                    disable_web_page_preview=True,
                )
            except RPCError:
                pass
            await cq.answer("User declined.", show_alert=False)
        except RPCError as e:
            await cq.answer(f"Failed to decline: {e}", show_alert=True)

    elif action == "decline_reason":
        await cq.answer("Please send me (in private) the reason for decline.", show_alert=True)
        PENDING_REASON_PROMPTS[caller.id] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "action": "decline",
            "expires_at": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
        }
        try:
            await client.send_message(
                caller.id,
                f"You chose to decline user <code>{user_id}</code> from group <code>{chat_id}</code>.\n"
                f"Please send me the reason (you have 5 minutes).",
            )
        except RPCError:
            await cq.answer("Could not open private chat. Start the bot in PM first.", show_alert=True)

    elif action == "mute":
        try:
            success = await mute_user(client, chat_id, user_id, caller)
            if success:
                await cq.edit_message_text(
                    f"<blockquote>🤐 Mᴜᴛᴇᴅ & Aᴘᴘʀᴏᴠᴇᴅ Bʏ \n{mention_html(caller)}</blockquote>\n"
                    f"<blockquote>✨ Usᴇʀ: <code>{user_id}</code></blockquote>",
                )
                await send_log(
                    client,
                    s.get("log_chat_id"),
                    f"<blockquote>{ts()} — 🚀 Rᴇǫᴜᴇsᴛ Mᴜᴛᴇᴅ & Aᴘᴘʀᴏᴠᴇᴅ Iɴ \n <b>{chat_id}</b>\n"
                    f"✨ Usᴇʀ: <code>{user_id}</code></blockquote>\n"
                    f"<blockquote>Bʏ: {mention_html(caller)}</blockquote>",
                )
                try:
                    await client.send_message(
                        user_id,
                        f"🤐 You were approved and muted in <b>{_html.escape(str(chat_id))}</b> by {mention_html(caller)}.",
                    )
                except RPCError:
                    pass
                await cq.answer("User approved and muted.", show_alert=False)
            else:
                await cq.answer("Failed to mute user.", show_alert=True)
        except RPCError as e:
            await cq.answer(f"Failed to mute: {e}", show_alert=True)

    elif action == "ban":
        try:
            success = await ban_user(client, chat_id, user_id, caller)
            if success:
                await cq.edit_message_text(
                    f"<blockquote>🔨 Bᴀɴɴᴇᴅ & Aᴘᴘʀᴏᴠᴇᴅ Bʏ \n{mention_html(caller)}</blockquote>\n"
                    f"<blockquote>✨ Usᴇʀ: <code>{user_id}</code></blockquote>",
                )
                await send_log(
                    client,
                    s.get("log_chat_id"),
                    f"<blockquote>{ts()} — 🚀 Rᴇǫᴜᴇsᴛ Bᴀɴɴᴇᴅ & Aᴘᴘʀᴏᴠᴇᴅ Iɴ \n <b>{chat_id}</b>\n"
                    f"✨ Usᴇʀ: <code>{user_id}</code></blockquote>\n"
                    f"<blockquote>Bʏ: {mention_html(caller)}</blockquote>",
                )
                try:
                    await client.send_message(
                        user_id,
                        f"🔨 You were approved and banned in <b>{_html.escape(str(chat_id))}</b> by {mention_html(caller)}.",
                    )
                except RPCError:
                    pass
                await cq.answer("User approved and banned.", show_alert=False)
            else:
                await cq.answer("Failed to ban user.", show_alert=True)
        except RPCError as e:
            await cq.answer(f"Failed to ban: {e}", show_alert=True)

    elif action == "view":
        try:
            user = await client.get_users(user_id)
            txt = (
                f"<b>User preview</b>\n{nice_user_details(user)}\n\n"
                f"<a href='tg://user?id={user.id}'>Open profile</a>"
            )
            await cq.answer("Showing user details.", show_alert=False)
            await cq.edit_message_text(txt)
        except RPCError as e:
            await cq.answer(f"Could not fetch user: {e}", show_alert=True)

# -------------------------
# Chat join request handler  (group=10)
# -------------------------
@Client.on_chat_join_request(group=10)
async def handle_chat_join_request(client, req: ChatJoinRequest):
    # Lazy-start the cleanup task on the first real update
    await _lazy_start_cleanup()
    chat = req.chat
    requester = req.from_user
    chat_id = chat.id
    user_id = requester.id
    s = await get_settings(chat_id)
    if not s.get("enabled", False):
        return
    if s.get("auto_approve", False):
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            await send_log(
                client,
                s.get("log_chat_id"),
                f"{ts()} — ✅ Auto-approved join request in "
                f"<b>{_html.escape(chat.title or str(chat_id))}</b>\n"
                f"User: {nice_user_details(requester)}",
                disable_web_page_preview=True,
            )
            try:
                await client.send_message(
                    user_id,
                    f"✅ Your join request to <b>{_html.escape(chat.title or str(chat_id))}</b> "
                    f"has been approved automatically.",
                )
            except RPCError:
                pass
        except RPCError as e:
            await send_log(
                client,
                s.get("log_chat_id"),
                f"{ts()} — ❌ Failed to auto-approve. Error: {e}",
            )
        return

    # Manual mode — post notification with admin buttons into the group
    bio = req.bio or "—"
    # Convert request date to IST with AM/PM
    date_sent = to_ist_str(req.date) if req.date else "—"

    # Group: Name with mention (chat id)
    chat_title = chat.title or str(chat_id)
    group_display = f"<a href='tg://resolve?domain=c/{str(abs(chat_id))[3:]}'>{_html.escape(chat_title)}</a> (<code>{chat_id}</code>)"

    # User: Name with mention (Username)
    user_name = f"{requester.first_name or ''} {requester.last_name or ''}".strip() or "User"
    user_mention = f"<a href='tg://user?id={requester.id}'>{_html.escape(user_name)}</a>"
    user_uname = f"@{requester.username}" if requester.username else "No username"
    user_display = f"{user_mention} ({_html.escape(user_uname)})"

    text = (
        f"🔔 <b>New Join Request</b>\n\n"
        f"<b>Group :</b> {group_display}\n"
        f"<b>User  :</b> {user_display}\n"
        f"<b>ID    :</b> <code>{requester.id}</code>\n\n"
        f"<b>Bio   :</b> <code>{_html.escape(bio)}</code>\n"
        f"<b>Requested at :</b> <code>{date_sent}</code>\n\n"
        f"Admins: use the buttons below to approve or decline."
    )
    kb = make_request_buttons(chat_id, user_id)
    try:
        await client.send_message(
            chat_id,
            text,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except RPCError:
        await send_log(
            client,
            s.get("log_chat_id"),
            f"{ts()} — ⚠️ Could not post join request into group <code>{chat_id}</code>.",
        )
        return
    await send_log(
        client,
        s.get("log_chat_id"),
        f"{ts()} — ℹ️ Join request posted in "
        f"<b>{_html.escape(chat.title or str(chat_id))}</b> for {nice_user_details(requester)}",
    )

# -------------------------
# OWNER PRIVATE HANDLER — set log chat  (group=9998)
# -------------------------
@Client.on_message(
    filters.private & filters.reply & ~filters.bot,
    group=9998,
)
async def owner_private_handler(client, message: Message):
    if not message.reply_to_message:
        return
    reply = message.reply_to_message
    me = await client.get_me()
    # Must be a reply to THIS bot
    if not reply.from_user or reply.from_user.id != me.id:
        return
    if not reply.text:
        return
    # Only handle the log-setup prompt
    if "Please reply to this message with the target log chat id" not in reply.text:
        return
    text = (message.text or "").strip()
    if not text:
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(
            "Format:\n<code>-100groupid -100logid</code>",
        )
    try:
        target_chat = int(parts[0])
    except ValueError:
        return await message.reply_text("First argument must be the group id (e.g. -1001234567890).")
    log_target_raw = parts[1].strip()
    try:
        if log_target_raw.startswith("@"):
            resolved = await client.get_chat(log_target_raw)
            log_target_id = resolved.id
        else:
            log_target_id = int(log_target_raw)
            await client.get_chat(log_target_id)
    except (RPCError, ValueError) as e:
        return await message.reply_text(f"Invalid log chat: {e}")
    if not await is_group_owner(client, target_chat, message.from_user.id):
        return await message.reply_text("You are not the owner of that group.")
    await set_settings(target_chat, {"log_chat_id": log_target_id})
    await message.reply_text(
        f"✅ Log chat set for <code>{target_chat}</code>",
    )
    await send_log(
        client,
        log_target_id,
        f"{ts()} — Log configured by {mention_html(message.from_user)}",
    )

# -------------------------
# PRIVATE REASON HANDLER  (group=9999)
# -------------------------
@Client.on_message(
    filters.private & ~filters.bot,
    group=9999,
)
async def private_reason_handler(client, message: Message):
    # Ignore commands
    if message.text and message.text.startswith("/"):
        return
    admin_id = message.from_user.id
    # Only trigger if waiting for a reason
    if admin_id not in PENDING_REASON_PROMPTS:
        return
    state = PENDING_REASON_PROMPTS.get(admin_id)
    if not state:
        return
    # Expiry check
    if datetime.datetime.utcnow() > state.get("expires_at"):
        PENDING_REASON_PROMPTS.pop(admin_id, None)
        return await message.reply_text("❌ Session expired. Please click the button again.")
    reason = (message.text or "").strip()
    if not reason:
        return await message.reply_text("Please send a valid reason (non-empty text).")
    chat_id = state["chat_id"]
    user_id = state["user_id"]
    try:
        await client.decline_chat_join_request(chat_id, user_id)
    except RPCError as e:
        PENDING_REASON_PROMPTS.pop(admin_id, None)
        return await message.reply_text(f"Failed to decline: {e}")
    s = await get_settings(chat_id)
    await send_log(
        client,
        s.get("log_chat_id"),
        f"{ts()} — ❌ Declined with reason:\nUser: <code>{user_id}</code>\nReason: {_html.escape(reason)}",
    )
    await message.reply_text("✅ Declined with reason sent.")
    # Send reason to user via PM
    try:
        await client.send_message(
            user_id,
            f"❌ Your join request was declined.\n\nReason:\n{_html.escape(reason)}",
        )
    except RPCError:
        pass
    # Also post decline reason notice to the group
    try:
        await client.send_message(
            chat_id,
            f"<blockquote>🍎 Jᴏɪɴ Rᴇǫᴜᴇsᴛ Dᴇᴄʟɪɴᴇᴅ Wɪᴛʜ Rᴇᴀsᴏɴ\n"
            f"Usᴇʀ: <code>{user_id}</code>\n"
            f"Bʏ: {mention_html(message.from_user)}\n\n"
            f"Rᴇᴀsᴏɴ: {_html.escape(reason)}</blockquote>",
            disable_web_page_preview=True,
        )
    except RPCError:
        pass
    PENDING_REASON_PROMPTS.pop(admin_id, None)

# -------------------------
# Module metadata
# -------------------------
__menu__ = "CMD_PRO"
__mod_name__ = "H_B_30"
__help__ = """
🔻 /joinreq ➠ ꜱᴇᴛ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ ꜰᴏʀ ɢʀᴏᴜᴘ / ᴄʜᴀɴɴᴇʟ  
🔻 /joinrequest ➠ ᴇɴᴀʙʟᴇ ᴏʀ ᴅɪꜱᴀʙʟᴇ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ
🔻 /approveall ➠ ᴀᴘᴘʀᴏᴠᴇꜱ ᴀʟʟ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
🔻 (ᴀᴜᴛᴏ) ➠ ᴇɴᴀʙʟᴇꜱ / ᴅɪꜱᴀʙʟᴇꜱ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ ꜱʏꜱᴛᴇᴍ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 (ᴀᴜᴛᴏ) ➠ ᴀᴜᴛᴏ-ᴀᴘᴘʀᴏᴠᴇꜱ ᴜꜱᴇʀꜱ ᴡʜᴇɴ ᴀᴜᴛᴏ ᴍᴏᴅᴇ ɪꜱ ᴇɴᴀʙʟᴇᴅ.
🔻 (ᴀᴜᴛᴏ) ➠ ꜱᴇɴᴅꜱ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴛᴏ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 (ʙᴜᴛᴛᴏɴ) ➠ 🍏 Aᴘᴘʀᴏᴠᴇ — ᴀᴘᴘʀᴏᴠᴇꜱ ᴛʜᴇ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ.
🔻 (ʙᴜᴛᴛᴏɴ) ➠ 🍎 Dɪꜱᴍɪꜱꜱ — ᴅᴇᴄʟɪɴᴇꜱ ᴛʜᴇ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ.
🔻 (ʙᴜᴛᴛᴏɴ) ➠ 🔻 Dɪꜱᴍɪꜱꜱ Wɪᴛʜ Rᴇᴀꜱᴏɴ — ᴅᴇᴄʟɪɴᴇꜱ ᴛʜᴇ ʀᴇǫᴜᴇꜱᴛ ᴡɪᴛʜ ᴀ ᴄᴜꜱᴛᴏᴍ ʀᴇᴀꜱᴏɴ.
🔻 (ʙᴜᴛᴛᴏɴ) ➠ 🤐 Mᴜᴛᴇ — ᴀᴘᴘʀᴏᴠᴇꜱ ᴛʜᴇ ᴜꜱᴇʀ ᴀɴᴅ ᴍᴜᴛᴇꜱ ᴛʜᴇᴍ.
🔻 (ʙᴜᴛᴛᴏɴ) ➠ 🔨 Bᴀɴ — ᴀᴘᴘʀᴏᴠᴇꜱ ᴀɴᴅ ɪᴍᴍᴇᴅɪᴀᴛᴇʟʏ ʙᴀɴꜱ ᴛʜᴇ ᴜꜱᴇʀ.
🔻 (ᴀᴜᴛᴏ) ➠ ꜱᴇɴᴅꜱ ᴘʀɪᴠᴀᴛᴇ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴛᴏ ᴜꜱᴇʀꜱ ᴏɴ ᴀᴘᴘʀᴏᴠᴀʟ ᴏʀ ᴅᴇᴄʟɪɴᴇ.
🔻 (ᴀᴜᴛᴏ) ➠ ʟᴏɢꜱ ᴀʟʟ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛ ᴀᴄᴛɪᴠɪᴛʏ ᴛᴏ ᴛʜᴇ ꜱᴇᴛ ʟᴏɢ ɢʀᴏᴜᴘ.
🔻 (ᴏᴡɴᴇʀ ᴍᴇɴᴜ) ➠ ꜱᴇᴛ / ᴄʟᴇᴀʀ ʟᴏɢ ɢʀᴏᴜᴘ ꜰᴏʀ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛꜱ.
🔻 (ᴏᴡɴᴇʀ ᴍᴇɴᴜ) ➠ ᴀᴘᴘʀᴏᴠᴇꜱ ᴀʟʟ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛꜱ ᴡɪᴛʜ ᴏɴᴇ ᴛᴀᴘ.
"""
MOD_TYPE = "PRO-BOTS"
MOD_NAME = "Join-Req"
MOD_PRICE = "100"
