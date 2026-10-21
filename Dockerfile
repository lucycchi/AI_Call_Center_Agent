# The Meridian chat agent's image (R77). Each release carries the code, prompts, search index and seed database, so
# rolling back a release rolls them back together (R83). The databases live on the Fly.io volume at /data.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app/ app/
COPY data/index/ data/index/
COPY data/kb_text/ data/kb_text/
COPY data/document_list.csv data/
COPY call_data/knowledge_base/ call_data/knowledge_base/
COPY call_data/scheduling_db/meridian_scheduling.sqlite call_data/scheduling_db/
COPY docs/FINDINGS.md docs/
# The Results tab's final summary, once Task 27 writes data/results/final (the wildcard copies nothing until then).
COPY data/result[s]/ data/results/
COPY scripts/entrypoint.sh scripts/

ENV DATABASE_PATH=/data/scheduling.sqlite \
    OPS_DATABASE_PATH=/data/operations.sqlite

EXPOSE 8080
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
# One worker: the reset gate, the scheduler and the message limits live in this one process.
CMD ["uvicorn", "app.web.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
