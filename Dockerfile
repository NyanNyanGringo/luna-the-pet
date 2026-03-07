# Multi-stage сборка: фронтенд (Vue 3) + бэкенд (FastAPI) в одном образе.
# Итоговый образ раздаёт собранный SPA как статику через FastAPI.

# --- Этап 1: Сборка фронтенда ---
FROM node:22-slim AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/ .
RUN npm run build

# --- Этап 2: Backend + собранный фронтенд ---
FROM python:3.11-slim AS runtime

# ffmpeg нужен для обработки голосовых сообщений (pydub)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Директория для загрузок медиафайлов
RUN mkdir -p /data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
