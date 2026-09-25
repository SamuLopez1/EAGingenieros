# Persistencia y sincronización de oportunidades

> **Issue:** MVP-05 / #5
> **Fecha:** 2026-09-17

## Qué se construyó

La persistencia de oportunidades y el registro de cada ejecución de
sincronización. La pieza central es la **idempotencia**: sincronizar dos veces
la misma fila oficial actualiza el registro existente en lugar de crear un
duplicado.

### Tablas

| Tabla | Para qué |
| --- | --- |
| `opportunities` | Catálogo de oportunidades oficiales con su trazabilidad de origen |
| `sync_runs` | Historial de ejecuciones, para que un fallo parcial quede visible |
| `sync_cursors` | Posición por conjunto de datos, para reanudar sin reiniciar |

La migración propia de MVP-05 crea solo estas tres tablas. El PR #21 también
contiene cambios de documentos, análisis, perfil y UI ajenos a esta issue; esa
mezcla debe resolverse en revisión sin sobrescribir trabajo existente.

### Decisiones de modelado

- **La identidad es `(source_dataset, source_id)`**, no solo el identificador.
  El mismo código en dos conjuntos distintos son dos oportunidades distintas.
- **`first_seen_at` y `last_synced_at` son campos diferentes.** El primero
  registra cuándo apareció la oportunidad y no se reescribe nunca; el segundo,
  cuándo se confirmó por última vez contra la fuente. Confundirlos impediría
  saber si un registro sigue publicado.
- **`raw_payload` conserva la carga original.** Si la normalización se corrige
  más adelante —como ocurrió con `urlproceso`— los registros ya guardados se
  pueden renormalizar sin volver a consultar SECOP.
- **Lo desconocido es `NULL`, nunca cero ni cadena vacía.** En este dominio
  "no sé" y "cero" son distintos, y confundirlos produce comparaciones
  incorrectas cuando se evalúen requisitos.

## Verificación ejecutada

### Pruebas offline

```bash
cd apps/api
.venv/bin/python -m pytest      # 61 pruebas
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy app
```

### Idempotencia contra Postgres real

Se levantó un PostgreSQL 17 desechable, se aplicó la migración y se ejecutaron
tres sincronizaciones sobre los mismos datos, más una con un cambio real:

| Ejecución | Resultado |
| --- | --- |
| 1.ª con 3 registros | `creados=3`, offset 3 |
| 2.ª idéntica | `creados=0`, `sin_cambios=3` |
| 3.ª con un cambio | `actualizados=1`, `creados=0` |

**Total en base de datos: 3 filas para 3 oportunidades.** Sin duplicación. El
cursor quedó en 3 y el cambio de estado se aplicó.

### Sincronización real de extremo a extremo

Con el cliente consultando la API pública de SECOP II:

| Ejecución | Resultado |
| --- | --- |
| 1.ª | `vistos=19`, `creados=19`, 1 petición |
| 2.ª idéntica | `creados=0`, `sin_cambios=19` |

Las 19 oportunidades quedaron guardadas con fecha y URL oficial. **El flujo
SECOP → Postgres funciona y es idempotente en la práctica, no solo en pruebas
con datos sintéticos.**

## Defectos corregidos durante la construcción

Encontrados por las pruebas, no en revisión posterior:

1. **Un fallo a mitad de sincronización descartaba todo lo leído.** El cliente
   iteraba páginas y el resultado se materializaba al final; si fallaba en la
   página 3, se perdían las páginas 1 y 2. Ahora lo leído se acumula y se
   persiste antes de registrar el fallo. La ejecución **sigue siendo un fallo**
   —guardar lo parcial no la convierte en exitosa— pero el trabajo no se pierde
   y la siguiente ejecución lo reconoce como existente.

2. **Ordenación invertida de las filas sin fecha.** La clave de ordenación
   incluía el indicador "tiene fecha" dentro de una tupla invertida, lo que
   colocaba las filas sin fecha **al principio**. Mostrarlas primero da a
   entender que son lo más reciente. Ahora se ordenan en dos grupos explícitos.

