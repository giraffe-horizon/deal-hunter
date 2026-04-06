FROM python:3.12-slim

WORKDIR /app

# Install tini (PID 1) and supercronic (non-root cron)
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends tini curl \
    && curl -fsSL https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-${TARGETARCH} -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY deal_hunter.py .
COPY feedback_bot.py .
COPY sources/ sources/
COPY filters/ filters/
COPY notifiers/ notifiers/
COPY utils/ utils/
COPY stores/ stores/
COPY storage/ storage/
COPY visualization/ visualization/
COPY examples/ examples/
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Create non-root user and directories
RUN useradd --create-home --shell /bin/bash dealer \
    && mkdir -p profiles state \
    && chown -R dealer:dealer /app

# Entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Volumes for persistent data and config
VOLUME ["/app/profiles", "/app/state"]

USER dealer

ENTRYPOINT ["tini", "--", "/entrypoint.sh"]
