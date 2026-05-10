# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Youtube.py — SHASHA_DRUGZ  ·  FINAL MERGED VERSION + LIVE STREAM SUPPORT  ║
# ║                                                                              ║
# ║  Download chain : API → cookies.txt → auto-generated browser cookies        ║
# ║  On bot/auth    : cookies wiped & regenerated INFINITELY until success      ║
# ║  No email/password used anywhere                                             ║
# ║                                                                              ║
# ║  Live Streams   : /live/ URLs + ?v= live detection supported                ║
# ║    Detection    : duration_min = None/0 → treat as live                     ║
# ║    Method       : yt-dlp with format=best/bestaudio (HLS manifest)          ║
# ║    live_stream(): returns direct HLS/manifest URL for pytgcalls              ║
# ║                                                                              ║
# ║  Progress bar   : shown in group chats during /play /vplay downloads        ║
# ║    Format:                                                                   ║
# ║      Song Nam.. (13 chars)                                                   ║
# ║      🎵 [▓▓▓▓▓▓░░░░] 61%                                                    ║
# ║      24MB/40MB • 2.1MB/s • ETA 6s                                           ║
# ║                                                                              ║
# ║  Log messages   :                                                            ║
# ║    Blocked  → 🚫 Amazon/AWS IP Detected                                     ║
# ║    Success  → 🌐 YouTube Cookies Extracted (with IP / Location / ISP)       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
import asyncio
import os
import re
import glob
import random
import time
import datetime
import logging
from typing import Union, Optional, Tuple
import aiohttp
import yt_dlp
from playwright.async_api import async_playwright
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
try:
    from youtubesearchpython.__future__ import VideosSearch
except ImportError:
    from py_yt import VideosSearch
from SHASHA_DRUGZ import app, LOGGER
from SHASHA_DRUGZ.utils.formatters import time_to_seconds
from config import LOG_GROUP_ID
# ══════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENT / CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
API_URL  = os.getenv("API_URL", "").rstrip("/") #,
API_KEY  = os.getenv("API_KEY", "")
PLAY_URL = os.getenv(
    "PLAY_URL", "https://youtu.be/ip8o5hDFLhI?si=jCdWYdBAEulr2b49")
ENABLE_YT_COOKIES    = os.getenv("ENABLE_YT_COOKIES",  "true").lower() == "true"
AUTO_REFRESH_COOKIES = True
YTDLP_PROXIES        = os.getenv("YTDLP_PROXIES",      "")
PLAYWRIGHT_PROXIES   = os.getenv("PLAYWRIGHT_PROXIES",  "")
# How often (seconds) the IP-quality background watcher polls
IP_POLL_INTERVAL = int(os.getenv("IP_POLL_INTERVAL", "60"))
# API retries (hard cap — API should be reliable)
MAX_API_RETRIES   = 3
# Give up only after this many *consecutive* non-auth yt-dlp errors
MAX_NON_AUTH_ERRS = 5
# Progress bar update throttle (seconds) — avoids Telegram flood-wait
PROGRESS_UPDATE_INTERVAL = 3
# ── Directories ───────────────────────────────────────────────────────────────
DOWNLOAD_DIR           = os.path.join(os.getcwd(), "downloads")
COOKIES_DIR            = os.path.join(os.getcwd(), "cookies")
PLAYWRIGHT_PROFILE_DIR = os.path.join(os.getcwd(), "playwright_profile")
YT_CACHE_DIR           = os.path.join(os.getcwd(), "ytcache")
for _d in (DOWNLOAD_DIR, COOKIES_DIR, PLAYWRIGHT_PROFILE_DIR, YT_CACHE_DIR):
    os.makedirs(_d, exist_ok=True)
# Single cookie file — only ONE kept at a time
COOKIE_FILE = os.path.join(COOKIES_DIR, "youtube_cookies.txt")
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
_COOKIE_LOCK       = asyncio.Lock()   # only ONE generation at a time
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
# ══════════════════════════════════════════════════════════════════════════════
#  BLOCKED ORG KEYWORDS  (Amazon / AWS only)
# ══════════════════════════════════════════════════════════════════════════════
BLOCKED_ORG_KEYWORDS = [
    "amazon", "amazon.com", "amazon technologies", "amazon data services",
    "amazon cloudfront", "amazon web services", "aws", "as16509", "as14618",
]
_IS_BLOCKED_IP:   bool = False
_CURRENT_IP_INFO: dict = {}
_GOOD_IP_EVENT         = None   # asyncio.Event — lazy-init inside running loop
def _good_ip_event() -> asyncio.Event:
    global _GOOD_IP_EVENT
    if _GOOD_IP_EVENT is None:
        _GOOD_IP_EVENT = asyncio.Event()
    return _GOOD_IP_EVENT
def is_blocked_ip() -> bool:
    return _IS_BLOCKED_IP
# ══════════════════════════════════════════════════════════════════════════════
#  LOGGER
# ══════════════════════════════════════════════════════════════════════════════
def get_logger(name: str):
    try:
        return LOGGER(name)
    except Exception:
        log = logging.getLogger(name)
        if not log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            log.addHandler(h)
        log.setLevel(logging.INFO)
        return log
logger = get_logger("SHASHA_DRUGZ/platforms/Youtube.py")
# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_proxy_list(proxy_env: str) -> list:
    return [p.strip() for p in proxy_env.split(",") if p.strip()]
YTDLP_PROXY_POOL      = _parse_proxy_list(YTDLP_PROXIES)
PLAYWRIGHT_PROXY_POOL = _parse_proxy_list(PLAYWRIGHT_PROXIES)
def choose_random_proxy(pool: list) -> Optional[str]:
    return random.choice(pool) if pool else None
# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def clear_old_cookies():
    try:
        for f in glob.glob(os.path.join(COOKIES_DIR, "*")):
            try:
                os.remove(f)
            except Exception:
                pass
        logger.warning("🧹 Old YouTube cookies removed")
    except Exception as e:
        logger.error(f"Failed to clear cookies: {e}")
# ══════════════════════════════════════════════════════════════════════════════
#  LOG GROUP HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def send_to_log_group(text: str = None, file_obj=None):
    if not LOG_GROUP_ID:
        return
    try:
        if file_obj and text:
            await app.send_document(
                chat_id=LOG_GROUP_ID, document=file_obj, caption=text)
        elif text:
            await app.send_message(chat_id=LOG_GROUP_ID, text=text)
    except Exception as e:
        logger.error(f"Failed to send to log group: {e}")
async def send_cookie_file_to_log_group(reason: str = ""):
    if not os.path.exists(COOKIE_FILE):
        logger.warning("Cookie file missing — cannot send to log group.")
        return
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    caption = (
        f"🍪 **YouTube Cookie Regenerated**\n\n"
        f"📅 Time   : `{timestamp}`\n"
        f"📄 File   : `youtube_cookies.txt`\n"
        f"📝 Reason : {reason or 'On-demand refresh'}\n\n"
        f"#YouTubeCookies"
    )
    try:
        import pyrogram
        with open(COOKIE_FILE, "rb") as f:
            await app.send_document(
                chat_id=LOG_GROUP_ID,
                document=pyrogram.types.InputFile(f, file_name="youtube_cookies.txt"),
                caption=caption,
            )
        logger.info(f"✅ Cookie sent to log group | reason={reason}")
    except Exception:
        try:
            with open(COOKIE_FILE, "rb") as f:
                await send_to_log_group(text=caption, file_obj=f)
        except Exception as e2:
            logger.error(f"Failed to send cookie file: {e2}")
# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC IP INFO
# ══════════════════════════════════════════════════════════════════════════════
async def get_public_ip_info() -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://ipapi.co/json/",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "ip":      data.get("ip"),
                        "city":    data.get("city"),
                        "country": data.get("country_name"),
                        "org":     data.get("org"),
                    }
    except Exception as e:
        logger.error(f"Failed to fetch IP info: {e}")
    return None
# ══════════════════════════════════════════════════════════════════════════════
#  IP QUALITY CHECK
# ══════════════════════════════════════════════════════════════════════════════
async def check_ip_quality() -> bool:
    global _IS_BLOCKED_IP, _CURRENT_IP_INFO
    info = await get_public_ip_info()
    if not info:
        _IS_BLOCKED_IP   = False
        _CURRENT_IP_INFO = {}
        logger.warning("⚠️ Could not fetch IP info — assuming good IP")
        return True
    _CURRENT_IP_INFO = info
    org = (info.get("org") or "").lower()
    _IS_BLOCKED_IP = any(kw in org for kw in BLOCKED_ORG_KEYWORDS)
    if _IS_BLOCKED_IP:
        _good_ip_event().clear()
        logger.warning(
            f"❌ BLOCKED IP (Amazon/AWS) → {info.get('ip')} | "
            f"Org: {info.get('org')} | "
            f"{info.get('city')}, {info.get('country')}"
        )
    else:
        logger.info(
            f"✅ GOOD IP → {info.get('ip')} | "
            f"Org: {info.get('org')} | "
            f"{info.get('city')}, {info.get('country')}"
        )
    return not _IS_BLOCKED_IP
