ARG PYTHON=3.13

# One stage: every dependency has a ready-made wheel for Intel/AMD and ARM, so nothing is compiled
FROM python:${PYTHON}-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2 \
    PUID=0 \
    PGID=0 \
    TZ=UTC
# MALLOC_ARENA_MAX=2: many threads would otherwise each keep their own memory pool, which only grows

COPY --from=tianon/gosu /gosu /usr/local/bin/

COPY requirements.txt .
RUN pip3 install -r requirements.txt

RUN groupadd -g 1000 kapowarr && \
    useradd -u 1000 -g kapowarr -d /nonexistent -M -s /bin/bash kapowarr && \
    mkdir -p /app/db /app/logs /app/temp_downloads

COPY --chmod=755 . .
RUN python3 -m compileall -q /app/backend /app/frontend /app/Kapowarr.py

EXPOSE 5656

# Up when the web server accepts connections (works with any URL base)
HEALTHCHECK --interval=60s --timeout=5s --start-period=90s --retries=3 \
    CMD python3 -c "import socket; socket.create_connection(('127.0.0.1', 5656), 3).close()"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python3", "/app/Kapowarr.py", "--LogFolder", "/app/logs"]