## Lo que sigue sin comprobarse

- **La relación entre `p6dx-8zbt` y `dmgg-8hin`.** Sin confirmar desde MVP-02.
  No se ha construido nada que dependa de ella.
- **Zona horaria de las fechas.** Llegan sin desplazamiento explícito y se
  interpretan como UTC. Para Colombia (UTC-5) esto puede desplazar el día en
  los bordes. Debe confirmarse antes de usar fechas en comparaciones.
- **Ventana incremental.** No se ha verificado cuántos procesos quedarían fuera
  al filtrar por fecha, por lo que la sincronización diaria de 7 días que
  propone el contexto sigue sin validar.
- **Comportamiento bajo cuota real sin token.** Solo se hicieron lecturas de
  muestra con un tope de peticiones.

## Cómo ejecutarlo

La URL de la base de datos se toma de `EAG_DATABASE_URL` y nunca se escribe en
`alembic.ini`, que sí se versiona. Sin esa variable la aplicación funciona en
modo memoria, lo que permite desarrollar sin base de datos; en producción su
ausencia debe impedir el arranque en lugar de degradar en silencio.

```bash
export EAG_DATABASE_URL="postgresql://usuario:clave@host:5432/basedatos"
cd apps/api
.venv/bin/python -m alembic upgrade head
```

## Siguiente paso

## Continuación acotada de MVP-05 (2026-09-25)

**Dependencias.** La issue #2 está cerrada y su spike comprobó con llamadas
reales una muestra de `p6dx-8zbt`, su esquema, paginación y un filtro. No
confirmó la relación con `dmgg-8hin`, la cobertura de pliegos ni la zona
horaria de las fechas. MVP-04 (#4) sigue abierta y el PR #19 no está fusionado.
La autorización de este PR usa su propia dependencia de identidad; la
integración con el proveedor y la matriz definitivos de MVP-04 está pendiente.

**Correcciones.** `id_del_proceso` es obligatorio para la clave natural; una
`referencia_del_proceso` aislada no lo sustituye. Una página llena de filas
descartadas ya no detiene la paginación. El cursor cuenta posiciones de la
respuesta original, incluidas filas descartadas, y en un fallo parcial guarda
el avance y los contadores tras persistir lo leído. La lectura del cursor se
confirma antes de consultar la red, evitando retener una transacción abierta.
Las rutas de oportunidades requieren identidad y la sincronización manual
requiere rol administrador. Las pruebas de autorización usan identidades
sintéticas; no son un login real ni validan la integración con #4.
Una consulta del historial ya no crea una ejecución `running`, y el servicio
se construye después del control de rol para que un 403 no escriba en la base.
Cada petición cierra su sesión SQL y cliente HTTP. CORS admite la cabecera
`Authorization` únicamente desde los orígenes configurados.

**Comprobaciones offline en el worktree aislado:**

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest -q tests/test_secop_client.py tests/test_sync_repository.py tests/test_api_opportunities.py tests/test_health.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
```

Resultado: 87 pruebas específicas correctas; Ruff y mypy correctos. Se
instalaron en un `.venv` ignorado las versiones de `requirements.lock` para
ejecutarlas. El suite completo falló en dos pruebas de extracción ajenas a
MVP-05 porque el ejecutable Tesseract no está instalado; sus demás pruebas
terminaron sin fallos. No se repitió la prueba de red contra SECOP ni la
prueba PostgreSQL histórica de este PR durante esta continuación.

**Pendiente para aceptación.** Confirmar con EAG el campo y la zona horaria que
permiten detectar cambios tardíos, validar la ventana incremental de siete
días y el horario diario antes de activarlos, probar cuota real con una
consulta acotada, integrar autorización con MVP-04 y revisar el exceso de
alcance del PR #21. CI verde y pruebas con mocks no cierran esas decisiones.
