# SHASHA_DRUGZ/plugins/sudo/PRIMESUDO/lscpu.py

import asyncio
import os
import platform
import shutil
import subprocess
import sys
from typing import Dict

from pyrogram import filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.decorators.language import language


def _run_cmd(cmd: list) -> str:
    """Blocking helper — run a command and return decoded output."""
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return out.decode(errors="ignore").strip()
    except Exception:
        return ""


def _parse_proc_cpuinfo() -> Dict[str, str]:
    """Fallback parser for /proc/cpuinfo (Linux)."""
    info: Dict[str, str] = {}
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
    except Exception:
        return info

    for line in data.splitlines():
        if ":" not in line:
            continue
        k, v = map(str.strip, line.split(":", 1))
        if k in (
            "model name", "cpu MHz", "vendor_id",
            "flags", "cache size", "processor",
        ):
            info.setdefault(k, v)
    return info


def _read_file_first_line(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readline().strip()
    except Exception:
        return ""


def _parse_meminfo() -> Dict[str, int]:
    """
    Parse /proc/meminfo and return a dict of key → value_in_kB.
    Example keys: MemTotal, MemFree, MemAvailable, SwapTotal, SwapFree.
    Returns an empty dict if /proc/meminfo is unavailable.
    """
    result: Dict[str, int] = {}
    if not os.path.exists("/proc/meminfo"):
        return result
    try:
        with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    try:
                        result[key] = int(parts[1])   # value is in kB
                    except ValueError:
                        pass
    except Exception:
        pass
    return result


def blocking_gather_system_info() -> Dict[str, str]:
    """Blocking function — gathers system info using lscpu or fallbacks."""
    out: Dict[str, str] = {}

    # ── Basic platform ────────────────────────────────────────────
    out["OS"]       = f"{platform.system()} {platform.release()} ({platform.version()})"
    out["Platform"] = platform.platform()
    out["Python"]   = f"{platform.python_implementation()} {platform.python_version()}"

    # ── PaaS environment detection ────────────────────────────────
    out["Platform-Env"] = (
        ", ".join(
            name
            for name in (
                "DYNO"    if os.environ.get("DYNO") else "",
                "RAILWAY" if (
                    os.environ.get("RAILWAY_ENVIRONMENT")
                    or os.environ.get("RAILWAY")
                ) else "",
                "RENDER"  if os.environ.get("RENDER") else "",
                "HEROKU"  if (
                    os.environ.get("PORT") and os.environ.get("DYNO")
                ) else "",
            )
            if name
        )
        or "self-host / unknown"
    )

    # ── CPU (lscpu or /proc/cpuinfo fallback) ─────────────────────
    lscpu = _run_cmd(["lscpu"])
    if lscpu:
        keep_keys = (
            "Architecture", "CPU(s)", "Model name",
            "Thread(s) per core", "Core(s) per socket", "Socket(s)",
            "Vendor ID", "CPU max MHz", "CPU min MHz",
            "L1d cache", "L1i cache", "L2 cache", "L3 cache",
        )
        lines = []
        for line in lscpu.splitlines():
            for k in keep_keys:
                if line.startswith(k + ":"):
                    lines.append(line.strip())
                    break
        out["CPU"] = "\n".join(lines) if lines else lscpu[:2000]
    else:
        cpuinfo = _parse_proc_cpuinfo()
        if cpuinfo:
            cpu_lines = []
            if "model name" in cpuinfo:
                cpu_lines.append(f"Model : {cpuinfo['model name']}")
            if "vendor_id" in cpuinfo:
                cpu_lines.append(f"Vendor: {cpuinfo['vendor_id']}")
            if "cpu MHz" in cpuinfo:
                cpu_lines.append(f"MHz   : {cpuinfo['cpu MHz']}")
            if "cache size" in cpuinfo:
                cpu_lines.append(f"Cache : {cpuinfo['cache size']}")
            out["CPU"] = "\n".join(cpu_lines) or "cpuinfo available"
        else:
            out["CPU"] = "No lscpu or /proc/cpuinfo available"

    # ── RAM (total + used, in MB and GB) ──────────────────────────
    meminfo = _parse_meminfo()
    if meminfo:
        total_kb     = meminfo.get("MemTotal",     0)
        available_kb = meminfo.get("MemAvailable", 0)
        used_kb      = total_kb - available_kb

        total_mb = round(total_kb  / 1024,         2)
        used_mb  = round(used_kb   / 1024,         2)
        free_mb  = round(available_kb / 1024,      2)

        total_gb = round(total_kb  / (1024 * 1024), 2)
        used_gb  = round(used_kb   / (1024 * 1024), 2)
        free_gb  = round(available_kb / (1024 * 1024), 2)

        out["Memory"] = (
            f"Total : {total_mb} MB  ({total_gb} GB)\n"
            f"Used  : {used_mb}  MB  ({used_gb}  GB)\n"
            f"Free  : {free_mb}  MB  ({free_gb}  GB)"
        )

        # SWAP if available
        swap_total_kb = meminfo.get("SwapTotal", 0)
        swap_free_kb  = meminfo.get("SwapFree",  0)
        swap_used_kb  = swap_total_kb - swap_free_kb
        if swap_total_kb > 0:
            out["Swap"] = (
                f"Total : {round(swap_total_kb/1024,2)} MB  "
                f"({round(swap_total_kb/(1024*1024),2)} GB)\n"
                f"Used  : {round(swap_used_kb/1024,2)}  MB  "
                f"({round(swap_used_kb/(1024*1024),2)}  GB)"
            )
        else:
            out["Swap"] = "No swap configured"
    else:
        # Non-Linux fallback via shutil (no RAM usage available this way)
        try:
            import psutil as _ps
            m = _ps.virtual_memory()
            total_mb = round(m.total / (1024**2), 2)
            used_mb  = round(m.used  / (1024**2), 2)
            free_mb  = round(m.available / (1024**2), 2)
            total_gb = round(m.total / (1024**3), 2)
            used_gb  = round(m.used  / (1024**3), 2)
            free_gb  = round(m.available / (1024**3), 2)
            out["Memory"] = (
                f"Total : {total_mb} MB  ({total_gb} GB)\n"
                f"Used  : {used_mb}  MB  ({used_gb}  GB)\n"
                f"Free  : {free_mb}  MB  ({free_gb}  GB)"
            )
        except Exception:
            out["Memory"] = "N/A (non-Linux, /proc/meminfo not available)"

    # ── Disk usage ────────────────────────────────────────────────
    try:
        total, used, free = shutil.disk_usage("/")
        out["Disk"] = (
            f"Total: {round(total/(1024**3),2)} GB  |  "
            f"Used: {round(used/(1024**3),2)} GB  |  "
            f"Free: {round(free/(1024**3),2)} GB"
        )
    except Exception:
        out["Disk"] = "unknown"

    # ── Uptime ────────────────────────────────────────────────────
    if os.path.exists("/proc/uptime"):
        try:
            with open("/proc/uptime", "r", encoding="utf-8", errors="ignore") as f:
                up = float(f.readline().split()[0])
            hours = int(up // 3600)
            mins  = int((up % 3600) // 60)
            secs  = int(up % 60)
            out["Uptime"] = f"{hours}h {mins}m {secs}s"
        except Exception:
            out["Uptime"] = "unknown"
    else:
        up_cmd = _run_cmd(["uptime", "-p"])
        out["Uptime"] = up_cmd or "unknown"

    # ── Container/cgroup hints ────────────────────────────────────
    cgroup = (
        _read_file_first_line("/proc/1/cgroup")
        if os.path.exists("/proc/1/cgroup")
        else ""
    )
    out["Container"] = (
        "likely (docker/k8s)"
        if ("docker" in cgroup or "kubepods" in cgroup)
        else "no obvious container marker"
    )

    # ── uname ─────────────────────────────────────────────────────
    uname = _run_cmd(["uname", "-a"])
    if uname:
        out["uname"] = uname

    # ── Logical CPU count ─────────────────────────────────────────
    out["Logical-CPUs"] = str(os.cpu_count() or "unknown")

    return out


@app.on_message(
    filters.command(
        ["lscpu"], prefixes=["/", "!", "%", ",", "", ".", "@", "#"]
    )
    & SUDOERS
)
@language
async def lscpu_cmd(client, message: Message, _):
    """Sudo-only /lscpu — gathers server specs and replies with a concise report."""
    status = await message.reply_text(
        _("server_please_wait")
        if _ and "server_please_wait" in _
        else "⏳ Gathering server info..."
    )
    loop = asyncio.get_event_loop()
    try:
        info = await asyncio.wait_for(
            loop.run_in_executor(None, blocking_gather_system_info),
            timeout=30,
        )
    except asyncio.TimeoutError:
        await status.edit_text("<code>Timed out while gathering system info.</code>")
        return
    except Exception as e:
        await status.edit_text(f"<code>{e}</code>")
        return

    # ── Build readable message ────────────────────────────────────
    parts = [
        f"<b>OS</b>: <code>{info.get('OS')}</code>",
        f"<b>Platform</b>: <code>{info.get('Platform')}</code>",
        f"<b>Python</b>: <code>{info.get('Python')}</code>",
        f"<b>Platform-Env</b>: <code>{info.get('Platform-Env')}</code>",
        f"<b>Logical CPUs</b>: <code>{info.get('Logical-CPUs')}</code>",
        "<b>CPU</b>:\n<pre>{}</pre>".format(info.get("CPU", "")),
        "<b>RAM</b>:\n<pre>{}</pre>".format(info.get("Memory", "N/A")),
        "<b>Swap</b>:\n<pre>{}</pre>".format(info.get("Swap", "N/A")),
        f"<b>Disk</b>: <code>{info.get('Disk')}</code>",
        f"<b>Uptime</b>: <code>{info.get('Uptime')}</code>",
        f"<b>Container</b>: <code>{info.get('Container')}</code>",
    ]
    if info.get("uname"):
        parts.append(f"<b>uname</b>: <code>{info['uname']}</code>")

    text = "\n\n".join(parts)

    # Trim if too long for Telegram
    if len(text) > 4000:
        cpu = info.get("CPU", "")
        if len(cpu) > 800:
            cpu = cpu[:800] + "\n... (truncated)"
        parts[5] = "<b>CPU</b>:\n<pre>{}</pre>".format(cpu)
        text = "\n\n".join(parts)

    await message.reply_text(text, disable_web_page_preview=True)
    await status.delete()


__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__     = """
🔻 /lscpu ➠ Show detailed server/system specs: OS, platform, Python version,
logical CPUs, CPU info, RAM (MB & GB), Swap, disk usage, uptime, container info.
"""
