FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN adduser --disabled-password --gecos "" --uid 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY config/ ./config/

RUN mkdir -p /app/traces && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Cloud Run injects $PORT; the default keeps local `docker run` working.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
