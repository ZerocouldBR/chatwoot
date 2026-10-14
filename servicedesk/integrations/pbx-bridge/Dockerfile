# sd-ops (evolução da pbx-bridge): telefonia 55PBX, tickets de negócio, SLA, gravações e CTI do ServiceDesk.
# Imagem leve (python:3.12-slim + ffmpeg), usuário sem privilégio. A pbx-bridge legada continua no pacote
# (python -m pbx_bridge ...) para o backfill de gravações históricas.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080 \
    SDOPS_STORAGE_DIR=/data/recordings DB_PATH=/data/pbx-bridge.sqlite3
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin pbx \
 && mkdir -p /data/recordings && chown -R pbx:pbx /data && chmod 700 /data/recordings
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY pbx_bridge ./pbx_bridge
COPY sd_ops ./sd_ops
COPY openapi.json ./openapi.json
USER pbx
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/sd-ops/health', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "sd_ops", "serve"]