# ══════════════════════════════════════════════════════════════════════════════
#  WAIT FOR GOOD IP
# ══════════════════════════════════════════════════════════════════════════════
async def wait_for_good_ip() -> None:
    if not _IS_BLOCKED_IP and _good_ip_event().is_set():
        return
    info = _CURRENT_IP_INFO
    logger.info(
        f"⏳ Download queued — waiting for a non-Amazon IP "
        f"(current: {info.get('ip', 'unknown')} / {info.get('org', 'unknown')}) …"
    )
    await _good_ip_event().wait()
    logger.info("✅ Good IP + cookies ready — resuming queued download …")
# ══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND IP WATCHER
# ══════════════════════════════════════════════════════════════════════════════
async def _ip_watcher_loop():
    logger.info(f"🔍 IP watcher started — polling every {IP_POLL_INTERVAL}s …")
    while True:
        await asyncio.sleep(IP_POLL_INTERVAL)
        was_blocked = _IS_BLOCKED_IP
        good        = await check_ip_quality()
        info        = _CURRENT_IP_INFO
        timestamp   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        if was_blocked and good:
            logger.info("🎉 IP changed to GOOD — generating cookies before resuming …")
            await send_to_log_group(
                text=(
                    f"🎉 **Good IP Detected — Generating Cookies**\n\n"
                    f"📅 Time     : `{timestamp}`\n"
                    f"🌍 IP       : `{info.get('ip', 'unknown')}`\n"
                    f"📍 Location : {info.get('city', 'unknown')}, "
                    f"{info.get('country', 'unknown')}\n"
                    f"🏢 Org/ISP  : `{info.get('org', 'unknown')}`\n\n"
                    f"⏳ Generating fresh cookies — downloads resume once ready …\n\n"
                    f"#GoodIP #YouTubeCookies"
                )
            )
            await _run_cookie_startup()
            _good_ip_event().set()
            logger.info("✅ Cookies ready — all queued downloads resuming …")
            await send_to_log_group(
                text=(
                    f"✅ **Services Resumed — Cookies Ready**\n\n"
                    f"📅 Time     : `{timestamp}`\n"
                    f"🌍 IP       : `{info.get('ip', 'unknown')}`\n"
                    f"🏢 Org/ISP  : `{info.get('org', 'unknown')}`\n\n"
                    f"All queued downloads are now resuming automatically.\n\n"
                    f"#GoodIP #Resumed"
                )
            )
        elif not was_blocked and not good:
            logger.warning("😱 IP changed to Amazon/AWS — suspending all downloads …")
            await send_to_log_group(
                text=(
                    f"🚫 **Amazon IP Detected — Services Suspended**\n\n"
                    f"📅 Time     : `{timestamp}`\n"
                    f"🌍 IP       : `{info.get('ip', 'unknown')}`\n"
                    f"📍 Location : {info.get('city', 'unknown')}, "
                    f"{info.get('country', 'unknown')}\n"
                    f"🏢 Org/ISP  : `{info.get('org', 'unknown')}`\n\n"
                    f"❌ YouTube blocks Amazon/AWS IPs.\n"
                    f"⏳ Polling every {IP_POLL_INTERVAL}s until a non-Amazon IP is detected.\n"
                    f"✅ Everything resumes automatically once a good IP appears.\n\n"
                    f"#BlockedIP"
                )
            )
# ══════════════════════════════════════════════════════════════════════════════
#  PLAYWRIGHT PROFILE LOCK CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def cleanup_playwright_profile():
    for fname in ("SingletonLock", "SingletonCookie",
                  "SingletonSocket", "DevToolsActivePort"):
        fpath = os.path.join(PLAYWRIGHT_PROFILE_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                logger.info(f"🧹 Removed stale profile file: {fname}")
            except Exception as e:
                logger.warning(f"Could not remove {fname}: {e}")
# ══════════════════════════════════════════════════════════════════════════════
#  BROWSER PROFILE COOKIE GENERATION
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(
    reason: str = "Profile cookie generation",
) -> bool:
    logger.info(f"🌐 Launching browser profile to generate cookies [{reason}] …")
    await send_to_log_group(
        text=(
            f"🌐 **Browser Profile – Generating Cookies**\n\n"
            f"📝 Reason : {reason}\n"
            f"⏳ Launching headless Chromium …\n\n"
            f"#YouTubeCookies"
        )
    )
    cleanup_playwright_profile()
    proxy      = choose_random_proxy(PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(USER_AGENTS)
    context    = None
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                PLAYWRIGHT_PROFILE_DIR,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                ],
                proxy={"server": proxy} if proxy else None,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
            )
            page = await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)
            try:
                logger.info("🔗 Visiting accounts.google.com …")
                await page.goto("https://accounts.google.com",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(4000)
            except Exception as e:
                logger.warning(f"accounts.google.com warning: {e}")
            try:
                logger.info("🔗 Visiting youtube.com …")
                await page.goto("https://www.youtube.com",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(5000)
                await page.mouse.move(
                    random.randint(100, 600), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1500))
                await page.mouse.wheel(0, random.randint(300, 800))
                await page.wait_for_timeout(random.randint(500, 1000))
            except Exception as e:
                logger.warning(f"youtube.com warning: {e}")
            if PLAY_URL:
                try:
                    logger.info(f"🎬 Priming session with PLAY_URL: {PLAY_URL}")
                    await page.goto(PLAY_URL,
                                    wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(6000)
                    await page.mouse.move(
                        random.randint(100, 800), random.randint(100, 500))
                    await page.mouse.wheel(0, random.randint(200, 500))
                    await page.wait_for_timeout(random.randint(1000, 2000))
                except Exception as e:
                    logger.warning(f"PLAY_URL prime warning: {e}")
            try:
                await page.goto("https://www.youtube.com/feed/trending",
                                wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)
            except Exception:
                pass
            await context.close()
            logger.info("✅ Browser profile cookies refreshed successfully")
            return True
    except Exception as e:
        logger.error(f"❌ Playwright cookie generation error: {str(e)[:300]}")
        if context:
            try:
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Browser Profile – Cookie Generation Failed**\n\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n\n"
                f"#YouTubeCookies"
            )
        )
        return False
# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACT COOKIES FROM BROWSER PROFILE
# ══════════════════════════════════════════════════════════════════════════════
async def _extract_cookies_from_profile() -> bool:
    logger.info("🔄 Extracting cookies from browser profile …")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", f"chrome:{PLAYWRIGHT_PROFILE_DIR}",
        "--cookies", COOKIE_FILE,
        "--no-check-certificate",
        "--quiet",
        "--no-download",
        "https://www.youtube.com",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0 and verify_cookies_file(COOKIE_FILE):
            logger.info("✅ Cookies extracted and verified.")
            return True
        err = (stderr or b"").decode()[:300]
        logger.warning(f"yt-dlp cookie extraction issue: {err}")
        return False
    except asyncio.TimeoutError:
        logger.error("Cookie extraction timed out (120 s).")
        return False
    except Exception as exc:
        logger.error(f"Cookie extraction error: {exc}")
        return False
# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-GENERATE COOKIES
# ══════════════════════════════════════════════════════════════════════════════
async def auto_generate_cookies(reason: str = "auto") -> Optional[str]:
    async with _COOKIE_LOCK:
        if (
            os.path.exists(COOKIE_FILE)
            and verify_cookies_file(COOKIE_FILE)
            and not is_cookie_file_expired(COOKIE_FILE)
        ):
            logger.info("✅ Cookies already refreshed by another coroutine — reusing.")
            return COOKIE_FILE
        clear_old_cookies()
        for sub in range(1, 6):
            logger.info(f"🔄 Cookie generation sub-attempt {sub}/5 [{reason}] …")
            ok = await generate_cookies_via_playwright(
                reason=f"{reason} (sub {sub})")
            if not ok:
                logger.warning(f"Browser session failed on sub-attempt {sub}.")
                await asyncio.sleep(min(5 * sub, 30))
                continue
            ok = await _extract_cookies_from_profile()
            if ok:
                ip_info   = await get_public_ip_info() or {}
                timestamp = datetime.datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S UTC")
                await send_to_log_group(
                    text=(
                        f"🌐 **YouTube Cookies Extracted (Browser Profile)**\n\n"
                        f"📅 Time     : `{timestamp}`\n"
                        f"🌍 IP       : `{ip_info.get('ip', 'unknown')}`\n"
                        f"📍 Location : {ip_info.get('city', 'unknown')}, "
                        f"{ip_info.get('country', 'unknown')}\n"
                        f"🏢 ISP/Org  : {ip_info.get('org', 'unknown')}\n"
                        f"📝 Reason   : {reason}\n\n"
                        f"#YouTubeCookies"
                    )
                )
                await send_cookie_file_to_log_group(reason=reason)
                return COOKIE_FILE
            logger.warning(f"Cookie extraction failed on sub-attempt {sub}.")
            await asyncio.sleep(min(5 * sub, 30))
        logger.error(
            "❌ All 5 sub-attempts failed — outer infinite loop will retry …")
        return None
# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════
def verify_cookies_file(filename: str) -> bool:
    try:
        if not os.path.exists(filename):
            logger.error(f"Cookies file does not exist: {filename}")
            return False
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        if "youtube.com" not in content and ".youtube.com" not in content:
            logger.error("No youtube.com domain in cookies file")
            return False
        important_cookies = [
            "VISITOR_INFO1_LIVE", "PREF", "GPS", "YSC",
            "SOCS", "__Secure-ROLLOUT_TOKEN", "__Secure-YNID",
            "VISITOR_PRIVACY_METADATA",
        ]
        found = [c for c in important_cookies if c in content]
        if len(found) < 2:
            logger.warning(f"⚠️ Too few important cookies found: {found}")
            return False
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Cookies file is JSON format, not Netscape")
            return False
        valid_lines = 0
        for line in content.strip().split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            if "\t" not in line:
                logger.error(f"Invalid Netscape format (no tabs): {line[:100]}")
                return False
            valid_lines += 1
        if valid_lines < 3:
            logger.error(f"Too few valid cookie lines: {valid_lines}")
            return False
        logger.info(
            f"✅ Cookies verified: {filename} | lines={valid_lines} | found={found}")
        return True
    except Exception as e:
        logger.error(f"Error verifying cookies file: {e}")
        return False
def get_cookie_min_expiry(filepath: str) -> Optional[int]:
    try:
        min_exp = None
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain = parts[0]
                if "youtube.com" not in domain and "google.com" not in domain:
                    continue
                try:
                    exp = int(parts[4])
                    if exp <= 0:
                        continue
                    if min_exp is None or exp < min_exp:
                        min_exp = exp
                except (ValueError, IndexError):
                    continue
        return min_exp
    except Exception as e:
        logger.error(f"Failed to parse cookie expiry: {e}")
        return None
def is_cookie_file_expired(filepath: str) -> bool:
    if not os.path.exists(filepath):
        logger.info("❌ Cookie file missing → expired")
        return True
    min_exp = get_cookie_min_expiry(filepath)
    if min_exp is None:
        logger.warning("⚠️ Could not determine expiry → treating as expired")
        return True
    now = int(time.time())
    if min_exp < now:
        logger.info(
            f"🕐 Cookie EXPIRED at "
            f"{datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z"
        )
        return True
    remaining = min_exp - now
    logger.info(
        f"✅ Cookie VALID → expires in "
        f"{remaining // 3600}h {(remaining % 3600) // 60}m"
    )
    return False
# ══════════════════════════════════════════════════════════════════════════════
#  ERROR CLASSIFIERS
# ══════════════════════════════════════════════════════════════════════════════
_AUTH_SIGNALS = [
    "sign in to confirm you're not a bot",
    "confirm you are not a robot",
    "confirm you're not a bot",
    "not a bot",
    "http error 401",
    "http error 403",
    "unable to extract video data",
    "login required",
    "robot",
    "captcha",
    "recaptcha",
    "access denied",
    "forbidden",
    "sign in",
    "authentication",
    "cookie",
    "private video",
    "members only",
]
_FORMAT_SIGNALS = [
    "requested format is not available",
    "no video formats found",
    "format is not available",
]
def is_auth_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(sig in s for sig in _AUTH_SIGNALS)
def is_format_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(sig in s for sig in _FORMAT_SIGNALS)
# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════
async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    if not ENABLE_YT_COOKIES:
        return None
    if force_refresh:
        logger.warning("🔄 Force refreshing cookies …")
        clear_old_cookies()
        return await auto_generate_cookies(reason="Force refresh – auth/robot/manual")
    if (
        os.path.exists(COOKIE_FILE)
        and verify_cookies_file(COOKIE_FILE)
        and not is_cookie_file_expired(COOKIE_FILE)
    ):
        logger.info("✅ Using existing valid cookies")
        return COOKIE_FILE
    logger.warning("⚠️ Cookies invalid or expired → regenerating …")
    clear_old_cookies()
    return await auto_generate_cookies(reason="Initial / expired")
# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO ID EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
_VID_PATTERNS = [
    r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})",
    r"watch\?v=([A-Za-z0-9_-]{11})",
    r"youtu\.be/([A-Za-z0-9_-]{11})",
    r"shorts/([A-Za-z0-9_-]{11})",
    r"live/([A-Za-z0-9_-]{11})",
    r"embed/([A-Za-z0-9_-]{11})",
]
def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    for pat in _VID_PATTERNS:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    if re.match(r"^[A-Za-z0-9_-]{11}$", url):
        return url
    return None
def is_live_url(url: str) -> bool:
    if not url:
        return False
    return bool(re.search(r"youtube\.com/live/", url, re.IGNORECASE))
# ══════════════════════════════════════════════════════════════════════════════
#  YT-DLP OPTIONS BUILDER  (SPEED-OPTIMISED)
# ══════════════════════════════════════════════════════════════════════════════
def _playwright_profile_has_cookies() -> bool:
    candidates = [
        os.path.join(PLAYWRIGHT_PROFILE_DIR, "Default", "Cookies"),
        os.path.join(PLAYWRIGHT_PROFILE_DIR, "Cookies"),
    ]
    return any(os.path.isfile(p) and os.path.getsize(p) > 0 for p in candidates)
def get_ytdlp_opts(
    extra_opts: dict = None,
    use_cookie_file: str = None,
) -> dict:
    ua   = random.choice(USER_AGENTS)
    base = {
        # ── Output / housekeeping ─────────────────────────────────────────
        "outtmpl":            os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet":              True,
        "no_warnings":        True,
        "geo_bypass":         True,
        "nocheckcertificate": True,

        # ── Retry / resilience ────────────────────────────────────────────
        "retries":            15,
        "fragment_retries":   15,
        "file_access_retries": 5,
        "extractor_retries":  5,

        # ── SPEED OPTIMISATIONS ───────────────────────────────────────────
        # Download up to 10 DASH/HLS fragments in parallel (was 5)
        "concurrent_fragment_downloads": 10,
        # Read 16 MB at once from the network socket (was default ~10 KB)
        "http_chunk_size": 10 * 1024 * 1024,        # 10 MB per chunk
        # Internal I/O buffer — reduces syscall overhead
        "buffersize": 16 * 1024,                     # 16 KB
        # Tell the server we accept byte ranges (enables resume + parallelism)
        "continuedl": True,
        # Skip format availability checks — saves an extra HTTP request
        "check_formats": False,
        # Skip writing thumbnail / description / etc.
        "writethumbnail": False,
        "writeinfojson":  False,
        "writesubtitles": False,
        # Don't wait between retries
        "sleep_interval":       0,
        "max_sleep_interval":   0,
        "sleep_interval_requests": 0,

        # ── Cache ─────────────────────────────────────────────────────────
        "cachedir": YT_CACHE_DIR,

        # ── Player clients — try fastest first ────────────────────────────
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "web", "tv_embedded"],
                # Skip age-gate bypass attempts when not needed
                "skip": ["webpage"],
            }
        },

        # ── Headers ───────────────────────────────────────────────────────
        "http_headers": {
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
            # Signal that we accept gzip/br compressed responses
            "Accept-Encoding": "gzip, deflate, br",
        },

        # ── Socket timeout ────────────────────────────────────────────────
        "socket_timeout": 30,
        "source_address": "0.0.0.0",   # bind to all interfaces
    }

    # ── Cookie source (priority: file > profile DB > none) ────────────────
    if use_cookie_file and os.path.isfile(use_cookie_file):
        base["cookiefile"] = use_cookie_file
        logger.debug(f"Using cookiefile: {use_cookie_file}")
    elif _playwright_profile_has_cookies():
        base["cookiesfrombrowser"] = ("chrome", PLAYWRIGHT_PROFILE_DIR)
        logger.debug("Using cookiesfrombrowser with persistent profile")
    else:
        logger.debug("No cookie source available — proceeding without cookies")

    # ── Optional proxy ────────────────────────────────────────────────────
    proxy = choose_random_proxy(YTDLP_PROXY_POOL)
    if proxy:
        base["proxy"] = proxy

    if extra_opts:
        base.update(extra_opts)
    return base

