# ---- Stage 1: Build ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy only dependency-related files first for layer caching
COPY pyproject.toml README.md ./
COPY src/ src/

# Build wheel with browser + api extras
RUN pip wheel --no-cache-dir --wheel-dir /wheels .[browser,api]

# ---- Stage 2: Runtime ----
FROM python:3.12-slim

# Playwright system dependencies (Chromium needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
        libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 flyto \
    && useradd --uid 1000 --gid flyto --create-home flyto

WORKDIR /app

# Install wheels from builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels flyto-core[browser,api] \
    && rm -rf /wheels

# Install Playwright Chromium only (as root, before switching user)
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN playwright install chromium \
    && chmod -R o+rx /opt/pw-browsers

# Copy source (for runtime access to package data / configs)
COPY --chown=flyto:flyto . /app

# Switch to non-root
USER flyto

EXPOSE 8000

# Health check against the API
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["flyto-serve"]
