FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    UZI_WEB_HOST=0.0.0.0 \
    UZI_WEB_PORT=8977

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    gcc \
    git \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
COPY requirements-web.txt ./requirements-web.txt
RUN pip install -U pip setuptools wheel && \
    pip install -r requirements-web.txt && \
    python -m playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/data /app/logs /app/reports/jobs \
    /app/skills/deep-analysis/scripts/.cache \
    /app/skills/deep-analysis/scripts/reports

EXPOSE 8977

CMD ["python", "main.py", "--serve-only", "--host", "0.0.0.0", "--port", "8977"]
