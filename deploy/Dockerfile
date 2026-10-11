# Static map site (Caddy). Build context = repo root.
FROM caddy:2-alpine

WORKDIR /srv/map
COPY map/ /srv/map/

# The repo ships map/data.json.gz (lean). Produce data.json at build.
RUN set -eux; \
    if [ ! -f data.json ] && [ -f data.json.gz ]; then gzip -dkf data.json.gz; fi

COPY deploy/Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
