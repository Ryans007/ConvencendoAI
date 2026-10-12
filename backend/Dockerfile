FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

# A CA corporativa entra no trust store antes de qualquer download: numa rede com
# inspecao TLS, sem isso a instalacao de dependencias falha em UnknownIssuer.
# Com o argumento vazio, esta etapa nao faz nada.
ARG CORPORATE_CA_CERT=""
COPY certs/ /tmp/certs/
RUN if [ -n "$CORPORATE_CA_CERT" ]; then \
        cp "/tmp/certs/${CORPORATE_CA_CERT}" /usr/local/share/ca-certificates/ && \
        update-ca-certificates; \
    fi && \
    rm -rf /tmp/certs

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

RUN pip install --no-cache-dir uv==0.11.19

WORKDIR /app

# O ambiente virtual vive fora de /app de proposito. Em runtime /app recebe um bind
# mount do host, que esconderia um .venv criado durante o build.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

RUN DJANGO_SETTINGS_MODULE=core.settings.prod     DJANGO_SECRET_KEY=build-only-key     POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build     python manage.py collectstatic --noinput --ignore test_client.html

RUN useradd --system --create-home --uid 10001 app     && chown -R app:app /app

USER app

EXPOSE 8000

# Gunicorn como gerente de processos, com worker ASGI: serve HTTP hoje e nao precisa
# ser trocado quando a sessao ao vivo passar a usar WebSocket. O compose sobrescreve
# este comando em desenvolvimento para ganhar recarregamento automatico.
CMD ["gunicorn", "core.asgi:application", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--access-logfile", "-"]
