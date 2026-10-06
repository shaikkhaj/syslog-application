FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 8000  : REST API + Swagger docs
# 514   : syslog UDP/TCP listeners (runs as root to bind privileged port)
# 6514  : reserved for TLS syslog (later phase)
EXPOSE 8000 514/udp 514/tcp 6514/tcp

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
