import asyncio
import importlib
import logging
import time

from pyrogram import idle
from pyrogram.errors import FloodWait as PyroFloodWait
from telethon.errors import FloodWaitError as TelethonFloodWait

import config
from SHASHA_DRUGZ import LOGGER, app, userbot, telethn
from SHASHA_DRUGZ.core.call import SHASHA
from SHASHA_DRUGZ.misc import sudo, BANNED_USERS
from SHASHA_DRUGZ.plugins import ALL_MODULES
from SHASHA_DRUGZ.utils.database import get_banned_users, get_gbanned
from SHASHA_DRUGZ.plugins.PREMIUM.deploy import (
    restart_bots, expiry_checker, load_manual_modules_map
)
from SHASHA_DRUGZ.mongo.deploydb import ensure_indexes
from SHASHA_DRUGZ.plugins.PREMIUM.movebots import load_movebots

# ─────────────────────────────────────────────────────────────
# Restart settings
# ─────────────────────────────────────────────────────────────
RESTART_DELAY   = 10    # seconds to wait before restarting after a crash
MAX_RESTARTS    = 0     # 0 = unlimited; set to N to stop after N crashes

# ─────────────────────────────────────────────────────────────
# Filter: hide noisy UpdateGroupCall AttributeErrors from logs
# ─────────────────────────────────────────────────────────────
class HideUpdateGroupCallError(logging.Filter):
    def filter(self, record):
        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            if exc_value and "UpdateGroupCall" in str(exc_value) and "chat_id" in str(exc_value):
                return False
        msg = record.getMessage()
        if "UpdateGroupCall" in msg and "chat_id" in msg:
            return False
        return True

logging.getLogger("pyrogram.dispatcher").addFilter(HideUpdateGroupCallError())


# ─────────────────────────────────────────────────────────────
# Safe Telethon start — auto-waits on FloodWait
# ─────────────────────────────────────────────────────────────
async def start_telethn_safe():
    while True:
        try:
            await telethn.start(bot_token=config.BOT_TOKEN)
            LOGGER(__name__).info("✅ Telethon started successfully.")
            break
        except TelethonFloodWait as e:
            wait = e.seconds
            LOGGER(__name__).warning(
                f"⚠️ Telethon FloodWait: waiting {wait}s "
                f"({wait // 60}m {wait % 60}s) before retrying..."
            )
            await asyncio.sleep(wait + 5)
        except Exception as e:
            LOGGER(__name__).error(f"Unexpected error starting Telethon: {e}")
            raise


# ─────────────────────────────────────────────────────────────
# Safe Pyrogram start — auto-waits on FloodWait
# ─────────────────────────────────────────────────────────────
async def start_app_safe():
    while True:
        try:
            await app.start()
            LOGGER(__name__).info("✅ Pyrogram app started successfully.")
            break
        except PyroFloodWait as e:
            wait = e.value
            LOGGER(__name__).warning(
                f"⚠️ Pyrogram FloodWait: waiting {wait}s "
                f"({wait // 60}m {wait % 60}s) before retrying..."
            )
            await asyncio.sleep(wait + 5)
        except Exception as e:
            LOGGER(__name__).error(f"Unexpected error starting Pyrogram app: {e}")
            raise


# ─────────────────────────────────────────────────────────────
# Bot initialisation
# ─────────────────────────────────────────────────────────────
async def init_bot():
    if not any([
        config.STRING1, config.STRING2, config.STRING3,
        config.STRING4, config.STRING5,
    ]):
        LOGGER(__name__).error(
            "𝐒𝐭𝐫𝐢𝐧𝐠 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐍𝐨𝐭 𝐅𝐢𝐥𝐥𝐞𝐝, 𝐏𝐥𝐞𝐚𝐬𝐞 𝐅𝐢𝐥𝐥 𝐀 𝐏𝐲𝐫𝐨𝐠𝐫𝐚𝐦 V2 𝐒𝐞𝐬𝐬𝐢𝐨𝐧🤬"
        )

    await sudo()

    try:
        gb = await get_gbanned()
        for u in gb:
            BANNED_USERS.add(u)
        ban = await get_banned_users()
        for u in ban:
            BANNED_USERS.add(u)
    except Exception:
        pass

    await start_app_safe()

    for all_module in ALL_MODULES:
        importlib.import_module("SHASHA_DRUGZ.plugins" + all_module)
    LOGGER("SHASHA_DRUGZ.plugins").info("𝐀𝐥𝐥 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐋𝐨𝐚𝐝𝐞𝐝🥳...")

    await userbot.start()
    await SHASHA.start()
    await SHASHA.decorators()

    LOGGER("SHASHA_DRUGZ").info(
        "\n╔═════════ஜ۩۞۩ஜ════════╗\n"
        "  ☠︎︎ 𝗠𝗔𝗗𝗘 𝗕𝗬 𝗛𝗘𝗔𝗥𝗧𝗕𝗘𝗔𝗧\n"
        "╚═════════ஜ۩۞۩ஜ════════╝\n"
    )


