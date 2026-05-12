import random
from SHASHA_DRUGZ import app, userbot
from SHASHA_DRUGZ.misc import SUDOERS
from pyrogram import filters
from pyrogram.types import ChatPermissions, ChatPrivileges
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter

shasha_text = [
    "hey please don't disturb me.",
    "who are you",
    "aap kon ho",
    "aap mere owner to nhi lgte ",
    "hey tum mera name kyu le rhe ho meko sone do",
    "ha bolo kya kaam hai ",
    "dekho abhi mai busy hu ",
    "hey i am busy",
    "aapko smj nhi aata kya ",
    "leave me alone",
    "dude what happend",
]

strict_txt = [
    "i can't restrict against my besties",
    "are you serious i am not restrict to my friends",
    "fuck you bsdk k mai apne dosto ko kyu kru",
    "hey stupid admin ",
    "ha ye phele krlo maar lo ek dusre ki gwaand",
    "i can't hi is my closest friend",
    "i love him please don't restict this user try to usertand "
]

ban     = ["ban", "boom"]
unban   = ["unban"]
mute    = ["mute", "silent", "shut"]
unmute  = ["unmute", "speak", "free"]
kick    = ["kick", "out", "nikaal", "nikal"]
promote = ["promote", "adminship"]
demote  = ["demote", "lelo"]

# ========================================= #
# group=1 ensures this handler does NOT block other modules (group=0 priority)
@app.on_message(
    filters.command(["sha", "shan", "shasha"], prefixes=["/"]) & admin_filter,
    group=1
)
async def restriction_app(client, message):
    reply = message.reply_to_message
    chat_id = message.chat.id

    if len(message.text.split()) < 2:
        return await message.reply(random.choice(shasha_text))

    bruh = message.text.split(maxsplit=1)[1]
    data = bruh.split(" ")

    if not reply:
        return await message.reply("Please reply to a user to perform this action.")

    user_id = reply.from_user.id

    for word in data:
        print(f"present {word}")

        # ── BAN ──
        if word in ban:
            if user_id in SUDOERS:
                await message.reply(random.choice(strict_txt))
            else:
                await client.ban_chat_member(chat_id, user_id)
                await message.reply("OK, Ban kar diya madrchod ko sala Chutiya tha !")

        # ── UNBAN ──
        elif word in unban:
            await client.unban_chat_member(chat_id, user_id)
            await message.reply("Ok, aap bolte hai to unban kar diya")

        # ── KICK ──
        elif word in kick:
            if user_id in SUDOERS:
                await message.reply(random.choice(strict_txt))
            else:
                await client.ban_chat_member(chat_id, user_id)
                await client.unban_chat_member(chat_id, user_id)
                await message.reply("get lost! bhga diya bhosdi wale ko")

        # ── MUTE ── FIX: can_send_messages=False to actually mute
        elif word in mute:
            if user_id in SUDOERS:
                await message.reply(random.choice(strict_txt))
            else:
                permissions = ChatPermissions(can_send_messages=False)
                await message.chat.restrict_member(user_id, permissions)
                await message.reply("muted successfully! Disgusting people.")

        # ── UNMUTE ── restore send permission
        elif word in unmute:
            permissions = ChatPermissions(can_send_messages=True)
            await message.chat.restrict_member(user_id, permissions)
            await message.reply("Huh, OK, sir!")

        # ── PROMOTE ──
        elif word in promote:
            await client.promote_chat_member(
                chat_id, user_id,
                privileges=ChatPrivileges(
                    can_change_info=False,
                    can_invite_users=True,
                    can_delete_messages=True,
                    can_restrict_members=False,
                    can_pin_messages=True,
                    can_promote_members=False,
                    can_manage_chat=True,
                    can_manage_video_chats=True,
                )
            )
            await message.reply("promoted !")

        # ── DEMOTE ──
        elif word in demote:
            await client.promote_chat_member(
                chat_id, user_id,
                privileges=ChatPrivileges(
                    can_change_info=False,
                    can_invite_users=False,
                    can_delete_messages=False,
                    can_restrict_members=False,
                    can_pin_messages=False,
                    can_promote_members=False,
                    can_manage_chat=False,
                    can_manage_video_chats=False,
                )
            )
            await message.reply("demoted !")


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__ = """
🔻 /sha <reply to user> ban ➠ ʙᴀɴ ᴀ ᴜsᴇʀ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ  
🔻 /sha <reply to user> unban ➠ ᴜɴʙᴀɴ ᴀ ᴜsᴇʀ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ  
🔻 /sha <reply to user> kick ➠ ᴋɪᴄᴋ ᴀ ᴜsᴇʀ ᴏᴜᴛ ᴏғ ᴛʜᴇ ɢʀᴏᴜᴘ  
🔻 /sha <reply to user> mute ➠ ᴍᴜᴛᴇ ᴀ ᴜsᴇʀ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ  
🔻 /sha <reply to user> unmute ➠ ᴜɴᴍᴜᴛᴇ ᴀ ᴜsᴇʀ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ  
🔻 /sha <reply to user> promote ➠ ᴘʀᴏᴍᴏᴛᴇ ᴀ ᴜsᴇʀ ᴛᴏ ᴀᴅᴍɪɴ  
🔻 /sha <reply to user> demote ➠ ᴅᴇᴍᴏᴛᴇ ᴀ ᴜsᴇʀ ғʀᴏᴍ ᴀᴅᴍɪɴ
"""
