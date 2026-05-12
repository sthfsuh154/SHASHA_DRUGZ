import subprocess
import time
import datetime
import os

# ⬇️ Change this to your bot's start command
BOT_COMMAND = ["bash", "start"]
REQUIREMENTS_FILE = "requirements.txt"

MAX_RESTARTS = 0          # 0 = unlimited restarts
RESTART_DELAY = 10        # seconds to wait before restarting


def log(message: str):
    """Log messages with timestamp to console and file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}"
    print(msg)
    with open("autorestart.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def install_requirements():
    """Install dependencies from requirements.txt if it exists."""
    if os.path.exists(REQUIREMENTS_FILE):
        log("📦 Installing dependencies from requirements.txt...")
        try:
            subprocess.check_call(["pip", "install", "-r", REQUIREMENTS_FILE])
            log("✅ Requirements installed successfully.")
        except subprocess.CalledProcessError as e:
            log(f"❌ Error installing requirements: {e}")
    else:
        log("⚠️ No requirements.txt found — skipping dependency installation.")


def start_bot() -> int:
    """Start the bot process, wait for it to finish, return exit code."""
    log(f"🚀 Launching bot: {' '.join(BOT_COMMAND)}")
    try:
        process = subprocess.Popen(BOT_COMMAND)
        process.wait()
        return process.returncode
    except FileNotFoundError as e:
        log(f"❌ Could not start bot — command not found: {e}")
        return -1
    except Exception as e:
        log(f"❌ Unexpected error while starting bot: {e}")
        return -1


def autorestart():
    """
    External process wrapper.
    Continuously restarts the bot if it stops or crashes.
    Run this file directly:  python autorestart.py
    """
    install_requirements()

    restart_count = 0

    while True:
        exit_code = start_bot()

        # Exit code 0  = clean shutdown (intentional), stop restarting
        if exit_code == 0:
            log("✅ Bot exited cleanly (exit code 0). Not restarting.")
            break

        restart_count += 1
        log(
            f"💥 Bot stopped (exit code: {exit_code}) | "
            f"Restart #{restart_count} in {RESTART_DELAY}s..."
        )

        if MAX_RESTARTS and restart_count >= MAX_RESTARTS:
            log(f"🛑 Reached max restarts ({MAX_RESTARTS}). Stopping.")
            break

        time.sleep(RESTART_DELAY)
        install_requirements()


if __name__ == "__main__":
    log("🔁 AutoRestart system started.")
    try:
        autorestart()
    except KeyboardInterrupt:
        log("🛑 AutoRestart stopped manually (KeyboardInterrupt).")
    except Exception as e:
        log(f"💀 AutoRestart fatal error: {e}")