# ─────────────────────────────────────────────────────────────
# Graceful shutdown helper
# ─────────────────────────────────────────────────────────────
async def shutdown():
    """Attempt a clean shutdown of all clients."""
    for coro, label in [
        (telethn.disconnect(), "Telethon"),
        (userbot.stop(),       "Userbot"),
        (app.stop(),           "Pyrogram"),
    ]:
        try:
            await coro
            LOGGER(__name__).info(f"✅ {label} disconnected.")
        except Exception as e:
            LOGGER(__name__).warning(f"⚠️ Error stopping {label}: {e}")


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────
async def main():
    await start_telethn_safe()
    await ensure_indexes()
    load_manual_modules_map()
    await init_bot()

    try:
        await load_movebots()
    except Exception:
        logging.exception("Error while starting movebots.")

    try:
        await restart_bots()
    except Exception:
        logging.exception("Fatal error in restart_bots, but main bot continues.")

    asyncio.create_task(expiry_checker())

    LOGGER("SHASHA_DRUGZ").info(
        "\n\n\n"
        "  ___ ______________   _____ __________________________________________   ________________\n"
        " /   |   \\_   _____/  /  _  \\______   \\__    ___/\\______   \\_   _____/  /  _  \\__    ___/\n"
        "/    ~    \\    __)_  /  /_\\  \\|       _/ |    |    |    |  _/|    __)_  /  /_\\  \\|    |   \n"
        "\\    Y    /        \\/    |    \\    |   \\ |    |    |    |   \\|        \\/    |    \\    |   \n"
        " \\___|_  /_______  /\\____|__  /____|_  / |____|    |______  /_______  /\\____|__  /____|   \n"
        "       \\/        \\/         \\/       \\/                   \\/        \\/         \\/  \n\n\n"
    )

    await idle()
    await shutdown()

    LOGGER("SHASHA_DRUGZ").info(
        "\n╔═════════ஜ۩۞۩ஜ════════╗\n"
        "  ☠︎︎ 𝗠𝗔𝗗𝗘 𝗕𝗬 𝗛𝗘𝗔𝗥𝗧𝗕𝗘𝗔𝗧\n"
        "╚═════════ஜ۩۞۩ஜ════════╝\n"
    )


# ─────────────────────────────────────────────────────────────
# Internal crash-recovery restart loop
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    restart_count = 0

    LOGGER(__name__).info("🔁 Internal AutoRestart system active.")

    while True:
        try:
            # Always create a fresh event loop on each restart to avoid
            # "Event loop is closed" errors after a crash.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            loop.run_until_complete(main())

            # If main() returned normally (clean idle stop), exit without restarting.
            LOGGER(__name__).info("✅ Bot exited cleanly. Shutting down.")
            break

        except KeyboardInterrupt:
            LOGGER(__name__).info("🛑 Bot stopped manually (KeyboardInterrupt).")
            break

        except Exception as e:
            restart_count += 1
            LOGGER(__name__).error(
                f"💥 Bot crashed with error: {e}\n"
                f"🔁 Restarting in {RESTART_DELAY}s... (restart #{restart_count})"
            )

            if MAX_RESTARTS and restart_count >= MAX_RESTARTS:
                LOGGER(__name__).error(
                    f"🛑 Reached max restarts ({MAX_RESTARTS}). Stopping."
                )
                break

            time.sleep(RESTART_DELAY)

        finally:
            # Always close the old loop cleanly before the next iteration.
            try:
                loop.close()
            except Exception:
                pass
