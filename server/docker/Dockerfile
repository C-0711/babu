# babu-web im Container — der Code ist Teil des Images, die Daten sind Volumes.
# Deploy = Image neu bauen + `docker compose up -d`, nicht mehr Dateien kopieren.
FROM python:3.12-slim

# git braucht boxschreiber (Klon fetch/commit/push) und der Lese-Pfad in den
# Bare-Store (git show/ls-tree/cat-file). Sonst nichts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY belegreview /app
WORKDIR /app

# HOME=/data: alle Path.home()-Pfade (babu-web/, inspektor-store/, …) zeigen
# auf die gemounteten Volumes — der Code bleibt unverändert.
ENV HOME=/data \
    PYTHONUNBUFFERED=1

CMD ["python", "babu_web.py"]
