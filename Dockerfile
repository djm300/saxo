FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY cli ./cli
COPY shared ./shared
COPY web ./web
COPY docs ./docs

RUN pip install --upgrade pip && pip install ".[cli]"

EXPOSE 5000

CMD ["saxo-web"]
