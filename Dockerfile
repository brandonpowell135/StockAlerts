FROM python:3.12-slim

# Links the GHCR package to this repo (shows it on the repo page and lets Actions publish it).
LABEL org.opencontainers.image.source=https://github.com/brandonpowell135/StockAlerts

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ALERTS_FILE=/app/data/alerts.json

WORKDIR /app

# Install dependencies first so code changes don't invalidate this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# Run as a non-root user; alerts persist on a volume across image updates.
RUN useradd --create-home bot && mkdir -p /app/data && chown bot:bot /app/data
USER bot
VOLUME /app/data

CMD ["python", "main.py"]
