FROM python:3.11-slim

# ===============================
# Configuração base
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ===============================
# Dependências
# ===============================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===============================
# Código da aplicação
# ===============================
COPY app ./app
COPY tests ./tests

# ===============================
# Start FastAPI (Railway-safe)
# ===============================
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
