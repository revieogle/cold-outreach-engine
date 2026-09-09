# ==============================================================================
# Dockerfile for Cold Email Outreach Engine & Master Inbox
# Ultra-lightweight: Runs entirely on Python Standard Library (No pip dependencies)
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cloud persistent volume directory
ENV DATA_DIR=/data
ENV PORT=8080

WORKDIR /app

# Copy application files
COPY outreach_engine.py /app/outreach_engine.py
COPY dashboard.html /app/dashboard.html

# Create persistent data directory and mount point
RUN mkdir -p /data

EXPOSE 8080

VOLUME ["/data"]

CMD ["python", "outreach_engine.py"]
