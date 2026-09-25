# Cliente SECOP: verificación con datos reales

> **Issue:** MVP-05 / #5
> **Fecha de la comprobación:** 2026-09-17
> **Conjunto consultado:** `p6dx-8zbt` (procesos de contratación)

Este documento registra lo que se comprobó ejecutando el cliente contra la API
pública real, y lo que **no** se comprobó. Las pruebas automáticas del módulo
son offline y no demuestran disponibilidad de SECOP II.

## Comandos ejecutados

```bash
cd apps/api
.venv/bin/python -m pytest          # 44 pruebas offline
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy app
```

Y una lectura de red acotada y explícita, con `page_size=10` y un máximo de 2
consultas, sin persistir nada.

## Resultado

| Comprobación | Resultado |
| --- | --- |
| API de procesos responde | Sí |
| Paginación por `$limit`/`$offset` | Sí |
| Filtro por campo confirmado (`estado_del_procedimiento`) | Sí |
| Identificador de origen presente | Sí, 10/10 registros |
| URL oficial extraída | Sí, 10/10 registros |
| Fecha de publicación extraída | Sí, 10/10 registros |

## Hallazgos corregidos durante la verificación

Estos tres defectos no eran visibles con datos sintéticos. Se encontraron al
contrastar con respuestas reales y quedaron cubiertos por pruebas.

### 1. `urlproceso` es un objeto, no una cadena

La fuente entrega `{"url": "https://community.secop.gov.co/..."}`, no el texto
de la URL. El primer intento leía el campo como cadena y producía
`official_url = None` en el 100 % de los registros. Se toleran ahora objeto
anidado, cadena directa y lista de objetos, porque el esquema ha cambiado
entre versiones.

### 2. Ordenar por fecha devuelve precisamente las filas sin fecha

Éste es el hallazgo de mayor impacto. Con `$order=fecha_de_publicacion_del DESC`,
Socrata devuelve primero los registros con ese campo nulo, que en este conjunto
son abundantes: una muestra de 40 filas ordenada así tenía **0 fechas no nulas**.

Los campos de fecha **sí existen y sí están poblados** —una consulta sin orden
devolvió 5 de 5 con fecha—, por lo que el problema era el orden, no el dato.
El orden por defecto es ahora `id_del_proceso DESC`, que es además estable: un
orden inestable puede repetir u omitir filas entre páginas de una misma
sincronización.

**Consecuencia para HU-07 (sincronización incremental):** no se puede usar
`fecha_de_publicacion_del` como criterio de ventana sin verificar antes cuántas
filas quedan fuera. Queda como punto a validar, no como decisión tomada.

### 3. Una fila descartada cortaba la paginación antes de tiempo

Un registro sin identificador se descarta (no hay sincronización idempotente
posible sin él), pero el avance de página se calculaba sobre los registros
normalizados. Si una fila se descartaba, la página parecía incompleta y la
iteración terminaba antes de agotar los resultados. El avance se calcula ahora
sobre las filas recibidas.

## Lo que sigue sin comprobarse

- **Relación entre `p6dx-8zbt` y `dmgg-8hin`.** El spike MVP-02 no la confirmó y
  este trabajo no la aborda. La carga manual de documentos sigue siendo el
  camino previsto para el expediente (issue MVP-07).
- **Volumen total y comportamiento bajo cuota real.** Solo se hicieron lecturas
  de muestra. No se probó un recorrido completo ni el límite de peticiones sin
  token.
- **Estabilidad del orden `id_del_proceso`.** Es estable dentro de una
  sincronización, pero no se verificó si el conjunto reordena registros entre
  ejecuciones separadas.
- **Fechas en la zona horaria correcta.** Los valores llegan sin desplazamiento
  horario explícito y se interpretan como UTC. Para Colombia (UTC-5) esto
  desplaza el día en los bordes; debe confirmarse con EAG qué zona aplica el
  conjunto antes de usar fechas en comparaciones.

## Continuación de MVP-05

La persistencia usa `natural_key` (`p6dx-8zbt:<id_del_proceso>`) como clave de
deduplicación. Una fila sin `id_del_proceso` se descarta aunque traiga
`referencia_del_proceso`: ambos campos no son intercambiables. El cursor de
reanudación avanza por filas crudas, no por registros normalizados, y una
página llena de filas descartadas no detiene el recorrido. Estas reglas se
probaron offline el 2026-09-25; no constituyen una nueva prueba de red.
