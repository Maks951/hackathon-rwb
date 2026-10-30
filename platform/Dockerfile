# Adapted from Dmitry's Docker branch b8ca420 (docker-fastapi-template.zip).
FROM docker.io/library/python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RWB_GENERATED_ROOT=/app/generated \
    RWB_TEMPLATES_ROOT=/app/templates

WORKDIR /app/platform
COPY platform/requirements-integration.lock.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home appuser \
    && mkdir -p /app/generated \
    && chown appuser:appuser /app/generated
COPY --chown=appuser:appuser platform/ /app/platform/
COPY --chown=appuser:appuser templates/ /app/templates/
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
