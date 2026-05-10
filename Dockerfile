# ══════════════════════════════════════════════════════════
#  STAGE 1 — builder
#  Heavy installs: Python deps, Playwright browser, bgutil
# ══════════════════════════════════════════════════════════
FROM python:3.10-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Build-time system tools only
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg \
        # Needed to compile some pip packages (aiohttp, cryptography, etc.)
        gcc g++ libffi-dev libssl-dev \
        # Needed by Pillow at build time
        libjpeg-dev zlib1g-dev \
        # Needed by lxml / beautifulsoup4
        libxml2-dev libxslt1-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt /tmp/*

WORKDIR /build

# ── Python packages ───────────────────────────────────────
COPY requirements.txt .

RUN pip install --upgrade pip --no-cache-dir \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt \
    && pip install --prefix=/install --no-cache-dir \
         bgutil-ytdlp-pot-provider \
         playwright \
         playwright-stealth \
         camoufox \
    # Strip test/docs folders from every installed package
    && find /install -depth \
         \( -type d \( -name "tests" -o -name "test" \
                    -o -name "docs"  -o -name "examples" \) \) \
         -exec rm -rf '{}' + 2>/dev/null || true \
    && find /install -name "*.pyc" -delete 2>/dev/null || true \
    && rm -rf /tmp/*

# ── Playwright: Chromium only ─────────────────────────────
RUN PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    python -m playwright install chromium \
    && rm -rf /tmp/*

# ── bgutil server ─────────────────────────────────────────
# tsx is a devDependency but REQUIRED at runtime — it executes src/main.ts directly
RUN git clone --single-branch --depth 1 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
        /build/bgutil-ytdlp-pot-provider \
    && cd /build/bgutil-ytdlp-pot-provider/server \
    && npm ci --omit=dev \
    && npm install --save-dev tsx \
    && npm cache clean --force \
    && rm -rf /root/.npm /tmp/* \
    && test -f src/main.ts \
        || (echo "ERROR: src/main.ts missing!" && exit 1) \
    && test -f node_modules/.bin/tsx \
        || (echo "ERROR: tsx missing!" && exit 1) \
    && echo "OK: bgutil verified."


# ══════════════════════════════════════════════════════════
#  STAGE 2 — final runtime image
# ══════════════════════════════════════════════════════════
FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BGUTIL_SERVER_HOME=/app/bgutil-ytdlp-pot-provider/server \
    DEBIAN_FRONTEND=noninteractive \
    NODE_ENV=production

RUN apt-get update \
    # ── Node.js 20 LTS via NodeSource (apt ships v18 which is too old) ──
    && apt-get install -y --no-install-recommends ca-certificates gnupg curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    # ── Media tools ────────────────────────────────────────────────────
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        mpv \
        libsndfile1 \
    # ── OpenCV / MoviePy runtime ────────────────────────────────────────
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
    # ── Playwright / Chromium runtime libs ──────────────────────────────
    && apt-get install -y --no-install-recommends \
        libnss3 libnspr4 \
        libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 \
        libgbm1 libasound2 \
        libpango-1.0-0 libpangocairo-1.0-0 \
        libgtk-3-0 \
        libx11-xcb1 libxcb-dri3-0 libxext6 \
        fonts-liberation \
    # ── py-tgcalls / voice chat audio ───────────────────────────────────
    && apt-get install -y --no-install-recommends \
        libopus0 libopus-dev \
    # ── Pillow runtime ───────────────────────────────────────────────────
    && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
    # ── gitpython needs git at runtime ──────────────────────────────────
    && apt-get install -y --no-install-recommends \
        git \
    # ── Cleanup: remove bootstrap tools, purge apt caches ───────────────
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt \
              /usr/share/doc /usr/share/man \
              /usr/share/locale /tmp/*

WORKDIR /app

# ── Copy only the built artifacts from builder stage ─────
COPY --from=builder /install                          /usr/local
COPY --from=builder /ms-playwright                    /ms-playwright
COPY --from=builder /build/bgutil-ytdlp-pot-provider  /app/bgutil-ytdlp-pot-provider

# ── Application source ────────────────────────────────────
COPY . .

RUN chmod +x start \
    # Strip leftover pyc / __pycache__ from copied packages and app code
    && find /usr/local/lib/python3.10 -depth \
         \( -type d \( -name "tests" -o -name "test" \) \) \
         -exec rm -rf '{}' + 2>/dev/null || true \
    && find /usr/local/lib/python3.10 -name "*.pyc" -delete 2>/dev/null || true \
    && find . -type d -name "__pycache__" -exec rm -rf '{}' + 2>/dev/null || true

CMD ["bash", "start"]
