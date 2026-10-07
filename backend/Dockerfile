# Base fijada a Debian 12 «bookworm» a propósito, no al «slim» genérico.
# El genérico sigue a la última Debian estable, y Playwright solo conoce las
# versiones que existían cuando se publicó: ante una desconocida recurre a su
# lista de paquetes de Ubuntu, que incluye nombres inexistentes en Debian
# (ttf-ubuntu-font-family, ttf-unifont) y la construcción se cae.
FROM python:3.12-slim-bookworm

# ffmpeg   -> unir fragmentos de audio y medir su duración
# curl/ca-certificates -> descargas y TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Navegador headless (opcional)
#
# Solo se instala si construyes con INSTALL_PLAYWRIGHT=true en el .env.
# Añade unos 500 MB a la imagen, por eso está desactivado por defecto.
#
# Las bibliotecas del sistema se instalan aquí con sus nombres de Debian 12 en
# vez de dejárselo a «playwright install --with-deps»: así la construcción no
# depende de que Playwright acierte a reconocer la distribución.
# ---------------------------------------------------------------------------
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        set -eux; \
        pip install --no-cache-dir playwright==1.49.1; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
            libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
            libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
            libasound2 libatspi2.0-0 libxshmfence1 libx11-6 libxcb1 \
            libxext6 libexpat1 fonts-liberation \
        || playwright install-deps chromium; \
        rm -rf /var/lib/apt/lists/*; \
        playwright install chromium; \
    fi

COPY . .

# Sello de construcción. Se escribe DESPUÉS de copiar el código, así que
# Docker solo lo rehace cuando el código cambió: si el sello es de hace días,
# es que la imagen no se reconstruyó, por muy actualizada que esté la carpeta.
# «git pull» sin «docker compose up -d --build» deja justo esa trampa.
RUN date -u +"%Y-%m-%d %H:%M UTC" > /app/BUILD_STAMP

RUN mkdir -p /data/audio /data/piper /data/beat

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
