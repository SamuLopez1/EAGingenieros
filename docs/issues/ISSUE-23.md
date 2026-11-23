# #23 · Encaje y personal

En la ficha, marca las versiones en revisión, completa la extracción y pulsa
**Comparar con EAG**. La sección «Encaje y personal» usa la matriz vigente y el perfil
de la organización. Muestra sus versiones y enlaza el pliego y las evidencias de EAG.
Las brechas habilitantes siguen visibles junto al encaje comercial.

## Reglas

- Una línea identificada en las citas del objeto o los requisitos se muestra con
  respaldo cuando el perfil tiene experiencia o capacidad verificada y vigente.
  Si falta una fecha de referencia para comprobar una vigencia registrada, queda pendiente.
- La detección conserva la cita. Por ejemplo:
  `Habilitante: Cargo: Residente; dedicación: 60%; periodo: 2026-12-01 a 2026-12-20.`
  El administrador puede completar o corregir cualquier requisito de la matriz.
  Las fechas o cantidades ambiguas y las adendas contradictorias quedan pendientes.
- Los periodos se dividen al cambiar la demanda o la disponibilidad. Las fechas de
  inicio y fin son inclusivas. Se suman las exigencias simultáneas sin contar dos
  veces una cita equivalente. La disponibilidad del perfil se interpreta como el
  total registrado por cargo e intervalo. Los registros superpuestos no se suman.
  Si sus valores difieren, se muestra el menor valor registrado y se pide conciliación.
- Si hay una brecha frente a capacidad verificada, se indica la dedicación y las
  fechas para evaluar contratación o reasignación. Si falta disponibilidad, se
  pide confirmación. Un 0 % verificado marca falta de cobertura. Un dato ausente
  queda pendiente. Talento Humano conserva la decisión.

## Permisos y correcciones

El analista consulta datos agregados de su organización. El administrador puede
corregir cargo, dedicación y periodo con justificación. El historial registra el
usuario, la fecha, la revisión de comparación y los valores anteriores y nuevos.
Las correcciones quedan ligadas a la huella de las entradas. Un cambio del pliego,
sus adendas o el perfil exige actualizar la comparación. La corrección del plan
queda registrada por separado de las decisiones de cumplimiento de la matriz.

El API privado usa `GET /api/v1/opportunities/{opportunity_id}/staffing` y el
subrecurso administrativo `POST /corrections`.

## Verificación

Desde `apps/api` ejecuta `python -m alembic upgrade head` y
`python -m pytest tests/test_staffing.py`. Para comprobar migración y acceso SQL
en PostgreSQL local desechable, ejecuta
`EAG_TEST_POSTGRES=1 python -m pytest tests/test_postgres_sync_integration.py -k staffing`.
La prueba PostgreSQL usa Docker y la imagen local `postgres:17.6-bookworm`.
Desde la raíz, el smoke en Chrome usa API, Vite, PostgreSQL y worker reales,
con identidad, antivirus y datos sintéticos.

```text
python scripts/mvp06_preview.py --dossier --extraction --comparison --staffing --browser-cli RUTA_A_PLAYWRIGHT_CLI
```

Las fixtures son sintéticas. Queda pendiente validar con EAG que el perfil registra
totales consolidados por cargo y que la política de acceso refleja su operación.
