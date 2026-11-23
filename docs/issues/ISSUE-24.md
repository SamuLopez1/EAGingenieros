# #24 · Utilidad y margen por escenarios

En la ficha abre «Escenarios de utilidad y margen». Registra el ingreso estimado y
los costos directos, indirectos, de personal interno, contratación adicional y
contingencia. Cada escenario usa una sola moneda, indicada en el formulario. Registra
el costo de personal una vez en su rubro y exclúyelo de los importes directos e
indirectos. Las brechas del plan de personal dan contexto para presupuestar y sus
costos se ingresan expresamente.

## Cálculo y fuentes

- Se usa decimal para los importes. La utilidad es ingreso menos costos totales.
  El margen porcentual es utilidad dividida por ingreso y multiplicada por 100.
  Se presenta con dos decimales y redondeo a la mitad hacia afuera de cero.
- Todos los rubros son explícitos. Cero indica que el rubro no aplica o no tiene
  importe. Un campo vacío mantiene pendiente el cálculo. Con ingreso cero y
  costos completos se muestra la utilidad y el margen queda indefinido.
- El importe publicado se toma del campo `precio_base` de SECOP II. El diccionario
  lo define como precio base del proceso. Para usarlo como ingreso hay que elegir
  ese supuesto, comprobar la moneda con el pliego y registrar una justificación.
  El valor visto queda fijado en la versión guardada.
  [Diccionario oficial de SECOP II](https://www.datos.gov.co/api/views/8scu-28fr/files/ffa9c16f-d9df-4e8d-b826-4eb5520953c7?download=true)
- Si hay montos completos con fuentes por confirmar, se muestra la estimación y
  se bloquea su revisión. Los escenarios de monedas distintas se presentan por
  separado. Finanzas debe validar impuestos, retenciones y demás rubros aplicables
  antes de adoptar este resultado como modelo contable.

## Permisos e historial

Los miembros de la organización pueden consultar y editar sus escenarios. El
administrador registra la revisión humana con una nota. Cada edición conserva
actor, fecha, importes, fuentes, resultado, versión de cálculo, documentos, perfil,
comparación y revisión de personal. Si cambian las entradas de origen, el escenario
queda desactualizado. Abre su edición y guarda una nueva versión para revalidarlo.

El API privado ofrece `GET/POST /api/v1/opportunities/{opportunity_id}/margin` y
`PUT /margin/{scenario_id}`, junto al historial `/versions` y la revisión
`POST /review` de ese escenario.

## Verificación

Desde `apps/api`, aplica `python -m alembic upgrade head` y ejecuta
`python -m pytest tests/test_margin.py`. La prueba de permisos y migración con
PostgreSQL local desechable se ejecuta con
`EAG_TEST_POSTGRES=1 python -m pytest tests/test_postgres_sync_integration.py -k margin`.
El smoke con Chrome usa Vite, FastAPI, PostgreSQL y el worker reales. Identidad,
antivirus y datos son sintéticos.

```text
python scripts/mvp06_preview.py --dossier --extraction --comparison --staffing --margin --browser-cli RUTA_A_PLAYWRIGHT_CLI
```

La validación de permisos operativos y reglas contables sigue pendiente con Finanzas.
