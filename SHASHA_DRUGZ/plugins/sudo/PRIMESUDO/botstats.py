import os
import psutil
import socket
import platform
import time
import asyncio
import speedtest
import shutil
from datetime import datetime

from pyrogram import filters, __version__ as pyrover
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import MONGO_DB_URI
from motor.motor_asyncio import AsyncIOMotorClient

START_TIME = time.time()   # Bot start time

# ---------- SUDO FILTER ----------
def sudo_filter(_, __, message: Message):
    return message.from_user and message.from_user.id in SUDOERS

sudo_only = filters.create(sudo_filter)

# ---------- READABLE TIME ----------
def get_readable_time(seconds: int) -> str:
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    out = []
    for name, count in periods:
        value = seconds // count
        if value:
            seconds -= value * count
            out.append(f"{value}{name}")
    return " ".join(out) or "0s"

# ---------- FOLDER SIZE ----------
def get_folder_size(path: str) -> float:
    """Returns folder size in MB."""
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    return round(total_size / (1024 * 1024), 2)

# ---------- MONGODB STATUS ----------
async def mongo_status() -> str:
    try:
        client = AsyncIOMotorClient(MONGO_DB_URI)
        await client.server_info()
        return "🟢 Connected"
    except Exception:
        return "🔴 Failed"

# ---------- SPEEDTEST ----------
async def get_speed():
    try:
        st = speedtest.Speedtest()
        download = round(st.download() / 1_000_000, 2)
        upload   = round(st.upload()   / 1_000_000, 2)
        return download, upload
    except Exception:
        return 0, 0

# ---------- TOP PROCESSES ----------
def get_top_processes() -> str:
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            processes.append(proc.info)
        except Exception:
            pass
    processes.sort(key=lambda x: x["cpu_percent"], reverse=True)
    lines = ""
    for p in processes[:5]:
        lines += f"• {p['name']} (PID {p['pid']}): {p['cpu_percent']}%\n"
    return lines

# ---------- MAIN HANDLER ----------
@app.on_message(filters.command("botstats") & sudo_only)
async def botstats_handler(client, message: Message):
    uptime = get_readable_time(int(time.time() - START_TIME))
    uname  = platform.uname()

    # ── CPU ──────────────────────────────────────────────────────
    cpu  = psutil.cpu_percent(interval=1)
    load1, load5, load15 = psutil.getloadavg()

    # CPU temperature (may be N/A on some VPS)
    try:
        temp = psutil.sensors_temperatures()["coretemp"][0].current
    except Exception:
        temp = "N/A"

    # ── RAM ──────────────────────────────────────────────────────
    mem           = psutil.virtual_memory()
    ram_percent   = mem.percent
    ram_total_mb  = round(mem.total / (1024 ** 2), 2)
    ram_used_mb   = round(mem.used  / (1024 ** 2), 2)
    ram_free_mb   = round(mem.available / (1024 ** 2), 2)
    ram_total_gb  = round(mem.total / (1024 ** 3), 2)
    ram_used_gb   = round(mem.used  / (1024 ** 3), 2)
    ram_free_gb   = round(mem.available / (1024 ** 3), 2)

    # ── SWAP ─────────────────────────────────────────────────────
    swap          = psutil.swap_memory()
    swap_percent  = swap.percent
    swap_total_mb = round(swap.total / (1024 ** 2), 2)
    swap_used_mb  = round(swap.used  / (1024 ** 2), 2)
    swap_total_gb = round(swap.total / (1024 ** 3), 2)
    swap_used_gb  = round(swap.used  / (1024 ** 3), 2)

    # ── DISK ─────────────────────────────────────────────────────
    disk = psutil.disk_usage("/").percent

    # ── NETWORK ──────────────────────────────────────────────────
    ipv4 = socket.gethostbyname(socket.gethostname())
    ipv6 = "N/A"
    try:
        ipv6 = socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET6
        )[0][4][0]
    except Exception:
        pass

    SHASHA_DRUGZ_size = get_folder_size("SHASHA_DRUGZ")
    mongo             = await mongo_status()
    download, upload  = await get_speed()
    top_process       = get_top_processes()

    text = f"""
**🤖 BOT SYSTEM STATS**

**⏳ Runtime**
• Uptime: `{uptime}`

**🖥 System Info**
• OS      : `{uname.system} {uname.release}`
• Machine : `{uname.machine}`
• Python  : `{platform.python_version()}`
• Pyrogram: `{pyrover}`
• Hostname: `{socket.gethostname()}`

**🌍 Network**
• IPv4           : `{ipv4}`
• IPv6           : `{ipv6}`
• Download Speed : `{download} Mbps`
• Upload Speed   : `{upload} Mbps`

**🗄 Storage**
• Disk Usage       : `{disk}%`
• SHASHA_DRUGZ Dir : `{SHASHA_DRUGZ_size} MB`

**🔋 Performance**
• CPU       : `{cpu}%`
• Load Avg  : `{load1} | {load5} | {load15}`
• CPU Temp  : `{temp}°C`

**💾 RAM**
• Usage     : `{ram_percent}%`
• Used      : `{ram_used_mb} MB  ({ram_used_gb} GB)`
• Free      : `{ram_free_mb} MB  ({ram_free_gb} GB)`
• Total     : `{ram_total_mb} MB  ({ram_total_gb} GB)`

**🔄 SWAP**
• Usage     : `{swap_percent}%`
• Used      : `{swap_used_mb} MB  ({swap_used_gb} GB)`
• Total     : `{swap_total_mb} MB  ({swap_total_gb} GB)`

**🧠 MongoDB**
• Status: {mongo}

**📋 Processes (Top 5 CPU)**
{top_process}
"""

    await message.reply_text(text)


__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__     = """
🔻 /botstats ➠ ᴅɪsᴘʟᴀʏ ᴅᴇᴛᴀɪʟᴇᴅ sʏsᴛᴇᴍ ᴀɴᴅ ʙᴏᴛ sᴛᴀᴛs
"""
