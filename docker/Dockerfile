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
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install -U pip setuptools wheel && \
    pip install -r requirements.txt && \
    pip install fastapi "uvicorn[standard]" jinja2 pydantic && \
    python -m playwright install chromium

COPY . .

RUN mkdir -p /app/data /app/web-reports \
    /app/skills/deep-analysis/scripts/.cache \
    /app/skills/deep-analysis/scripts/reports

EXPOSE 8977

CMD ["bash", "-lc", "uvicorn web.app:app --host ${UZI_WEB_HOST:-0.0.0.0} --port ${UZI_WEB_PORT:-8977}"]
