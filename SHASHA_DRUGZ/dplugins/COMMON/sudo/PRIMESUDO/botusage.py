import asyncio
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    InputMediaPhoto,
)
import matplotlib.pyplot as plt

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import mongodb

# ===================== Mongo Collections =====================
users_col    = mongodb.users
chats_col    = mongodb.chats
channels_col = mongodb.channels
monthly_col  = mongodb.monthly_users   # stores {user_id, month:"YYYY-MM"}

# ===================== SUDO FILTER =====================
def sudo_filter(_, __, message: Message):
    return message.from_user and message.from_user.id in SUDOERS

sudo_only = filters.create(sudo_filter)

# ===================== CURRENT MONTH KEY =====================
def current_month_key() -> str:
    """Returns a string like '2025-06' for the current UTC month."""
    now = datetime.utcnow()
    return f"{now.year}-{now.month:02d}"

# ===================== TRACK MONTHLY USER (call from other modules if needed) =====================
async def track_monthly_user(user_id: int):
    """
    Upserts a unique record per user per calendar month.
    Calling this multiple times for the same user in the same month
    will NOT inflate the count.
    """
    key = current_month_key()
    await monthly_col.update_one(
        {"user_id": user_id, "month": key},
        {"$set": {"user_id": user_id, "month": key}},
        upsert=True,
    )

# ===================== AUTO RESET OLD MONTHLY DOCS =====================
async def auto_reset_monthly():
    """
    Runs in the background and removes monthly_col docs that are NOT
    from the current month.  This keeps the collection lean without
    depending on the bot being alive at exactly midnight on the 1st.
    Runs every 6 hours.
    """
    while True:
        try:
            key = current_month_key()
            result = await monthly_col.delete_many({"month": {"$ne": key}})
        except Exception:
            pass
        await asyncio.sleep(6 * 3600)   # check every 6 hours

asyncio.get_event_loop().create_task(auto_reset_monthly())

# ===================== GET STATS =====================
async def get_stats():
    """
    Returns accurate counts:
      total_users   — all documents in users_col
      total_chats   — all documents in chats_col
      total_channels— all documents in channels_col
      monthly_users — unique users tracked THIS calendar month
    """
    key = current_month_key()

    total_users    = await users_col.count_documents({})
    total_chats    = await chats_col.count_documents({})
    total_channels = await channels_col.count_documents({})
    monthly_users  = await monthly_col.count_documents({"month": key})

    return total_users, total_chats, total_channels, monthly_users

# ===================== PIE CHART GENERATOR =====================
async def generate_pie_chart():
    total_users, total_chats, total_channels, monthly_users = await get_stats()

    labels = ["Users", "Chats", "Channels", "Monthly"]
    values = [total_users, total_chats, total_channels, monthly_users]

    # Avoid pie-chart crash when all values are 0
    if all(v == 0 for v in values):
        values = [1, 1, 1, 1]

    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=140)
    plt.title("Bot Usage Statistics")
    plt.tight_layout()

    path = "usage_pie_chart.png"
    plt.savefig(path)
    plt.close()
    return path

# ===================== SEND IMAGE + CAPTION =====================
async def send_usage_graph(message: Message):
    img = await generate_pie_chart()
    total_users, total_chats, total_channels, monthly_users = await get_stats()

    caption = (
        "📊 **Bot Usage Statistics**\n\n"
        f"👥 Total Users   : `{total_users}`\n"
        f"💬 Total Chats   : `{total_chats}`\n"
        f"📢 Total Channels: `{total_channels}`\n"
        f"📅 Monthly Users : `{monthly_users}`"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats_graph")],
            [
                InlineKeyboardButton("Tot-Users",  callback_data="show_users"),
                InlineKeyboardButton("Chats",      callback_data="show_chats"),
            ],
            [
                InlineKeyboardButton("Channels",      callback_data="show_channels"),
                InlineKeyboardButton("MonthlyUsers",  callback_data="show_monthly"),
            ],
        ]
    )

    await message.reply_photo(photo=img, caption=caption, reply_markup=keyboard)

# ===================== COMMAND HANDLER =====================
@app.on_message(filters.command("botusage") & sudo_only)
async def usage_graph_handler(client, message: Message):
    await send_usage_graph(message)

# ===================== CALLBACK QUERY HANDLER =====================
@app.on_callback_query(
    filters.regex(
        r"^(refresh_stats_graph|show_users|show_chats|show_channels|show_monthly)$"
    )
)
async def callback_handler(client, callback):
    total_users, total_chats, total_channels, monthly_users = await get_stats()

    # -------- REFRESH --------
    if callback.data == "refresh_stats_graph":
        img = await generate_pie_chart()
        new_caption = (
            "📊 **Bot Usage Statistics (Updated)**\n\n"
            f"👥 Total Users   : `{total_users}`\n"
            f"💬 Total Chats   : `{total_chats}`\n"
            f"📢 Total Channels: `{total_channels}`\n"
            f"📅 Monthly Users : `{monthly_users}`"
        )
        await callback.message.edit_media(
            InputMediaPhoto(img),
            reply_markup=callback.message.reply_markup,
        )
        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=callback.message.reply_markup,
        )
        return await callback.answer("✔ Stats Updated!", show_alert=False)

    # -------- POPUP ONLY BUTTONS --------
    if callback.data == "show_users":
        return await callback.answer(f"👥 Total Users: {total_users}", show_alert=True)
    if callback.data == "show_chats":
        return await callback.answer(f"💬 Total Chats: {total_chats}", show_alert=True)
    if callback.data == "show_channels":
        return await callback.answer(f"📢 Total Channels: {total_channels}", show_alert=True)
    if callback.data == "show_monthly":
        return await callback.answer(
            f"📅 Monthly Users ({current_month_key()}): {monthly_users}",
            show_alert=True,
        )

__menu__    = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__     = """
🔻 /botusage ➠ ᴅɪsᴘʟᴀʏ ɢʀᴀᴘʜɪᴄᴀʟ ʙᴏᴛ ᴜsᴀɢᴇ sᴛᴀᴛs ᴡɪᴛʜ ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ ʙᴜᴛᴛᴏɴs
"""

MOD_TYPE = "SUDO"
MOD_NAME = "Bot-Usage"
MOD_PRICE = "20"
