# Imagen de la API. Se instala desde el lockfile para que la imagen sea
# reproducible: sin él, una reconstrucción podría traer versiones distintas y
# un fallo aparecería solo en producción.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Las dependencias se copian e instalan antes que el código para aprovechar la
# caché de capas: cambiar un archivo de la aplicación no reinstala todo.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts

# Usuario sin privilegios: un proceso comprometido no debe ser root.
RUN useradd --create-home --uid 10001 eag && chown -R eag:eag /srv
USER eag

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
