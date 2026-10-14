# qa-pipeline: transcrição (STT local), resumo e QA com IA, para o ServiceDesk.
# Worker assíncrono (consome sd:events) + API do console de QA. Sem segredos na imagem.
#
# Gravações: o qa (uid 10002) é membro do grupo "sdrec" (gid 10010), grupo principal do sd-ops (uid 10001) na imagem
# dele. Com o volume de gravações montado só leitura e os modos 0640/0750 do sd-ops, o qa lê sem ser dono e sem
# poder alterar nada. Ver docs/INTEGRACAO-55PBX.md §17.
FROM python:3.12-slim
ARG SDREC_GID=10010
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models HF_HUB_DISABLE_TELEMETRY=1 PORT=8090
RUN groupadd --gid "$SDREC_GID" sdrec \
 && useradd --uid 10002 --groups sdrec --create-home --shell /usr/sbin/nologin qa \
 && mkdir -p /models /data && chown qa:qa /models /data
WORKDIR /app
COPY requirements.txt requirements-stt.txt ./
ARG WITH_STT=1
RUN pip install -r requirements.txt \
 && if [ "$WITH_STT" = "1" ]; then pip install -r requirements-stt.txt; fi
COPY alembic.ini ./
COPY qa_pipeline ./qa_pipeline
USER qa
VOLUME ["/models", "/data"]
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/sd-qa/health', timeout=4).status == 200 else 1)"
# "api" (console de QA) ou "worker" (pipeline). Mesmo código, processos separados.
CMD ["python", "-m", "qa_pipeline", "api"]
