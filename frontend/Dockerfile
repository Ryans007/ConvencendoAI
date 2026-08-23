FROM node:22-slim

ENV NPM_CONFIG_UPDATE_NOTIFIER=false

# Diferente da imagem do Python, node:22-slim nao traz o pacote de certificados: nao
# existe /etc/ssl/certs nem update-ca-certificates. Instalar antes de qualquer passo que
# dependa de TLS, senao o mecanismo de CA abaixo nao tem como funcionar. O apt do Debian
# usa HTTP nas fontes padrao, entao este passo funciona mesmo atras do proxy.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Mesmo mecanismo do backend: a CA corporativa entra no trust store antes de qualquer
# download, senao a inspecao TLS do proxy derruba o npm ci. Com o argumento vazio, esta
# etapa nao faz nada.
ARG CORPORATE_CA_CERT=""
COPY certs/ /tmp/certs/
RUN if [ -n "$CORPORATE_CA_CERT" ]; then \
        cp "/tmp/certs/${CORPORATE_CA_CERT}" /usr/local/share/ca-certificates/ && \
        update-ca-certificates; \
    fi && \
    rm -rf /tmp/certs

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# O node_modules e recriado dentro do container e protegido por um volume nomeado no
# compose: o bind mount de /app viria do host, que nao tem node_modules instalado, e
# encobriria o que foi instalado no build.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
