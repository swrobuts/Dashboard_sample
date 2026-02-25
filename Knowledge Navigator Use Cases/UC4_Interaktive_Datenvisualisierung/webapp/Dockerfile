FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050
CMD ["gunicorn", "app:server", "-b", "0.0.0.0:8050", "--workers", "2", "--timeout", "120"]
