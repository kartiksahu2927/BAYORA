FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BAYORA_DATA_DIR=/var/lib/bayora \
    LLM_PROVIDER=fixture

WORKDIR /opt/bayora
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --system --uid 10001 --create-home bayora && mkdir -p /var/lib/bayora/database /var/lib/bayora/audit /var/lib/bayora/application && chown -R bayora:bayora /opt/bayora /var/lib/bayora

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["bayora", "serve", "--host", "0.0.0.0", "--port", "8080"]
