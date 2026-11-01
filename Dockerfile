FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

# Avoid prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

WORKDIR /app

# Install Xvfb, VNC, noVNC (web VNC client), cron, and process manager
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    cron \
    curl \
    git \
    supervisor \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries
RUN python -m playwright install --with-deps chromium

# Copy application files
COPY . /app/

# Make scripts executable
RUN chmod +x /app/*.py /app/*.sh 2>/dev/null || true

# Copy supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8585 6080

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