def _audio_extra() -> dict:
    return {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "postprocessors": [{
            "key":              "FFmpegExtractAudio",
            "preferredcodec":   "mp3",
            "preferredquality": "192",
        }],
    }

def _video_extra() -> dict:
    return {
        "format":              "bv*+ba/b",
        "merge_output_format": "mp4",
    }
# ══════════════════════════════════════════════════════════════════════════════
#  FILE FINDER
# ══════════════════════════════════════════════════════════════════════════════
def _get_downloaded_file(
    video_id: str, prefer_m4a: bool = False
) -> Optional[str]:
    if not video_id:
        return None
    exts = (
        ["m4a", "mp3", "webm", "opus", "mp4", "mkv"]
        if prefer_m4a
        else ["mp3", "webm", "m4a", "opus", "mp4", "mkv"]
    )
    for ext in exts:
        p = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(p):
            return p
    if os.path.exists(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            if video_id in f:
                return os.path.join(DOWNLOAD_DIR, f)
    return None
# ══════════════════════════════════════════════════════════════════════════════
#  PROGRESS BAR HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _make_progress_bar(percent: float, length: int = 10) -> str:
    filled = int(length * percent / 100)
    bar    = "▓" * filled + "░" * (length - filled)
    return f"[{bar}]"

def _fmt_bytes(num_bytes: float) -> str:
    if num_bytes is None:
        return "?MB"
    mb = num_bytes / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f}MB"
    kb = num_bytes / 1024
    return f"{kb:.0f}KB"

def _fmt_speed(speed: float) -> str:
    if speed is None or speed <= 0:
        return "?MB/s"
    mb = speed / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f}MB/s"
    kb = speed / 1024
    return f"{kb:.0f}KB/s"

def _fmt_eta(eta_seconds) -> str:
    if eta_seconds is None:
        return "?s"
    eta = int(eta_seconds)
    if eta >= 3600:
        return f"{eta // 3600}h {(eta % 3600) // 60}m"
    if eta >= 60:
        return f"{eta // 60}m {eta % 60}s"
    return f"{eta}s"

def _build_progress_text(title: str, d: dict) -> str:
    short_title = (title[:13] + "..") if len(title) > 13 else title
    downloaded = d.get("downloaded_bytes", 0) or 0
    total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
    speed      = d.get("speed") or 0
    eta        = d.get("eta")
    if total > 0:
        percent = min(downloaded / total * 100, 100)
    else:
        percent = 0
    bar   = _make_progress_bar(percent)
    line1 = f"🎵 `{short_title}`"
    line2 = f"🎵 {bar} `{percent:.0f}%`"
    line3 = (
        f"`{_fmt_bytes(downloaded)}/{_fmt_bytes(total)}` • "
        f"`{_fmt_speed(speed)}` • ETA `{_fmt_eta(eta)}`"
    )
    return f"{line1}\n{line2}\n{line3}"
# ══════════════════════════════════════════════════════════════════════════════
#  PROGRESS HOOK FACTORY  (FIXED — works correctly during download)
#
#  Root cause of the original bug:
#    • yt-dlp calls the hook from a ThreadPoolExecutor worker thread.
#    • asyncio.run_coroutine_threadsafe() is the only safe way to schedule
#      coroutines from a non-async thread onto the running event loop.
#    • The loop must be captured BEFORE the executor starts (done here via
#      the `loop` parameter passed in from the caller).
#    • We store `last_update` in a mutable dict (not a closure variable)
#      so the thread-local mutation is visible across calls.
#    • The "finished" guard prevents a race where the hook fires one last
#      "downloading" event after the "finished" event.
# ══════════════════════════════════════════════════════════════════════════════
def make_progress_hook(
    loop: asyncio.AbstractEventLoop,
    mystic,
    title: str,
) -> callable:
    # Use a mutable dict so the nested function can mutate shared state
    # without `nonlocal` (which doesn't work across thread boundaries reliably).
    state = {
        "last_update": 0.0,
        "finished":    False,
    }

    def hook(d: dict):
        # d is the yt-dlp progress dict — called from a worker thread
        if state["finished"]:
            return

        now    = time.monotonic()   # monotonic is thread-safe
        status = d.get("status", "")

        if status == "finished":
            state["finished"] = True
            short = (title[:13] + "..") if len(title) > 13 else title
            asyncio.run_coroutine_threadsafe(
                _safe_edit(
                    mystic,
                    f"🎵 `{short}`\n✅ Download complete, processing…",
                ),
                loop,
            )
            return

        if status == "downloading":
            # Throttle: don't spam Telegram more often than every N seconds
            if now - state["last_update"] < PROGRESS_UPDATE_INTERVAL:
                return
            state["last_update"] = now

            # Build and schedule the Telegram edit — non-blocking from this thread
            text = _build_progress_text(title, d)
            asyncio.run_coroutine_threadsafe(_safe_edit(mystic, text), loop)

    return hook

async def _safe_edit(mystic, text: str):
    """Edit mystic message safely, ignoring flood-wait and not-modified errors."""
    try:
        await mystic.edit_text(text)
    except Exception as e:
        err = str(e).lower()
        if "not modified" in err or "flood" in err or "too many" in err:
            pass
        elif "message to edit not found" in err or "message_id_invalid" in err:
            pass
        else:
            logger.debug(f"Progress edit error (ignored): {e}")
# ══════════════════════════════════════════════════════════════════════════════
#  METHOD 1 — API DOWNLOAD  (with progress bar support)
# ══════════════════════════════════════════════════════════════════════════════
async def _download_via_api(
    video_id: str,
    media_type: str,
    mystic=None,
    title: str = "",
) -> Optional[str]:
    if not API_URL:
        return None
    ext      = "mp3" if media_type == "audio" else "mp4"
    out_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
    headers  = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY
    display_title = title or video_id
    logger.info(f"📡 [API] {media_type} download for {video_id} …")
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                params = {"url": video_id, "type": media_type}
                async with session.get(
                    f"{API_URL}/download",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        raise ValueError(f"API /download → HTTP {resp.status}")
                    data  = await resp.json()
                    token = data.get("download_token") or data.get("token")
                    dl_url = (
                        data.get("download_url")
                        or (
                            f"{API_URL}/stream/{video_id}"
                            f"?type={media_type}&token={token}"
                            if token else None
                        )
                    )
                    if not dl_url:
                        raise ValueError("No download URL in API response")
                    if not dl_url.startswith("http"):
                        dl_url = API_URL + dl_url

                last_update  = 0.0
                downloaded   = 0
                total        = 0
                start_time   = time.monotonic()

                # Show initial progress immediately
                if mystic:
                    await _safe_edit(mystic, _build_progress_text(display_title, {
                        "downloaded_bytes": 0, "total_bytes": None,
                        "speed": None, "eta": None,
                    }))

                async with session.get(
                    dl_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600),
                    allow_redirects=True,
                ) as file_resp:
                    if file_resp.status not in (200, 206):
                        raise ValueError(f"File stream → HTTP {file_resp.status}")
                    total = int(file_resp.headers.get("Content-Length", 0))
                    with open(out_path, "wb") as fh:
                        async for chunk in file_resp.content.iter_chunked(1024 * 1024):
                            fh.write(chunk)
                            downloaded += len(chunk)
                            now = time.monotonic()
                            if mystic and now - last_update >= PROGRESS_UPDATE_INTERVAL:
                                last_update = now
                                elapsed = max(now - start_time, 0.001)
                                speed   = downloaded / elapsed
                                eta     = (
                                    (total - downloaded) / speed
                                    if speed > 0 and total > 0
                                    else None
                                )
                                fake_d = {
                                    "downloaded_bytes": downloaded,
                                    "total_bytes":      total if total > 0 else None,
                                    "speed":            speed,
                                    "eta":              eta,
                                }
                                await _safe_edit(mystic, _build_progress_text(
                                    display_title, fake_d))

            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                logger.info(f"✅ [API] Downloaded: {out_path}")
                if mystic:
                    short = (
                        (display_title[:13] + "..")
                        if len(display_title) > 13
                        else display_title
                    )
                    await _safe_edit(
                        mystic,
                        f"🎵 `{short}`\n✅ Download complete, processing…",
                    )
                return out_path
            raise ValueError("File is empty after API download.")
        except Exception as exc:
            logger.warning(f"[API] Attempt {attempt}/{MAX_API_RETRIES} failed: {exc}")
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            if attempt < MAX_API_RETRIES:
                await asyncio.sleep(2 * attempt)
    logger.error("[API] All attempts exhausted.")
    return None
