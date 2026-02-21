# Stage 1 — Node build (React + Vite)
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Build output goes to ../static (see vite.config.ts: outDir: '../static')
RUN npm run build

# Stage 2 — Python runtime
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
# Copy built frontend (static/)
COPY --from=frontend-build /app/static ./static/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
