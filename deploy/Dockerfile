# Static map site (Caddy). Build context = repo root.
FROM caddy:2-alpine

WORKDIR /srv/map
COPY map/ /srv/map/

# The repo ships map/data.json.gz (lean). Produce data.json at build.
RUN set -eux; \
    for f in data.json odbori.json odbori.csv; do \
      if [ ! -f "$f" ] && [ -f "$f.gz" ]; then gzip -dkf "$f.gz"; fi; \
    done

COPY deploy/Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
