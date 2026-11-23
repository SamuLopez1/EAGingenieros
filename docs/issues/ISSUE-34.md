# #34 · Lista corta de oportunidades

En el catálogo o el detalle, pulsa **Guardar en lista corta**. Con dos o tres
oportunidades seleccionadas, pulsa **Comparar lista corta**. Puedes quitar fichas,
abrirlas desde la tabla y volver al catálogo con sus filtros. La lista es privada
por usuario y organización y se conserva al recargar o iniciar sesión de nuevo.

La tabla separa el cierre sincronizado del plazo documentado y el presupuesto
publicado. Abre las brechas para ver los motivos y las citas. Personal resume
cobertura, dedicación faltante y disponibilidad por confirmar. Margen muestra
cada escenario vigente en su moneda y marca importes, fuentes o revisión
pendientes. Los resultados desactualizados se señalan para actualizar la ficha
y conservan su valor histórico allí.

El API privado publica `GET/PUT /api/v1/opportunity-shortlist` y
`GET /api/v1/opportunity-shortlist/comparison`. La escritura guarda el orden y
usa la revisión de la lista para detectar cambios desde otra sesión. La consulta
de comparación reutiliza las reglas y los resultados de #11, #23 y #24.

## Verificación

Desde `apps/api`, aplica `python -m alembic upgrade head` y ejecuta
`python -m pytest tests/test_shortlist.py`. Con PostgreSQL real desechable usa
`EAG_TEST_POSTGRES=1 python -m pytest tests/test_postgres_sync_integration.py -k shortlist`.

Desde la raíz se puede probar el recorrido con Chrome, Vite, API, PostgreSQL y
worker reales e identidad, antivirus y documentos sintéticos.

```text
python scripts/mvp06_preview.py --dossier --extraction --comparison --staffing --margin --shortlist --browser-cli RUTA_A_PLAYWRIGHT_CLI
```

El PR se prepara sobre #24, que ya contiene #11 y #23 en su cadena de dependencias.
