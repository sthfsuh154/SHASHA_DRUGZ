# ══════════════════════════════════════════════════════════
#  STAGE 1 — builder
# ══════════════════════════════════════════════════════════
FROM python:3.10-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg \
        gcc g++ libffi-dev libssl-dev \
        libjpeg-dev zlib1g-dev \
        libxml2-dev libxslt1-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt /tmp/*

WORKDIR /build

COPY requirements.txt .

# ── Python packages (installed to /install prefix) ────────
RUN pip install --upgrade pip --no-cache-dir \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt \
    && pip install --prefix=/install --no-cache-dir \
         bgutil-ytdlp-pot-provider \
         playwright \
         playwright-stealth \
         camoufox \
    && find /install -depth \
         \( -type d \( -name "tests" -o -name "test" \
                    -o -name "docs"  -o -name "examples" \) \) \
         -exec rm -rf '{}' + 2>/dev/null || true \
    && find /install -name "*.pyc" -delete 2>/dev/null || true \
    && rm -rf /tmp/*

# ── Playwright: Chromium only ──────────────────────────────
# PYTHONPATH must point to /install so python can find playwright
RUN PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONPATH=/install/lib/python3.10/site-packages \
    python -m playwright install chromium \
    && rm -rf /tmp/*

# ── bgutil server ──────────────────────────────────────────
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
    && apt-get install -y --no-install-recommends ca-certificates gnupg curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        mpv \
        libsndfile1 \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
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
    && apt-get install -y --no-install-recommends \
        libopus0 libopus-dev \
    && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
    && apt-get install -y --no-install-recommends \
        git \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt \
              /usr/share/doc /usr/share/man \
              /usr/share/locale /tmp/*

WORKDIR /app

# ── Copy built artifacts from builder ────────────────────
COPY --from=builder /install                          /usr/local
COPY --from=builder /ms-playwright                    /ms-playwright
COPY --from=builder /build/bgutil-ytdlp-pot-provider  /app/bgutil-ytdlp-pot-provider

# ── Application source ────────────────────────────────────
COPY . .

RUN chmod +x start \
    && find /usr/local/lib/python3.10 -depth \
         \( -type d \( -name "tests" -o -name "test" \) \) \
         -exec rm -rf '{}' + 2>/dev/null || true \
    && find /usr/local/lib/python3.10 -name "*.pyc" -delete 2>/dev/null || true \
    && find . -type d -name "__pycache__" -exec rm -rf '{}' + 2>/dev/null || true

CMD ["bash", "start"]