# ══════════════════════════════════════════════════════════════════════════════
#  METHODS 2 & 3 — YT-DLP  (with progress bar support, FIXED hook)
# ══════════════════════════════════════════════════════════════════════════════
async def download_with_ytdlp(
    link: str,
    is_audio: bool,
    mystic=None,
    title: str = "",
) -> Optional[str]:
    video_id = extract_video_id(link)
    if not video_id:
        logger.error(f"Could not extract video ID from {link}")
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    existing = _get_downloaded_file(video_id)
    if existing:
        logger.info(f"📁 File already exists: {existing}")
        return existing

    if is_blocked_ip():
        info = _CURRENT_IP_INFO
        await send_to_log_group(
            text=(
                f"🚫 **Download Queued — Amazon/AWS IP Detected**\n\n"
                f"🌍 IP      : `{info.get('ip', 'unknown')}`\n"
                f"🏢 Org     : {info.get('org', 'unknown')}\n\n"
                f"YouTube blocks Amazon/AWS IPs.\n"
                f"⏳ IP watcher polls every {IP_POLL_INTERVAL}s.\n"
                f"✅ Download resumes automatically when a non-Amazon IP is "
                f"detected and cookies are ready.\n\n"
                f"#BlockedIP"
            )
        )
        await wait_for_good_ip()

    cookie_file     = await get_cookies()
    # Capture the running event loop BEFORE any executor calls.
    # This is the loop that asyncio.run_coroutine_threadsafe must target.
    loop            = asyncio.get_event_loop()
    format_fallback = False
    non_auth_errors = 0
    cookie_cycle    = 0
    label           = "🎵" if is_audio else "🎬"
    display_title   = title or video_id

    def _build_opts(cf: Optional[str], prog_hook=None) -> dict:
        if format_fallback:
            fallback: dict = {"format": "best"}
            if is_audio:
                fallback["postprocessors"] = _audio_extra()["postprocessors"]
            else:
                fallback["merge_output_format"] = "mp4"
            opts = get_ytdlp_opts(fallback, use_cookie_file=cf)
        else:
            extra = _audio_extra() if is_audio else _video_extra()
            opts  = get_ytdlp_opts(extra, use_cookie_file=cf)
        if prog_hook:
            opts["progress_hooks"] = [prog_hook]
        return opts

    while True:
        # Create a fresh progress hook for each attempt so state resets
        prog_hook = make_progress_hook(loop, mystic, display_title) if mystic else None
        ydl_opts  = _build_opts(cookie_file, prog_hook)

        logger.info(
            f"{label} [yt-dlp] {video_id} | "
            f"cookie_cycle={cookie_cycle} | "
            f"non_auth_errs={non_auth_errors} | "
            f"format_fallback={format_fallback}"
        )

        # Show an initial "starting" message so the user sees something immediately
        if mystic:
            await _safe_edit(mystic, _build_progress_text(display_title, {
                "downloaded_bytes": 0, "total_bytes": None,
                "speed": None, "eta": None,
            }))

        try:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            async with DOWNLOAD_SEMAPHORE:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await loop.run_in_executor(
                        None,
                        lambda: ydl.extract_info(link, download=True),
                    )

            file_path = _get_downloaded_file(video_id)
            if not file_path and info:
                candidate = info.get("_filename") or info.get("filepath")
                if candidate and os.path.exists(candidate):
                    file_path = candidate

            if file_path and os.path.exists(file_path):
                logger.info(f"✅ {label} Download successful: {file_path}")
                return file_path
            raise RuntimeError("File not found after yt-dlp download completed.")

        except Exception as exc:
            err_str = str(exc)
            logger.error(f"{label} [yt-dlp] Error: {err_str[:300]}")

            if is_auth_error(exc):
                await check_ip_quality()
                if is_blocked_ip():
                    info = _CURRENT_IP_INFO
                    logger.warning("🚫 IP became Amazon mid-download — re-queuing …")
                    await send_to_log_group(
                        text=(
                            f"🚫 **Download Paused — Amazon IP Mid-Download**\n\n"
                            f"🌍 IP  : `{info.get('ip', 'unknown')}`\n"
                            f"🏢 Org : `{info.get('org', 'unknown')}`\n\n"
                            f"⏳ Waiting for non-Amazon IP to resume …\n\n"
                            f"#BlockedIP"
                        )
                    )
                    await wait_for_good_ip()
                    cookie_file = await get_cookies()
                    continue

            if is_format_error(exc) and not format_fallback:
                logger.warning("⚠️ Format unavailable — switching to 'best' format …")
                format_fallback = True
                non_auth_errors = 0
                await asyncio.sleep(2)
                continue

            if is_auth_error(exc) or "file not found" in err_str.lower():
                cookie_cycle   += 1
                non_auth_errors = 0
                logger.warning(
                    f"🤖 Auth/bot error — cookie regen cycle #{cookie_cycle} …")
                clear_old_cookies()
                await send_to_log_group(
                    text=(
                        f"⚠️ **YouTube: Confirm You're Not a Robot – Detected**\n\n"
                        f"{label} Video  : `{video_id}`\n"
                        f"⚠️ Error : `{err_str[:200]}`\n\n"
                        f"🧹 Old cookies cleared\n"
                        f"🔄 Regenerating cookies via Browser Profile …\n"
                        f"♻️ Regen cycle #{cookie_cycle} — retrying until success …\n\n"
                        f"#YouTubeCookies"
                    )
                )
                new_cf      = None
                inner_cycle = 0
                while new_cf is None:
                    inner_cycle += 1
                    logger.info(
                        f"♻️ Cookie gen inner cycle #{inner_cycle} "
                        f"(regen cycle #{cookie_cycle}) …"
                    )
                    new_cf = await auto_generate_cookies(
                        reason=(
                            f"Robot/auth detected during download "
                            f"regen#{cookie_cycle} inner#{inner_cycle}"
                        )
                    )
                    if new_cf is None:
                        wait_s = min(10 * inner_cycle, 120)
                        logger.warning(
                            f"Cookie generation returned None — "
                            f"retrying in {wait_s} s …"
                        )
                        await asyncio.sleep(wait_s)
                cookie_file     = new_cf
                format_fallback = False
                logger.info(
                    f"✅ Fresh cookies obtained after {inner_cycle} "
                    f"inner cycle(s). Resuming download …"
                )
                await asyncio.sleep(random.uniform(1, 3))
                continue

            non_auth_errors += 1
            logger.warning(
                f"Non-auth error #{non_auth_errors}/{MAX_NON_AUTH_ERRS}: "
                f"{err_str[:200]}"
            )
            if non_auth_errors >= MAX_NON_AUTH_ERRS:
                logger.error(
                    f"{label} Giving up on {video_id} after "
                    f"{MAX_NON_AUTH_ERRS} consecutive non-auth errors."
                )
                return None
            await asyncio.sleep(5 * non_auth_errors)
# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC DOWNLOAD WRAPPERS
# ══════════════════════════════════════════════════════════════════════════════
async def download_song(
    link: str,
    mystic=None,
    title: str = "",
) -> Optional[str]:
    logger.info(f"🎵 Downloading audio: {link}")
    vid    = extract_video_id(link) or link
    result = await _download_via_api(vid, "audio", mystic=mystic, title=title)
    if result:
        return result
    logger.info("🎵 API failed / not configured — falling back to yt-dlp …")
    return await download_with_ytdlp(link, is_audio=True, mystic=mystic, title=title)

async def download_video(
    link: str,
    mystic=None,
    title: str = "",
) -> Optional[str]:
    logger.info(f"🎬 Downloading video: {link}")
    vid    = extract_video_id(link) or link
    result = await _download_via_api(vid, "video", mystic=mystic, title=title)
    if result:
        return result
    logger.info("🎬 API failed / not configured — falling back to yt-dlp …")
    return await download_with_ytdlp(link, is_audio=False, mystic=mystic, title=title)
# ══════════════════════════════════════════════════════════════════════════════
#  STREAMING HELPER
# ══════════════════════════════════════════════════════════════════════════════
STREAM_MIN_SIZE = 500_000
STREAM_FORMAT   = "140/bestaudio"

async def wait_for_partial_file(
    file_path: str,
    min_size: int         = STREAM_MIN_SIZE,
    check_interval: float = 0.3,
):
    while True:
        if os.path.exists(file_path) and os.path.getsize(file_path) > min_size:
            return
        await asyncio.sleep(check_interval)

