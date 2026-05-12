# =========================================================
# SHASHA_DRUGZ - RAM + CACHE GUARD  (v3 - Final)
# Optimized for Railway Free Tier
# =========================================================

import os
import gc
import time
import ctypes
import psutil
import asyncio
import logging
from pathlib import Path

LOGGER = logging.getLogger("SHASHA_RAM")

# =========================================================
# SETTINGS  —  edit these to match your setup
# =========================================================

CHECK_INTERVAL = 300    # RAM check frequency in seconds (default: 5 min)
MAX_RAM_MB     = 450    # Force restart if RAM exceeds this (MB)
WARN_RAM_MB    = 380    # Log a warning at this level (MB)
CPU_WARN       = 85     # Log a CPU warning above this % usage
MAX_FILE_AGE   = 1800   # Only delete files older than this (seconds = 30 min)

# Folders to scan and clean
CACHE_FOLDERS = [
    "downloads",
    "cache",
    "temp",
    "downloads/thumb",
    "/tmp",
]

# Only these file extensions are ever deleted — nothing else is touched
DELETE_EXTENSIONS = frozenset({
    ".mp3", ".mp4", ".mkv", ".webm",
    ".jpg", ".jpeg", ".png", ".webp",
    ".part", ".temp", ".ytdl",
    ".aac", ".ogg", ".flac", ".m4a",
})

# =========================================================
# ACTIVE DOWNLOAD TRACKER
#
# Import this set in your downloader/music modules to
# protect files that are currently being downloaded or streamed.
#
# Usage:
#   from SHASHA_DRUGZ.utils.ram_guard import ACTIVE_DOWNLOADS
#
#   ACTIVE_DOWNLOADS.add(file_path)      # before download starts
#   ...do download / ffmpeg / stream...
#   ACTIVE_DOWNLOADS.discard(file_path)  # after done
#
# The cleaner will SKIP any file path present in this set.
# =========================================================

ACTIVE_DOWNLOADS: set = set()

# =========================================================
# INTERNALS
# =========================================================

_PROCESS = psutil.Process(os.getpid())

# Try to load libc for malloc_trim (Linux / Railway / Docker only)
try:
    _libc = ctypes.CDLL("libc.so.6")
    _HAS_LIBC = True
except Exception:
    _libc = None
    _HAS_LIBC = False


# ----------------------------------------------------------
# Metrics
# ----------------------------------------------------------

def get_ram_mb() -> float:
    """Current RAM usage of this process in MB."""
    return _PROCESS.memory_info().rss / 1024 / 1024


def get_cpu_percent() -> float:
    """Current CPU usage % of this process (1-second sample)."""
    return _PROCESS.cpu_percent(interval=1)


# ----------------------------------------------------------
# Memory helpers
# ----------------------------------------------------------

def _malloc_trim() -> None:
    """
    Ask the Linux kernel to reclaim unused heap pages.
    Very effective inside Docker / Railway containers.
    No-op on non-Linux platforms.
    """
    if _HAS_LIBC:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def force_gc() -> int:
    """
    Force Python garbage collection, then call malloc_trim.
    Returns the number of objects collected.
    """
    try:
        count = gc.collect()
        _malloc_trim()
        #LOGGER.info(f"[RAM_GUARD] GC collected {count} object(s); malloc_trim done.")
        return count
    except Exception as exc:
        LOGGER.error(f"[RAM_GUARD] GC error: {exc}")
        return 0


# ----------------------------------------------------------
# Cache cleaner
# ----------------------------------------------------------

