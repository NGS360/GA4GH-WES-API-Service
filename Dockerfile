# syntax=docker/dockerfile:1
#
# GA4GH WES service image.
#
# Web (default CMD): gunicorn + uvicorn workers on :8000, same as the Procfile.
# Migrations are NOT run on web start. Run them as a one-off task with the same
# image and the same environment (SQLALCHEMY_DATABASE_URI or ENV_SECRETS):
#
#   docker run --rm --env-file wes.env <image> alembic upgrade head
#
# Health endpoint: GET /healthcheck -> {"status": "healthy"}

ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.13-slim

FROM ${PYTHON_IMAGE} AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "uv==0.13.6"

WORKDIR /app
COPY pyproject.toml uv.lock ./
# Install locked runtime dependencies only. The app is run from /app/src
# (imports are `src.wes_service...`), so the project itself is not installed.
RUN uv sync --locked --no-dev --no-install-project


FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 wes \
    && useradd --system --uid 10001 --gid 10001 --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin wes \
    && mkdir -p /var/wes/storage \
    && chown 10001:10001 /var/wes/storage

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthcheck', timeout=4).status == 200 else 1)"]

CMD ["gunicorn", "src.wes_service.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