async def download_song_stream(
    link: str,
) -> Tuple[Optional[str], Optional[asyncio.Task]]:
    video_id = extract_video_id(link)
    if not video_id:
        return None, None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    existing = _get_downloaded_file(video_id, prefer_m4a=True)
    if existing:
        return existing, None
    if is_blocked_ip():
        logger.warning("🚫 Stream queued — waiting for non-Amazon IP …")
        await wait_for_good_ip()
    cookie_file   = await get_cookies()
    ydl_opts      = get_ytdlp_opts(
        {"format": STREAM_FORMAT}, use_cookie_file=cookie_file)
    expected_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")
    loop          = asyncio.get_event_loop()

    async def _bg():
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(
                    None, lambda: ydl.extract_info(link, download=True))

    task = asyncio.create_task(_bg())
    try:
        await wait_for_partial_file(expected_path, min_size=STREAM_MIN_SIZE)
        return expected_path, task
    except Exception as e:
        logger.error(f"Streaming wait error: {e}")
        task.cancel()
        return None, None
# ══════════════════════════════════════════════════════════════════════════════
#  LIVE STREAM — INTERNAL URL PICKER
# ══════════════════════════════════════════════════════════════════════════════
def _pick_stream_url(info: dict, video: bool) -> Optional[str]:
    if info.get("url"):
        return info["url"]
    formats = info.get("formats") or []
    if not formats:
        return None
    if video:
        candidates = [
            f for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
            and f.get("url")
        ]
        if not candidates:
            candidates = [f for f in formats if f.get("url")]
        candidates.sort(
            key=lambda f: f.get("tbr") or f.get("abr") or 0, reverse=True)
    else:
        candidates = [
            f for f in formats
            if f.get("vcodec") in (None, "none")
            and f.get("acodec") not in (None, "none")
            and f.get("url")
        ]
        if not candidates:
            candidates = [f for f in formats if f.get("url")]
        candidates.sort(
            key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
    return candidates[0]["url"] if candidates else None
# ══════════════════════════════════════════════════════════════════════════════
#  LIVE STREAM — METHOD 1: API
# ══════════════════════════════════════════════════════════════════════════════
async def _live_stream_via_api(
    video_id: str,
    video: bool = False,
) -> Optional[str]:
    if not API_URL:
        return None
    media_type = "livestream_video" if video else "livestream_audio"
    headers    = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY
    logger.info(f"📡 [live/API] Trying API for live stream: {video_id} | type={media_type}")
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                params = {"url": video_id, "type": media_type}
                async with session.get(
                    f"{API_URL}/download",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        raise ValueError(f"API /download → HTTP {resp.status}")
                    data = await resp.json()
            stream_url = data.get("stream_url") or data.get("hls_url")
            if not stream_url:
                token  = data.get("download_token") or data.get("token")
                dl_url = data.get("download_url") or (
                    f"{API_URL}/stream/{video_id}?type={media_type}&token={token}"
                    if token else None
                )
                if dl_url:
                    stream_url = dl_url if dl_url.startswith("http") else API_URL + dl_url
            if not stream_url:
                raise ValueError("No stream URL in API response")
            logger.info(f"✅ [live/API] Got stream URL from API")
            return stream_url
        except Exception as exc:
            logger.warning(
                f"[live/API] Attempt {attempt}/{MAX_API_RETRIES} failed: {exc}")
            if attempt < MAX_API_RETRIES:
                await asyncio.sleep(2 * attempt)
    logger.warning("[live/API] All API attempts failed — falling back to yt-dlp")
    return None
# ══════════════════════════════════════════════════════════════════════════════
#  LIVE STREAM — METHOD 2: YT-DLP WITH COOKIE FILE / COOKIE REGEN
# ══════════════════════════════════════════════════════════════════════════════
async def _live_stream_via_ytdlp(
    link: str,
    video: bool = False,
) -> Optional[str]:
    if is_blocked_ip():
        info = _CURRENT_IP_INFO
        logger.warning("🚫 Live stream (yt-dlp) queued — waiting for non-Amazon IP …")
        await send_to_log_group(
            text=(
                f"🚫 **Live Stream Queued — Amazon/AWS IP**\n\n"
                f"🌍 IP  : `{info.get('ip', 'unknown')}`\n"
                f"🏢 Org : `{info.get('org', 'unknown')}`\n\n"
                f"⏳ Waiting for non-Amazon IP …\n\n"
                f"#BlockedIP #LiveStream"
            )
        )
        await wait_for_good_ip()

    cookie_file  = await get_cookies()
    loop         = asyncio.get_event_loop()
    cookie_cycle = 0
    fmt_selector = "bv*+ba/b/best" if video else "bestaudio[ext=m4a]/bestaudio/best"

    while True:
        cf = cookie_file if (cookie_file and os.path.isfile(cookie_file)) else None
        ydl_opts = get_ytdlp_opts(
            {
                "format":        fmt_selector,
                "quiet":         True,
                "no_warnings":   True,
                "skip_download": True,
            },
            use_cookie_file=cf,
        )
        logger.info(
            f"📡 [live/yt-dlp] Extracting info | "
            f"cookie_file={'yes' if cf else 'no'} | "
            f"cookie_cycle={cookie_cycle} | video={video}"
        )
        try:
            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(link, download=False)
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _extract),
                timeout=60,
            )
            if not info:
                raise RuntimeError("yt-dlp returned no info for live stream.")
            stream_url = _pick_stream_url(info, video)
            if not stream_url:
                raise RuntimeError(
                    "Could not extract a streaming URL from yt-dlp info.")
            logger.info(
                f"✅ [live/yt-dlp] Resolved URL (first 80 chars): "
                f"{stream_url[:80]}…"
            )
            return stream_url
        except Exception as exc:
            err_str = str(exc)
            logger.error(f"📡 [live/yt-dlp] Error: {err_str[:300]}")

            if is_auth_error(exc):
                await check_ip_quality()
                if is_blocked_ip():
                    ip_info = _CURRENT_IP_INFO
                    logger.warning(
                        "🚫 Live stream resolve: IP became Amazon — re-queuing …")
                    await send_to_log_group(
                        text=(
                            f"🚫 **Live Stream Paused — Amazon IP**\n\n"
                            f"🌍 IP  : `{ip_info.get('ip', 'unknown')}`\n"
                            f"🏢 Org : `{ip_info.get('org', 'unknown')}`\n\n"
                            f"⏳ Waiting for non-Amazon IP …\n\n"
                            f"#BlockedIP #LiveStream"
                        )
                    )
                    await wait_for_good_ip()
                    cookie_file = await get_cookies()
                    continue

            if is_auth_error(exc):
                cookie_cycle += 1
                logger.warning(
                    f"🤖 [live/yt-dlp] Auth/bot error — "
                    f"cookie regen cycle #{cookie_cycle} …"
                )
                clear_old_cookies()
                await send_to_log_group(
                    text=(
                        f"⚠️ **Live Stream: Robot/Auth Detected**\n\n"
                        f"🔗 URL     : `{link}`\n"
                        f"⚠️ Error   : `{err_str[:200]}`\n\n"
                        f"🧹 Old cookies cleared\n"
                        f"🔄 Regenerating via Browser Profile …\n"
                        f"♻️ Regen cycle #{cookie_cycle}\n\n"
                        f"#YouTubeCookies #LiveStream"
                    )
                )
                new_cf      = None
                inner_cycle = 0
                while new_cf is None:
                    inner_cycle += 1
                    new_cf = await auto_generate_cookies(
                        reason=(
                            f"Live stream robot/auth "
                            f"regen#{cookie_cycle} inner#{inner_cycle}"
                        )
                    )
                    if new_cf is None:
                        wait_s = min(10 * inner_cycle, 120)
                        logger.warning(
                            f"Cookie generation returned None — "
                            f"retrying in {wait_s} s …"
                        )
                        await asyncio.sleep(wait_s)
                cookie_file = new_cf
                await asyncio.sleep(random.uniform(1, 3))
                continue

            logger.error(
                f"📡 [live/yt-dlp] Non-retryable error for {link}: "
                f"{err_str[:300]}"
            )
            await send_to_log_group(
                text=(
                    f"❌ **Live Stream (yt-dlp) Failed**\n\n"
                    f"🔗 URL   : `{link}`\n"
                    f"⚠️ Error : `{err_str[:300]}`\n\n"
                    f"#LiveStream"
                )
            )
            return None
# ══════════════════════════════════════════════════════════════════════════════
#  LIVE STREAM — PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
async def live_stream(
    link: str,
    video: bool = False,
) -> Optional[str]:
    logger.info(f"🔴 [live_stream] Start | link={link} | video={video}")
    vid = extract_video_id(link) or link
    if API_URL:
        result = await _live_stream_via_api(vid, video=video)
        if result:
            logger.info("✅ [live_stream] Resolved via API")
            return result
        logger.info("📡 [live_stream] API failed / not configured — trying yt-dlp …")
    result = await _live_stream_via_ytdlp(link, video=video)
    if result:
        logger.info("✅ [live_stream] Resolved via yt-dlp")
        return result
    logger.error(f"❌ [live_stream] All methods failed for: {link}")
    await send_to_log_group(
        text=(
            f"❌ **Live Stream Resolution Failed — All Methods**\n\n"
            f"🔗 URL  : `{link}`\n"
            f"📋 Tried: API → yt-dlp+cookies\n\n"
            f"#LiveStream"
        )
    )
    return None
