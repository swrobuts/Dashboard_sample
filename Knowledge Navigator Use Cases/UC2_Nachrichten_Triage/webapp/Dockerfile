FROM python:3.12-slim

WORKDIR /app

# Dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Port
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