def clear_cache() -> int:
    """
    Delete stale temp / cache media files.

    Safety rules (ALL must pass before a file is deleted):
      1. Extension must be in DELETE_EXTENSIONS
      2. File must NOT be in ACTIVE_DOWNLOADS
      3. File must be older than MAX_FILE_AGE seconds
      4. .session / .db / code files are never touched

    Returns count of deleted files.
    """
    deleted = 0
    now     = time.time()

    for folder in CACHE_FOLDERS:
        path = Path(folder)
        if not path.exists():
            continue

        try:
            for file in path.rglob("*"):

                if not file.is_file():
                    continue

                # Rule 1 — allowed extension only
                if file.suffix.lower() not in DELETE_EXTENSIONS:
                    continue

                # Rule 2 — skip active downloads / streams
                if str(file) in ACTIVE_DOWNLOADS:
                    LOGGER.debug(f"[RAM_GUARD] Skipped active file: {file.name}")
                    continue

                # Rule 3 — only old files
                try:
                    age = now - file.stat().st_mtime
                except OSError:
                    continue

                if age < MAX_FILE_AGE:
                    continue

                # All rules passed — safe to remove
                try:
                    file.unlink(missing_ok=True)
                    deleted += 1
                except OSError:
                    pass  # file in use or already gone — skip silently

        except Exception as exc:
            LOGGER.error(f"[RAM_GUARD] Scan error in '{folder}': {exc}")

    #LOGGER.info(f"[RAM_GUARD] Removed {deleted} old cache file(s).")
    return deleted


def rebuild_folders() -> None:
    """Re-create expected cache folders so downloads never fail after cleanup."""
    for folder in CACHE_FOLDERS:
        if folder == "/tmp":
            continue   # system-managed — never touch
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass


# ----------------------------------------------------------
# Status
# ----------------------------------------------------------

def status_line() -> str:
    """One-line human-readable RAM status for logs."""
    ram = get_ram_mb()
    if   ram >= MAX_RAM_MB:  badge = "🔴 CRITICAL"
    elif ram >= WARN_RAM_MB: badge = "🟡 WARNING"
    else:                    badge = "🟢 OK"
    return #f"[RAM_GUARD] RAM: {ram:.1f} MB — {badge}"


# =========================================================
# MAIN BACKGROUND LOOP
# =========================================================

async def ram_guard_loop() -> None:
    """
    Asyncio background task — call once at startup:

        asyncio.create_task(ram_guard_loop())

    Every CHECK_INTERVAL seconds this task:
      • Logs RAM + CPU usage
      • Runs gc.collect() + malloc_trim
      • Deletes old cache/temp files (safely)
      • Re-creates empty cache folders
      • Warns when RAM approaches the limit
      • Calls os._exit(1) if RAM exceeds MAX_RAM_MB
        so Railway auto-restarts the container cleanly
        before it gets OOM-killed forcefully.
    """
    LOGGER.info(
        f"[RAM_GUARD] Started ✅ | "
        f"check every {CHECK_INTERVAL // 60}m | "
        f"warn >{WARN_RAM_MB} MB | "
        f"restart >{MAX_RAM_MB} MB | "
        f"file age >{MAX_FILE_AGE // 60}m | "
        f"malloc_trim {'on' if _HAS_LIBC else 'off (non-Linux)'}"
    )

    while True:
        try:
            ram = get_ram_mb()
            cpu = get_cpu_percent()

            # ── Status log ──────────────────────────────
            LOGGER.info(status_line())

            # ── CPU spike warning ────────────────────────
            if cpu >= CPU_WARN:
                LOGGER.warning(
                    f"[RAM_GUARD] High CPU: {cpu:.1f}% "
                    "(possible ffmpeg / yt-dlp spike)"
                )

            # ── Routine cleanup ──────────────────────────
            force_gc()
            clear_cache()
            rebuild_folders()

            # ── CRITICAL — graceful restart ──────────────
            if ram >= MAX_RAM_MB:
                LOGGER.warning(
                    #f"[RAM_GUARD] RAM at {ram:.1f} MB exceeds limit "
                    f"({MAX_RAM_MB} MB). Performing safe restart..."
                )
                force_gc()
                clear_cache()
                await asyncio.sleep(3)   # let pending tasks settle
                os._exit(1)             # Railway restarts the container

            # ── Approaching limit — extra GC ─────────────
            elif ram >= WARN_RAM_MB:
                LOGGER.warning(
                    f"[RAM_GUARD] RAM at {ram:.1f} MB — "
                    "approaching limit, running extra GC."
                )
                force_gc()
                force_gc()

        except Exception as exc:
            LOGGER.error(f"[RAM_GUARD] Loop error: {exc}")

        await asyncio.sleep(CHECK_INTERVAL)
