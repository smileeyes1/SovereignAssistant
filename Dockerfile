FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMEGA_DB_PATH=/data/omega.db \
    OMEGA_HOST=0.0.0.0 \
    OMEGA_PORT=8080

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 omega \
    && mkdir -p /data \
    && chown -R omega:omega /data /app

USER omega
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('OMEGA_PORT','8080')+'/healthz', timeout=3)" || exit 1

CMD ["python", "-m", "app.hakim.run_autonomy"]
