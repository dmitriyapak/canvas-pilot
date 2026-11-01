# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
WORKDIR /app
COPY requirements-server.txt ./
# Optional combined CA bundle is used only in managed build environments.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements-server.txt && \
    python -m playwright install --with-deps chromium && \
    groupadd --gid 10001 penn && useradd --uid 10001 --gid penn --create-home penn && \
    mkdir -p /data /run/penn-browser && chown penn:penn /data /run/penn-browser
COPY --chown=10001:10001 src/penn_server ./src/penn_server
COPY --chown=10001:10001 src/__init__.py ./src/__init__.py
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "src.penn_server"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD python -c "import http.client,os,urllib.parse; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=3); c.request('GET','/healthz',headers={'Host':urllib.parse.urlsplit(os.environ['PENN_PUBLIC_URL']).netloc}); assert c.getresponse().status==200"
