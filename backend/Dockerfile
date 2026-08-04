FROM python:3.12-slim

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

# Navegador headless: solo se instala si construyes con
#   INSTALL_PLAYWRIGHT=true docker compose build
# Añade ~500 MB a la imagen, por eso está desactivado por defecto.
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        pip install --no-cache-dir playwright==1.49.1 && \
        playwright install --with-deps chromium ; \
    fi

COPY . .

RUN mkdir -p /data/audio /data/piper /data/beat

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
