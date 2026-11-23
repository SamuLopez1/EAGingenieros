# [MVP-08] Extraer texto de PDF, DOCX y XLSX con OCR básico

## Objetivo

Obtener texto trazable sin confundir fallos de extracción con ausencia de requisitos.

## Dependencias

- MVP-07

El PR de extracción parte de `bb46e7ab4b28ec628a300f3cf7680e451d78d11e`, la revisión comprobada del PR #27 de expediente.

## Trabajo incluido

- Crear pipeline por formato y activar OCR solo cuando el PDF no tenga texto suficiente.
- Preservar documento, página/sección/celda y versión como localizadores.
- Procesar en tareas con timeout, límites de páginas/recursos, reintentos e indicadores de calidad.
- Exponer estados de extracción y advertencias al analista.

## Criterios de aceptación

- [ ] Fixtures sintéticas PDF textual, escaneado, DOCX y XLSX producen texto y localizadores verificables.
- [ ] Archivo corrupto, cifrado o exceso de presupuesto termina con error visible y recuperable.
- [ ] OCR de mala calidad o texto vacío se marca para revisión; no produce éxito silencioso.
- [ ] Reprocesamiento por hash/versión evita trabajo innecesario sin mezclar versiones.
- [ ] Pruebas offline no requieren OpenAI y comandos de OCR documentan dependencias del sistema.

## Verificación

Desde `apps/api`, con las dependencias fijadas en `requirements.lock` y la configuración del
expediente, aplica la migración y arranca el worker junto al API.

```sh
python -m alembic upgrade head
python -m app.documents.extraction_worker
```

`--once` permite atender una sola tarea. En el detalle de la oportunidad, abre «Extracción de
texto» en la versión disponible y pulsa «Extraer texto». El API consulta y encola en
`GET/POST /api/v1/opportunities/{opportunity_id}/documents/{document_id}/extraction`.
Cada resultado conserva el ID del documento y de la oportunidad, la versión y el SHA-256.
Solicitar de nuevo una versión lista devuelve el resultado existente. «Reintentar extracción»
vuelve a encolar una versión fallida o con avisos.

- PDF usa páginas numeradas desde 1. Una página con menos de 40 caracteres activa OCR.
  Una confianza media inferior a 60, una página ilegible o el agotamiento del presupuesto
  produce un aviso con su página. El PDF tiene un límite de 100 páginas.
- DOCX usa el título de sección cuando existe, la posición del párrafo en el cuerpo o la
  tabla, fila y celda, todo desde 1. El cuerpo principal se recorre en orden. Las imágenes,
  contenido anidado y otras partes del documento pueden requerir revisión directa.
- XLSX usa el nombre de la hoja y la coordenada de celda. Las fórmulas se muestran literalmente.
  Se inspeccionan hasta 20 hojas, 2.000 filas y 64 columnas por hoja.
- Cada intento procesa hasta 1.000 fragmentos y 200.000 caracteres. El worker tiene un plazo
  de 90 segundos por defecto, con hasta dos intentos ante fallos transitorios y un límite de
  espacio de direcciones de 1 GiB en Linux. Los límites pueden producir resultados parciales
  con aviso o un fallo con código explícito.

OCR necesita `pdftoppm` y `tesseract` en el PATH. En Ubuntu, los paquetes usados en CI son
`poppler-utils`, `tesseract-ocr`, `tesseract-ocr-spa` y `tesseract-ocr-eng`. El idioma sugerido es
`spa+eng`. `apps/api/.env.example` documenta el idioma, el máximo predeterminado de 12 páginas OCR
y el plazo del intento. Un motor ausente aparece como aviso de cobertura en la interfaz.

```sh
python -m ruff check .
python -m mypy app
python -m pytest -o addopts='' -q
EAG_TEST_REAL_OCR=1 python -m pytest -q tests/test_extraction.py -k real_ocr
EAG_TEST_POSTGRES=1 python -m pytest -q tests/test_postgres_sync_integration.py -k extraction
```

Las dos variables optativas se pueden definir con `$env:NOMBRE = '1'` en PowerShell. La suite
offline usa fixtures sintéticas y OCR simulado para las ramas de error. La prueba de OCR real
ejecuta los binarios sobre un PDF sintético sin capa textual. La comprobación PostgreSQL usa
Docker y la imagen local `postgres:17.6-bookworm`. Desde la raíz, el recorrido en Chrome reutiliza
el entorno local de expediente con el worker y el proxy Vite.

```sh
python scripts/mvp06_preview.py --dossier --extraction --browser-cli RUTA_A_PLAYWRIGHT_CLI
```

El recorrido usa PostgreSQL, API, worker y navegador reales, con identidad y antivirus de fixture.
Falta inspeccionar localizadores y calidad OCR en una muestra de EAG autorizada y fuera de Git.

## Fuera de alcance

Extracción semántica de requisitos o evaluación de cumplimiento.

## Modelo sugerido para programar

GPT-5.6 Terra · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Añade extracción por formato y OCR básico con trazabilidad y límites de recursos. Prueba escaneados, archivos corruptos y texto vacío. Mantén esta etapa independiente de IA y de evaluación de cumplimiento.
```
