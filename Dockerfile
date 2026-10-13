FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so this layer is cached when only application code changes.
COPY requirements.txt requirements-dev.txt ./
# The test image (docker-compose "tests" service) also installs pytest/httpx2.
ARG INSTALL_DEV=false
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Run as an unprivileged user; the code stays owned by root, so it's read-only for the app (SEC-04).
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Apply migrations, then start the API (DB-01).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
