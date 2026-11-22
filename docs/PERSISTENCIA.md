# Sincronización de oportunidades de SECOP II

MVP-05 amplía el catálogo público de procesos [p6dx-8zbt](https://www.datos.gov.co/api/views/p6dx-8zbt.json).
El catálogo pertenece a EAG y sus rutas exigen una pertenencia validada por
MVP-04. Analistas y administradores de EAG pueden leerlo. Solo un administrador
puede disparar la sincronización manual.

## Preparación y operación

Desde `apps/api`, instalar `requirements.lock`, configurar
`EAG_DATABASE_URL` en el backend y aplicar `python -m alembic upgrade head`.
Las dos revisiones administran oportunidades, historial y cursores. Las
migraciones de Supabase Auth de MVP-04 conservan su procedimiento separado.
La API sin base configurada devuelve HTTP 503 en las rutas del catálogo.

| Operación | Entrada | Comportamiento |
| --- | --- | --- |
| Carga inicial | `POST /api/v1/sync-runs?mode=initial` | Recorre el catálogo por identificador, sin filtro temporal ni de estado. Incluye registros antiguos y sin fecha. `limit=N` acota un lote y `resume=true` retoma desde la posición guardada. |
| Incremental manual | `POST /api/v1/sync-runs?mode=incremental` | Revisa la ventana de siete días que termina en el último corte de Bogotá. `resume=true` retoma una ventana fallida con el mismo corte. |
| Incremental diario | `python -m app.secop.daily --run` | Usa el mismo servicio y registra el disparador `daily`. Sale con código 1 si falla para que el programador pueda reintentar. |
| Diagnóstico | `GET /api/v1/sync-runs` | Expone el resultado, contadores, avance, tipo de error y límites de la ventana cuando corresponden. |

Usar una conexión PostgreSQL directa o con pool de sesión para el bloqueo.

La carga inicial puede necesitar varios lotes según el límite de peticiones
de `EAG_SECOP_MAX_REQUESTS`. Si se alcanza, queda una ejecución fallida con el
avance guardado. Para continuar, usar `resume=true`. El cursor es posicional:
SECOP puede insertar o retirar filas entre páginas. Un nuevo barrido puede
reconciliar omisiones, pues la API pública no da una instantánea estable.

Los [archivos de systemd](../infra/secop/) programan el worker a las 06:00
`America/Bogota`. Ajustar rutas y usuario del servicio a la instalación.
Después de aplicar migraciones y preparar el archivo de entorno en el host,
instalar ambas unidades con el mismo nombre y activar
`systemctl enable --now eag-secop-sync.timer`.
`python -m app.secop.daily --as-of 2026-11-22T11:00:00Z` inspecciona el plan sin
red ni escritura. Con `--run --as-of` se puede volver al corte de una ventana
anterior. El timer recupera una ejecución tras inactividad, pero una parada
superior a la ventana exige revisar los cortes omitidos.

La restricción única `(source_dataset, source_id)` conserva un registro por
oportunidad. PostgreSQL serializa API y worker con un bloqueo por conjunto.
El lote, su resultado y el avance de catálogo se guardan juntos. Una falla
del proveedor conserva las filas ya leídas y registra el error. Un reintento
incremental sin límite explícito retoma su ventana sin tocar el cursor de
catálogo. Una ejecución interrumpida se marca al volver a adquirir el bloqueo.
Un error de persistencia revierte el lote y registra el fallo si la base sigue
disponible.

## Contrato y alcance de la fuente

`GET /api/v1/opportunities` y `GET /api/v1/opportunities/{id}` publican:

| Campo | Origen |
| --- | --- |
| `status` | `estado_del_procedimiento`, el estado oficial en el catálogo. |
| `published_at` | `fecha_de_publicacion_del`, fecha de publicación inicial. |
| `last_updated_at` | `fecha_de_ultima_publicaci`, fecha de última publicación y campo usado por el incremental. |
| `reception_at` | `fecha_de_recepcion_de`, fecha asignada a la recepción de respuestas. Se devuelve `null` cuando falta o es ilegible. Se lee del registro original para cubrir oportunidades ya almacenadas. |
| `last_synced_at` | Hora en que se guardó o se reconfirmó la oportunidad, aunque su contenido no cambiara. |

La ventana incluye el inicio y excluye el final. Socrata declara las tres
fechas de origen como `calendar_date`, sin zona. La conversión actual interpreta
UTC para los valores sin offset. La zona de origen queda por confirmar. El
incremental detecta publicaciones tardías cuyo campo cae dentro de la ventana.
No existe garantía de detectar cambios que no actualicen ese campo o filas con
ese valor ausente. El estado y la recepción no garantizan que el portal siga
aceptando ofertas.

## Verificación reproducible

Ejecutar desde `apps/api` con el entorno virtual y las dependencias fijadas:

```powershell
python -m ruff check .
python -m mypy app
python -m pytest
$env:EAG_TEST_POSTGRES = '1'
python -m pytest tests/test_postgres_sync_integration.py
Remove-Item Env:EAG_TEST_POSTGRES
python -m app.secop.daily --as-of 2026-11-22T11:00:00Z
```

La integración de persistencia requiere la imagen local `postgres:17.6-bookworm`.
Crea una base desechable en loopback y simula SECOP. Cubre carga inicial
paginada con un proceso más antiguo que la ventana y una fecha de recepción
futura, actualización tardía, 429 parcial, reanudación independiente, repetición
idempotente y exclusión de ejecuciones concurrentes. Las pruebas de API usan
pertenencias sintéticas para comprobar roles, aislamiento y OpenAPI.

El smoke de red opt-in usa hasta cinco consultas públicas al catálogo por
ejecución, hasta cinco filas por consulta, timeout de 12 s y sin reintentos.
Proyecta los campos necesarios y conserva las filas solo en SQLite en memoria.
Emite estados y recuentos, sin IDs ni contenido de registros.

```powershell
python -m app.secop.smoke --run --as-of 2026-11-22T11:00:00Z
```

### Resultado del 22 de noviembre de 2026

La consulta de metadatos devolvió HTTP 200 y confirmó la semántica de los
campos de publicación, recepción y estado. La ventana estimada fue
`[2026-11-15T11:00:00Z, 2026-11-22T11:00:00Z)`.

El smoke terminó con salida 0 y cinco respuestas HTTP 200:

- La consulta acotada a cinco filas encontró cinco procesos con estado
  `Publicado`, publicación anterior al inicio de la ventana y recepción
  posterior al corte. La carga inicial por ID creó una fila de esa muestra.
- La selección dentro de la ventana devolvió tres candidatos. Sobre un
  candidato, el primer incremental creó una fila. El segundo devolvió una
  sin cambios y cero nuevas. Quedaron dos oportunidades únicas en memoria.
- Las dos filas expusieron estado y última sincronización. Una traía fecha
  de recepción y la otra quedó en `null`.

La muestra acredita esos resultados frente al catálogo público. No mide el
volumen o la cuota necesarios para una ventana completa, ni comprueba una
transición real de estado entre ejecuciones. La transición tardía se probó
con fixtures. El timer se entrega versionado y queda por activar en el
entorno autorizado después de integrar MVP-04.