# ══════════════════════════════════════════════════════════════════════════════
#  PLAY_URL AUTO-TEST
# ══════════════════════════════════════════════════════════════════════════════
async def test_cookie_with_playurl(retries: int = 2):
    if not PLAY_URL:
        logger.warning("PLAY_URL not set — skipping auto-test.")
        return
    if is_blocked_ip():
        info = _CURRENT_IP_INFO
        logger.warning(
            f"⏭️  PLAY_URL test skipped — Amazon IP "
            f"({info.get('org', 'unknown')} / {info.get('ip', 'unknown')})."
        )
        await send_to_log_group(
            text=(
                f"⏭️ **PLAY_URL Test Skipped — Amazon IP**\n\n"
                f"🌍 IP      : `{info.get('ip', 'unknown')}`\n"
                f"🏢 Org     : `{info.get('org', 'unknown')}`\n\n"
                f"Test will run automatically when a non-Amazon IP is detected.\n\n"
                f"#BlockedIP #CookieTest"
            )
        )
        return
    if retries <= 0:
        logger.error("❌ PLAY_URL test: max retries reached")
        await send_to_log_group(
            text=(
                "❌ **Cookie Auto-Test: Max Retries Reached**\n\n"
                f"🎬 URL: `{PLAY_URL}`\n\n"
                "Will retry on next download.\n\n"
                "#CookieTest"
            )
        )
        return
    logger.info(f"🎬 Auto-testing cookies with PLAY_URL (retries left: {retries}) …")
    test_dir = os.path.join(os.getcwd(), "cookie_test")
    os.makedirs(test_dir, exist_ok=True)
    video_id  = extract_video_id(PLAY_URL)
    test_opts = get_ytdlp_opts(
        {
            "outtmpl": os.path.join(test_dir, "%(id)s.%(ext)s"),
            "format":  "bestaudio/best",
        },
        use_cookie_file=COOKIE_FILE if os.path.isfile(COOKIE_FILE) else None,
    )
    try:
        loop = asyncio.get_event_loop()
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                await loop.run_in_executor(
                    None, lambda: ydl.extract_info(PLAY_URL, download=True))
        file_path = None
        if video_id:
            for ext in ["mp3", "webm", "m4a", "opus", "mp4", "mkv"]:
                p = os.path.join(test_dir, f"{video_id}.{ext}")
                if os.path.exists(p):
                    file_path = p
                    break
        if not file_path and os.path.exists(test_dir):
            files = [
                os.path.join(test_dir, f)
                for f in os.listdir(test_dir)
                if os.path.isfile(os.path.join(test_dir, f))
            ]
            if files:
                file_path = max(files, key=os.path.getmtime)
        if file_path and os.path.exists(file_path):
            size_kb = os.path.getsize(file_path) // 1024
            logger.info(f"✅ Cookie test PASSED — {file_path} ({size_kb} KB)")
            await send_to_log_group(
                text=(
                    f"✅ **Cookie Auto-Test: PASSED**\n\n"
                    f"🎬 URL  : `{PLAY_URL}`\n"
                    f"📁 File : `{os.path.basename(file_path)}`\n"
                    f"📦 Size : `{size_kb} KB`\n\n"
                    f"Cookies are working correctly ✔️\n\n"
                    f"#CookieTest"
                )
            )
            try:
                os.remove(file_path)
            except Exception:
                pass
        else:
            logger.error("❌ Cookie test FAILED — file not found after download")
            await send_to_log_group(
                text=(
                    f"❌ **Cookie Auto-Test: FAILED**\n\n"
                    f"🎬 URL: `{PLAY_URL}`\n\n"
                    f"Download completed but no file found.\n"
                    f"Triggering cookie regeneration …\n\n"
                    f"#CookieTest"
                )
            )
            clear_old_cookies()
            new_cookie = await auto_generate_cookies(
                reason="PLAY_URL test: file not found")
            if new_cookie:
                await test_cookie_with_playurl(retries=retries - 1)
    except Exception as e:
        err_str = str(e)
        logger.error(f"Cookie auto-test error: {err_str}")
        if is_auth_error(e):
            await check_ip_quality()
            if is_blocked_ip():
                logger.warning("🚫 IP re-check shows Amazon IP — skipping cookie regen.")
                return
            logger.warning("🤖 Robot/auth during PLAY_URL test — regenerating …")
            clear_old_cookies()
            await send_to_log_group(
                text=(
                    f"⚠️ **Robot/Auth Detected During PLAY_URL Cookie Test**\n\n"
                    f"🔗 URL    : `{PLAY_URL}`\n"
                    f"⚠️ Error  : `{err_str[:200]}`\n\n"
                    f"🧹 Old cookies cleared\n"
                    f"🔄 Regenerating via Browser Profile …\n\n"
                    f"#YouTubeCookies"
                )
            )
            new_cookie = await auto_generate_cookies(
                reason="Robot detected during PLAY_URL auto-test")
            if new_cookie:
                await test_cookie_with_playurl(retries=retries - 1)
        else:
            await send_to_log_group(
                text=(
                    f"❌ **Cookie Auto-Test: ERROR**\n\n"
                    f"🎬 URL   : `{PLAY_URL}`\n"
                    f"⚠️ Error : `{err_str[:300]}`\n\n"
                    f"Cookies will regenerate automatically on next download.\n\n"
                    f"#CookieTest"
                )
            )
# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════════════════════
async def shell_cmd(cmd: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if err:
        decoded = err.decode("utf-8")
        if "unavailable videos are hidden" in decoded.lower():
            return out.decode("utf-8")
        return decoded
    return out.decode("utf-8")

async def check_file_size(link: str) -> Optional[int]:
    try:
        ydl_opts = get_ytdlp_opts(
            {"quiet": True},
            use_cookie_file=COOKIE_FILE if os.path.isfile(COOKIE_FILE) else None,
        )
        loop = asyncio.get_event_loop()
        def _get_size():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info  = ydl.extract_info(link, download=False)
                total = 0
                for f in info.get("formats", []):
                    size = f.get("filesize") or f.get("filesize_approx")
                    if size:
                        total += size
                return total
        return await asyncio.wait_for(
            loop.run_in_executor(None, _get_size), timeout=60)
    except Exception as e:
        logger.error(f"Failed to get file size: {e}")
        return None
# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE STARTUP HELPER
# ══════════════════════════════════════════════════════════════════════════════
async def _run_cookie_startup():
    cleanup_playwright_profile()
    need = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )
    if need:
        logger.info("🔄 No valid cookies — generating via Browser Profile …")
        cf = await get_cookies(force_refresh=True)
        if cf:
            logger.info(f"✅ Cookies ready: {cf}")
        else:
            logger.warning(
                "⚠️ Cookie generation failed — will retry on next download.")
            await send_to_log_group(
                text=(
                    "⚠️ **Cookie Generation Failed**\n\n"
                    "Could not generate cookies via Browser Profile.\n"
                    "The bot will retry automatically when a download is requested.\n\n"
                    "#YouTubeCookies"
                )
            )
    else:
        logger.info("✅ Existing cookies valid — skipping regeneration.")
    logger.info("🎬 Running PLAY_URL startup test …")
    await test_cookie_with_playurl(retries=2)
# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def startup_services():
    if not ENABLE_YT_COOKIES:
        logger.info("YouTube cookie handling disabled (ENABLE_YT_COOKIES=false).")
        return
    logger.info("🚀 Starting YouTube services …")
    good = await check_ip_quality()
    info = _CURRENT_IP_INFO
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    if not good:
        logger.warning(
            f"🚫 Amazon IP on startup — "
            f"{info.get('org', 'unknown')} / {info.get('ip', 'unknown')}. "
            f"Cookie generation suspended. Polling every {IP_POLL_INTERVAL}s."
        )
        await send_to_log_group(
            text=(
                f"🚫 **Startup: Amazon IP Detected — Services On Hold**\n\n"
                f"📅 Time     : `{timestamp}`\n"
                f"🌍 IP       : `{info.get('ip', 'unknown')}`\n"
                f"📍 Location : {info.get('city', 'unknown')}, "
                f"{info.get('country', 'unknown')}\n"
                f"🏢 Org/ISP  : `{info.get('org', 'unknown')}`\n\n"
                f"❌ YouTube blocks Amazon/AWS IPs.\n"
                f"⏳ Cookie generation and downloads are **suspended**.\n"
                f"🔁 Polling every **{IP_POLL_INTERVAL}s** until a non-Amazon IP is detected.\n"
                f"✅ Everything resumes **automatically** once a good IP appears.\n\n"
                f"#BlockedIP #Startup"
            )
        )
        asyncio.create_task(_ip_watcher_loop())
        return
    logger.info(
        f"✅ Good IP on startup — "
        f"{info.get('org', 'unknown')} / {info.get('ip', 'unknown')}. "
        f"Proceeding with cookie generation."
    )
    await send_to_log_group(
        text=(
            f"✅ **Startup: Good IP Detected**\n\n"
            f"📅 Time     : `{timestamp}`\n"
            f"🌍 IP       : `{info.get('ip', 'unknown')}`\n"
            f"📍 Location : {info.get('city', 'unknown')}, "
            f"{info.get('country', 'unknown')}\n"
            f"🏢 Org/ISP  : `{info.get('org', 'unknown')}`\n\n"
            f"Proceeding with cookie generation and PLAY_URL test …\n\n"
            f"#GoodIP #Startup"
        )
    )
    await _run_cookie_startup()
    _good_ip_event().set()
    logger.info("✅ Startup complete — event set, downloads enabled.")
    asyncio.create_task(_ip_watcher_loop())
# ══════════════════════════════════════════════════════════════════════════════
#  YouTubeAPI CLASS
# ══════════════════════════════════════════════════════════════════════════════
class YouTubeAPI:
    def __init__(self):
        self.base     = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.status   = "https://www.youtube.com/oembed?url="
        self.regex    = re.compile(
            r"(https?://)?(www\.|m\.)?"
            r"(youtube\.com/(?:watch\?v=|shorts/|live/|embed/|playlist\?list=)"
            r"|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)"
            r"([&?][^\s]*)?"
        )
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-9?]*[ -/]*[@-~])")

    def _norm(self, link: str) -> str:
        return link.split("&")[0] if "&" in link else link

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Optional[str]:
        msgs = [message_1]
        if message_1.reply_to_message:
            msgs.append(message_1.reply_to_message)
        for msg in msgs:
            if msg.entities:
                for ent in msg.entities:
                    if ent.type == MessageEntityType.URL:
                        txt = msg.text or msg.caption
                        return txt[ent.offset: ent.offset + ent.length]
            if msg.caption_entities:
                for ent in msg.caption_entities:
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link    = self._norm(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            dur_sec = int(time_to_seconds(r["duration"])) if r["duration"] else 0
            return (r["title"], r["duration"], dur_sec,
                    r["thumbnails"][0]["url"].split("?")[0], r["id"])

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        link    = self._norm(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            return r["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        link    = self._norm(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            return r["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        link    = self._norm(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            return r["thumbnails"][0]["url"].split("?")[0]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        original_link = link
        if is_live_url(link):
            logger.info(f"🔴 [track] Detected /live/ URL — fetching live info: {link}")
            return await self._track_live(link)
        link    = self._norm(link)
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            duration_min = r.get("duration")
            if not duration_min:
                logger.info(
                    f"🔴 [track] No duration from search — "
                    f"treating as live: {link}"
                )
                live_title = r.get("title") or link
                live_thumb = r["thumbnails"][0]["url"].split("?")[0] if r.get("thumbnails") else ""
                return (
                    {
                        "title":        live_title,
                        "link":         r.get("link") or original_link,
                        "vidid":        r["id"],
                        "duration_min": None,
                        "thumb":        live_thumb,
                    },
                    r["id"],
                )
            return (
                {
                    "title":        r["title"],
                    "link":         r["link"],
                    "vidid":        r["id"],
                    "duration_min": duration_min,
                    "thumb":        r["thumbnails"][0]["url"].split("?")[0],
                },
                r["id"],
            )

    async def _track_live(self, link: str):
        video_id = extract_video_id(link)
        loop     = asyncio.get_event_loop()
        cf       = COOKIE_FILE if os.path.isfile(COOKIE_FILE) else None
        ydl_opts = get_ytdlp_opts(
            {"quiet": True, "skip_download": True},
            use_cookie_file=cf,
        )
        try:
            def _get_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(link, download=False)
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _get_info),
                timeout=30,
            )
            title = info.get("title") or link
            thumb = info.get("thumbnail") or ""
            vid   = info.get("id") or video_id or ""
            return (
                {
                    "title":        title,
                    "link":         link,
                    "vidid":        vid,
                    "duration_min": None,
                    "thumb":        thumb,
                },
                vid,
            )
        except Exception as exc:
            logger.warning(
                f"[_track_live] yt-dlp metadata failed ({exc}) — "
                f"falling back to search …"
            )
            try:
                results = VideosSearch(video_id or link, limit=1)
                for r in (await results.next())["result"]:
                    return (
                        {
                            "title":        r.get("title") or link,
                            "link":         link,
                            "vidid":        r["id"],
                            "duration_min": None,
                            "thumb":        (
                                r["thumbnails"][0]["url"].split("?")[0]
                                if r.get("thumbnails") else ""
                            ),
                        },
                        r["id"],
                    )
            except Exception as exc2:
                logger.error(f"[_track_live] search fallback also failed: {exc2}")
            return (
                {
                    "title":        link,
                    "link":         link,
                    "vidid":        video_id or "",
                    "duration_min": None,
                    "thumb":        "",
                },
                video_id or "",
            )

    async def slider(
        self, link: str, query_type: int, videoid: Union[bool, str] = None
    ):
        if videoid:
            link = self.base + link
        link    = self._norm(link)
        results = VideosSearch(link, limit=10)
        result  = (await results.next()).get("result")
        r       = result[query_type]
        return (r["title"], r["duration"],
                r["thumbnails"][0]["url"].split("?")[0], r["id"])

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link     = self._norm(link)
        cf       = COOKIE_FILE if os.path.isfile(COOKIE_FILE) else None
        ydl_opts = get_ytdlp_opts({"quiet": True}, use_cookie_file=cf)
        loop     = asyncio.get_event_loop()
        def _get():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                out  = []
                for fmt in info.get("formats", []):
                    try:
                        if "dash" not in str(fmt.get("format", "")).lower():
                            out.append({
                                "format":      fmt.get("format"),
                                "filesize":    fmt.get("filesize"),
                                "format_id":   fmt.get("format_id"),
                                "ext":         fmt.get("ext"),
                                "format_note": fmt.get("format_note"),
                                "yturl":       link,
                            })
                    except Exception:
                        pass
                return out
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _get), timeout=60)
            return result, link
        except Exception as exc:
            logger.error(f"formats() error: {exc}")
            return [], link

    async def playlist(
        self, link: str, limit: int, user_id,
        videoid: Union[bool, str] = None,
    ) -> list:
        if videoid:
            link = self.listbase + link
        link     = self._norm(link)
        cf       = COOKIE_FILE if os.path.isfile(COOKIE_FILE) else None
        ydl_opts = get_ytdlp_opts(
            {"quiet": True, "extract_flat": True, "playlistend": limit},
            use_cookie_file=cf,
        )
        loop = asyncio.get_event_loop()
        try:
            def _get():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    if "entries" in info:
                        return [e["id"] for e in info["entries"] if e.get("id")]
                    return []
            return await asyncio.wait_for(
                loop.run_in_executor(None, _get), timeout=60)
        except Exception as exc:
            logger.error(f"playlist() error: {exc}")
            return []

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        try:
            f = await download_video(link)
            if f and os.path.exists(f):
                return 1, f
            return 0, "Video download failed"
        except Exception as exc:
            return 0, f"Video failed: {str(exc)[:100]}"

    async def download(
        self,
        link:      str,
        mystic,
        video:     Union[bool, str] = None,
        videoid:   Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title:     Union[bool, str] = None,
    ) -> tuple:
        if videoid:
            link = self.base + link
        display_title = str(title) if title else ""
        if not display_title:
            try:
                display_title = await self.title(link) or ""
            except Exception:
                display_title = extract_video_id(link) or ""
        try:
            if songvideo or songaudio:
                f = await download_song(link, mystic=mystic, title=display_title)
            elif video:
                f = await download_video(link, mystic=mystic, title=display_title)
            else:
                f = await download_song(link, mystic=mystic, title=display_title)
            if not f or not os.path.exists(f):
                logger.error(f"download() — file missing: {f!r}")
                return None, False
            return f, True
        except Exception as exc:
            logger.error(f"download() exception: {exc}")
            return None, False

    async def live_stream(
        self,
        link:    str,
        videoid: Union[bool, str] = None,
        video:   bool = False,
    ) -> Optional[str]:
        if videoid:
            link = self.base + link
        return await live_stream(link, video=video)
