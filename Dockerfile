# NYSE_DATA — options-intelligence engine + MCP server
# =====================================================
# One image, multiple entrypoints:
#   * default CMD runs the MCP stdio server (Portfolio-track Phase 1/2 deliverable) —
#     an MCP client launches it with `docker run -i --rm ... nyse-options`.
#   * docker-compose overrides `command:` to run the Telegram bot / Streamlit dashboard.
#
# Secrets are NEVER baked in. token.txt / api_keys.env / *.db are excluded by
# .dockerignore and mounted at runtime (see docker-compose.yml and docs/DOCKER.md).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    TZ=America/New_York \
    NYSE_DB_PATH=/data/US_data_OpenBB.db

WORKDIR /app

# System libraries:
#  - build-essential: compile any dependency that ships only an sdist for py3.12
#  - libgomp1:        OpenMP runtime required by numpy/scipy wheels
#  - fontconfig:      fonts for matplotlib chart rendering (headless, Agg backend)
#  - curl/ca-certs:   TLS + data fetches (yfinance / OpenBB / news feeds)
#  - tzdata:          America/New_York market-hours logic
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates libgomp1 fontconfig tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so this layer caches independently of source changes.
# requirements.txt = bot/dashboard/MCP core; requirements_openbb.txt = pinned OpenBB stack.
COPY requirements.txt requirements_openbb.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -r requirements_openbb.txt

# Application code. Secrets and *.db are excluded via .dockerignore.
COPY . .

# Mount points created at build time so runtime bind-mounts land cleanly.
#   /data      -> host directory holding US_data_OpenBB.db (+ intraday / backup DBs)
#   /app/logs  -> writable log dir
RUN mkdir -p /data /app/logs

# Default entrypoint: the MCP stdio server. It speaks JSON-RPC on stdout, so run with -i.
CMD ["python", "mcp_server.py"]
