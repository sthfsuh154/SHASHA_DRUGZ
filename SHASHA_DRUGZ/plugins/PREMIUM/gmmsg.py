import random
from pyrogram import filters
from SHASHA_DRUGZ import app

@app.on_message(
    filters.command(["m", "oodmorning", "orning"], prefixes=["g", "G"]),
    group=-1
)
async def goodmorning_command_handler(_, message):
    sender = message.from_user.mention
    send_video = random.choice([True, False])

    if send_video:
        video_id = get_random_video()
        await app.send_video(message.chat.id, video_id)
        await message.reply_text(f"**Good Morning, {sender}! Wakeup fast. 🥰**")
    else:
        emoji = get_random_emoji()
        await app.send_message(message.chat.id, emoji)
        await message.reply_text(f"**Good Morning, {sender}! Wakeup fast. {emoji}**")

def get_random_video():
    videos = [
        "https://telegra.ph/file/2c63e594336bfab096835.mp4",
        "https://telegra.ph/file/8e5a08a654079fef23659.mp4",
        "https://telegra.ph/file/7dd498fb3c0ddd6c17e84.mp4",
        "https://telegra.ph/file/941f1237d433974398b12.mp4",
    ]
    return random.choice(videos)

def get_random_emoji():
    emojis = ["🥰", "🥱", "🤗"]
    return random.choice(emojis)
