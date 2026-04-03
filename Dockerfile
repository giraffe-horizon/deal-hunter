FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY deal_hunter.py .
COPY sources/ sources/
COPY filters/ filters/
COPY notifiers/ notifiers/
COPY utils/ utils/
COPY stores/ stores/
COPY examples/ examples/

# Create directories for runtime data
RUN mkdir -p profiles state

# Install cron
RUN apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash dealer

# Entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Volumes for persistent data and config
VOLUME ["/app/profiles", "/app/state"]

ENTRYPOINT ["/entrypoint.sh"]
