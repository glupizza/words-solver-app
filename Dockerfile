# Frontend build stage
FROM node:18-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# Backend runtime stage
FROM python:3.11-slim AS backend
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ca-certificates \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/

# Put built SPA into Flask static folder
COPY --from=frontend-builder /app/frontend/dist ./backend/static

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD gunicorn backend.app:app \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers 1 \
  --threads 4 \
  --timeout 45 \
  --graceful-timeout 30 \
  --keep-alive 2 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile - \
  --error-logfile -
