# =========================================================
# SHASHA_DRUGZ - RAM + CACHE GUARD  (v2)
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
# SETTINGS
# =========================================================

CHECK_INTERVAL  = 300   # How often to check (seconds) — default: 5 mins
MAX_RAM_MB      = 450   # Force restart above this (MB)
WARN_RAM_MB     = 380   # Log warning above this (MB)
CPU_WARN        = 85    # Log CPU warning above this (%)
MAX_FILE_AGE    = 1800  # Only delete files older than this (seconds) — 30 mins

# Folders to scan for junk files
CACHE_FOLDERS = [
    "downloads",
    "cache",
    "temp",
    "downloads/thumb",
    "/tmp",
]

# Only these file types will ever be deleted
DELETE_EXTENSIONS = (
    ".mp3", ".mp4", ".mkv", ".webm",
    ".jpg", ".jpeg", ".png", ".webp",
    ".part", ".temp", ".ytdl",
    ".aac", ".ogg", ".flac", ".m4a",
)

# =========================================================
# ACTIVE DOWNLOAD TRACKER
# Import ACTIVE_DOWNLOADS in your downloader module and
# add/remove file paths to protect files mid-stream.
#
# Usage in your downloader:
#   from SHASHA_DRUGZ.utils.ram_guard import ACTIVE_DOWNLOADS
#   ACTIVE_DOWNLOADS.add(file_path)
#   ...download/stream...
#   ACTIVE_DOWNLOADS.discard(file_path)
# =========================================================

ACTIVE_DOWNLOADS: set = set()

# =========================================================
# INTERNALS
# =========================================================

PROCESS = psutil.Process(os.getpid())

# Load libc once for malloc_trim
try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None


def get_ram_mb() -> float:
    """Return current RAM usage in MB."""
    return PROCESS.memory_info().rss / 1024 / 1024


def get_cpu_percent() -> float:
    """Return current CPU usage % of this process."""
    return PROCESS.cpu_percent(interval=1)


def malloc_trim():
    """
    Return unused memory pages back to Linux kernel.
    Very effective inside Docker / Railway containers.
    """
    if _libc:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def force_gc():
    """Force Python garbage collection + malloc_trim."""
    try:
        collected = gc.collect()
        malloc_trim()
        LOGGER.info(f"[RAM_GUARD] GC collected {collected} object(s).")
    except Exception as e:
        LOGGER.error(f"[RAM_GUARD] GC error: {e}")


def clear_cache() -> int:
    """
    Delete old temp/cache media files safely.
    Rules:
      - Only files older than MAX_FILE_AGE seconds
      - Only allowed extensions
      - Skips files currently in ACTIVE_DOWNLOADS
      - Never touches .session / .db / code files
    Returns count of deleted files.
    """
    deleted = 0
    now = time.time()

    for folder in CACHE_FOLDERS:
        path = Path(folder)
        if not path.exists():
            continue

        try:
            for file in path.rglob("*"):
                if not file.is_file():
                    continue

                # Only allowed extensions
                if file.suffix.lower() not in DELETE_EXTENSIONS:
                    continue

                # Skip files being actively downloaded/streamed
                if str(file) in ACTIVE_DOWNLOADS:
                    LOGGER.info(f"[RAM_GUARD] Skipped active file: {file.name}")
                    continue

                # Only delete files older than MAX_FILE_AGE
                try:
                    age = now - file.stat().st_mtime
                except Exception:
                    continue

                if age < MAX_FILE_AGE:
                    continue

                # Safe to delete
                try:
                    file.unlink(missing_ok=True)
                    deleted += 1
                except Exception:
                    pass  # File in use — skip silently

        except Exception as e:
            LOGGER.error(f"[RAM_GUARD] Cache scan error in '{folder}': {e}")

    LOGGER.info(f"[RAM_GUARD] Cleared {deleted} old cache file(s).")
    return deleted


def rebuild_folders():
    """Re-create cache folders after cleanup so downloads don't break."""
    for folder in CACHE_FOLDERS:
        if folder == "/tmp":
            continue
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            pass


def get_status_report() -> str:
    """Human-readable RAM status line."""
    ram = get_ram_mb()
    if ram >= MAX_RAM_MB:
        label = "🔴 CRITICAL"
    elif ram >= WARN_RAM_MB:
        label = "🟡 WARNING"
    else:
        label = "🟢 OK"
    return f"[RAM_GUARD] RAM: {ram:.1f} MB — {label}"


# =========================================================
# MAIN LOOP
# =========================================================

async def ram_guard_loop():
    """
    Background task. Runs every CHECK_INTERVAL seconds.
    Handles:
      - RAM monitoring + warnings
      - CPU spike detection
      - Garbage collection + malloc_trim
      - Old cache file cleanup (skips active downloads)
      - Graceful restart before Railway OOM-kills the bot
    """
    LOGGER.info(
        f"[RAM_GUARD] Started — interval: {CHECK_INTERVAL // 60} min(s) | "
        f"RAM limit: {MAX_RAM_MB} MB | File age limit: {MAX_FILE_AGE // 60} min(s)."
    )

    while True:
        try:
            ram = get_ram_mb()
            cpu = get_cpu_percent()

            LOGGER.info(get_status_report())

            # ---- CPU Warning ----
            if cpu >= CPU_WARN:
                LOGGER.warning(
                    f"[RAM_GUARD] High CPU: {cpu:.1f}% — "
                    "possible ffmpeg/yt-dlp spike."
                )

            # ---- Routine cleanup ----
            force_gc()
            clear_cache()
            rebuild_folders()

            # ---- CRITICAL: graceful restart before Railway OOM ----
            if ram >= MAX_RAM_MB:
                LOGGER.warning(
                    f"[RAM_GUARD] RAM at {ram:.1f} MB — exceeds {MAX_RAM_MB} MB. "
                    "Restarting safely..."
                )
                force_gc()
                clear_cache()
                await asyncio.sleep(3)
                os._exit(1)  # Railway auto-restarts the container

            # ---- Extra GC when approaching limit ----
            elif ram >= WARN_RAM_MB:
                LOGGER.warning(
                    f"[RAM_GUARD] RAM at {ram:.1f} MB — approaching limit. "
                    "Running extra GC."
                )
                force_gc()
                force_gc()

        except Exception as e:
            LOGGER.error(f"[RAM_GUARD] Loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
