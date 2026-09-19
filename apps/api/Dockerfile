# Imagen de la API. Se instala desde el lockfile para que la imagen sea
# reproducible: sin él, una reconstrucción podría traer versiones distintas y
# un fallo aparecería solo en producción.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependencias del sistema para la extracción de documentos:
#   - tesseract-ocr y su paquete de español: reconocimiento de PDF escaneados.
#     Sin el idioma instalado, el OCR de un pliego en español devolvería basura
#     sin dar error, que es peor que fallar.
#   - poppler-utils: pdf2image lo necesita para rasterizar páginas.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        tesseract-ocr \
        tesseract-ocr-spa \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias de Python se copian e instalan antes que el código para
# aprovechar la caché de capas: cambiar un archivo de la aplicación no
# reinstala todo.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Verificación en tiempo de construcción: si falta el idioma español o
# poppler, el OCR fallaría en producción de forma silenciosa. Mejor fallar aquí.
RUN tesseract --list-langs 2>&1 | grep -qx spa \
    && command -v pdftoppm >/dev/null \
    && echo "OCR listo: tesseract con español y poppler presentes"

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts

# Usuario sin privilegios: un proceso comprometido no debe ser root.
RUN useradd --create-home --uid 10001 eag && chown -R eag:eag /srv
USER eag

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
