FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ===============================
# Dependências
# ===============================
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===============================
# Código do backend
# ===============================
COPY backend/app ./app
COPY backend/tests ./tests

# ===============================
# Start FastAPI (Railway-safe)
# ===============================
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
