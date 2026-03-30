# ---------- build stage ----------
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY clawlink_agent/ ./clawlink_agent/

RUN pip install --no-cache-dir --prefix=/install .

# ---------- runtime stage ----------
FROM python:3.12-slim

LABEL maintainer="ClawLink Team"

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/clawlink_agent/ ./clawlink_agent/

RUN mkdir -p /app/memories \
    # Install Node.js and npm for openclaw (npm) support
    && apt-get update \
    && apt-get install -y curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm --version \
    && node --version \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

EXPOSE 8430

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8430/ping')" || exit 1

# Default: start agent with configurable env vars
# Override AGENT_ID, DISPLAY_NAME, ROUTER_URL, PORT at runtime
ENV AGENT_ID=agent-default
ENV DISPLAY_NAME="CLAWLINK Agent"
ENV ROUTER_URL=""
ENV PORT=8430

CMD clawlink-agent serve \
    --agent-id $AGENT_ID \
    --display-name "$DISPLAY_NAME" \
    --memory-dir /app/memories \
    --router-url "$ROUTER_URL" \
    --port $PORT \
    --no-write-mcp-config
