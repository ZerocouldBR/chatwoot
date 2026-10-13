# pbx-bridge: ponte 55PBX -> ServiceDesk. Imagem leve (python:3.12-slim + ffmpeg), usuário sem privilégio.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DB_PATH=/data/pbx-bridge.sqlite3 PORT=8080
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin pbx \
 && mkdir -p /data && chown pbx:pbx /data
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY pbx_bridge ./pbx_bridge
USER pbx
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/integracoes/55pbx/health', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "pbx_bridge", "serve"]
