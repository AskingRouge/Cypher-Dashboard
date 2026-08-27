FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 dashboard \
    && useradd --uid 10001 --gid dashboard --create-home --shell /usr/sbin/nologin dashboard

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

COPY --chown=dashboard:dashboard app ./app
COPY --chown=dashboard:dashboard migrations ./migrations
COPY --chown=dashboard:dashboard config.py run.py ./
COPY --chown=dashboard:dashboard docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod 755 /app/docker/entrypoint.sh

USER dashboard

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]

# APScheduler is embedded in the web process, so this must stay at one worker.
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "60", "--graceful-timeout", "30", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "run:app"]
