# Spike SECOP II: API y disponibilidad de documentos

> **Issue:** MVP-02 / #2
> **Estado:** borrador técnico; las secciones de red se completan únicamente
> después de ejecutar el smoke test real. Las pruebas offline no prueban la
> disponibilidad de SECOP II.

## Propósito y alcance

El spike comprueba de forma acotada si las fuentes públicas oficiales candidatas
permiten consultar una muestra de procesos y observar si el dataset de archivos
ofrece referencias que puedan relacionarse y descargarse de forma segura.

Fuentes consultadas exclusivamente por el script:

- Procesos SECOP II: [`p6dx-8zbt`](https://dev.socrata.com/foundry/www.datos.gov.co/p6dx-8zbt).
- Archivos de descarga desde 2025: [`dmgg-8hin`](https://dev.socrata.com/foundry/www.datos.gov.co/dmgg-8hin).

No implementa frontend, base de datos productiva, OCR, IA, autenticación ni
sincronización masiva. No registra oportunidades manualmente. No envía
documentos a servicios externos ni persiste archivos descargados.

## Ejecución reproducible

Requisitos: Python 3.11+ y conectividad explícitamente autorizada para el smoke
test. No hay dependencias de terceros.

```powershell
# Pruebas offline: no hay red ni secretos.
python -m unittest discover -s tests -p "test_*.py"

# Smoke test de red, limitado a cinco filas por dataset y dos filas por página.
python scripts/secop_spike.py --process-limit 5 --document-limit 5 --page-size 2

# Solo si la muestra descubre URLs y se quiere probar una lectura en memoria.
python scripts/secop_spike.py --process-limit 5 --document-limit 5 --page-size 2 --download-documents
```

El token Socrata, si hiciera falta, se toma exclusivamente de
`SOCRATA_APP_TOKEN`. No se imprime, no se añade a URLs y no se guarda. Los
metadatos mínimos se escriben en `output/secop-spike/`, ruta ya ignorada por
Git. La lectura de documentos sigue redirecciones solo HTTPS y solo hacia hosts
permitidos con `--allow-download-host`; de forma predeterminada solo permite
`www.datos.gov.co`. El límite de 1 MiB es una protección del spike, no el límite
de producto propuesto en el contexto.

## Método de comprobación

1. Descargar metadatos de cada dataset por la API Socrata oficial y registrar
   propietario, atribución, campos y tipos realmente devueltos.
2. Consultar una muestra paginada de `p6dx-8zbt`; los filtros `campo=valor`
   solo se construyen tras validar que el campo existe en su esquema.
3. Exportar únicamente los campos mínimos reconocidos de procesos a JSON y CSV
   en `output/`; no se versionan los resultados.
4. Consultar una muestra paginada de `dmgg-8hin`; comparar nombres de campos
   compartidos y coincidencias exactas de valores dentro de ambas muestras. Si
   ambos esquemas exponen los campos candidatos, probar de forma separada hasta
   tres valores de `referencia_del_proceso` e `id_del_proceso` contra el campo
   `proceso` del dataset de archivos, y repetir la comprobación en sentido
   inverso desde la muestra de documentos. Esta prueba no declara equivalencia
   ni cobertura universal.
5. Si hay URLs en la muestra y se activa explícitamente la descarga, leer como
   máximo dos respuestas en memoria, con timeout, validación de host/esquema,
   redirecciones manuales y límite de bytes. El resultado guarda host, tamaño,
   tipo de contenido y hash; no guarda la URL ni el archivo.

Una coincidencia de campo o valor en una muestra no demuestra una relación
formal, la cobertura de pliegos ni que un expediente esté completo. La ausencia
de URL en la muestra tampoco demuestra ausencia en todo el dataset.

## Pruebas offline ejecutadas

**Fecha:** 2026-09-03.
**Comando:** `python -m unittest discover -s tests -p "test_*.py"`
**Resultado:** 11 pruebas ejecutadas, todas exitosas. No realizaron red.

Cubren respuestas sintéticas para:

- filtros sobre campos existentes y rechazo de campos inválidos;
- paginación, respuesta vacía y deduplicación;
- timeout, HTTP 429 y HTTP 503;
- URL no permitida y redirección hacia host no permitido;
- límite de tamaño de descarga.

Estas pruebas no hacen llamadas a SECOP II ni se presentan como integración.

## Resultado de red real

**Fecha de comprobación:** 2026-09-03, entre 14:19 y 14:22 UTC.
**Token:** el script solo lo lee de `SOCRATA_APP_TOKEN`; no imprimió ni guardó
tokens. Las consultas de esta comprobación no requirieron registrar ningún token.

Se hicieron estas llamadas de red, con `timeout=15` segundos:

```text
# Muestra principal, sin filtros: cinco filas por dataset; páginas de dos filas.
python scripts/secop_spike.py --process-limit 5 --document-limit 5 --page-size 2 --relationship-limit 3 --download-documents --download-limit 2 --allow-download-host community.secop.gov.co --timeout 15

# Filtro real: tres procesos y una fila de documentos; páginas de una fila.
python scripts/secop_spike.py --filter "modalidad_de_contratacion=Contratación directa" --process-limit 3 --document-limit 1 --page-size 1 --relationship-limit 1 --timeout 15
```

Las primeras lecturas de documentos se hicieron antes sin permitir el host
observado y fueron rechazadas por la política de host. La ejecución final lo
permitió explícitamente, porque la URL provino del campo del dataset oficial.

| Validación | Resultado real | Evidencia y límite observable |
| --- | --- | --- |
| API de procesos `p6dx-8zbt` | Accesible | La API Socrata devolvió metadatos y cinco procesos sin token documentado. |
| Propietario y esquema de procesos | Comprobado | Propietario mostrado: `Datos Abiertos CCE` (`mb3d-8f4b`); atribución: Agencia Nacional de Contratación Pública – Colombia Compra Eficiente, Bogotá D.C. El esquema devolvió 59 campos. |
| Consulta paginada y filtro seguro | Comprobada | La muestra sin filtros usó páginas de 2 y 5 resultados. El filtro real `modalidad_de_contratacion=Contratación directa`, campo presente en el esquema, devolvió 3 resultados. |
| API de archivos `dmgg-8hin` | Accesible | La API Socrata devolvió metadatos y cinco registros sin token documentado. |
| Propietario y esquema de archivos | Comprobado | Mismo propietario y atribución. El esquema devolvió 11 campos, incluido `url_descarga_documento`. |
| Relación muestra procesos-documentos | No confirmada | Los campos con el mismo nombre fueron `entidad` y `nit_entidad`, sin coincidencias de valor en la muestra. Las 12 consultas dirigidas entre `referencia_del_proceso`/`id_del_proceso` y `proceso`, en ambos sentidos, no devolvieron filas relacionadas. No prueba que la relación no exista fuera de esta muestra. |
| URLs de documentos | Comprobadas en la muestra | Se observaron 5 valores en el campo URL; su host era `community.secop.gov.co`. Esto no demuestra que sean pliegos de procesos abiertos. |
| Descarga acotada en memoria | Parcialmente comprobada | Una respuesta fue `application/pdf` y leyó 767 421 bytes. La segunda fue rechazada por el límite de 1 MiB. Ningún documento se escribió en disco ni se añadió a Git. |

### Esquema confirmado

De `p6dx-8zbt` se comprobaron, entre otros, `id_del_proceso`,
`referencia_del_proceso`, `nombre_del_procedimiento`,
`fecha_de_publicacion_del`, `fecha_de_ultima_publicaci`,
`estado_del_procedimiento`, `modalidad_de_contratacion` y `urlproceso`.

De `dmgg-8hin` se comprobaron `n_mero_de_contrato`, `id_documento`, `proceso`,
`nombre_archivo`, `tamanno_archivo`, `extensi_n`, `descripci_n`, `fecha_carga`,
`entidad`, `nit_entidad` y `url_descarga_documento`.

Los metadatos mínimos exportados de la muestra de procesos se escribieron en
`output/secop-spike-network-final/`, ruta ignorada por Git. No se incluyeron en
el commit, y tampoco se guardaron las URL ni los bytes de los documentos.

## Limitaciones y riesgos conocidos antes de red

- `dmgg-8hin` es un candidato de archivos desde 2025; no hay evidencia todavía
  de que contenga todos los pliegos de oportunidades abiertas ni de que cada
  archivo se relacione con `p6dx-8zbt`. Su esquema describe el campo `proceso`
  como asociado al contrato del documento y contiene `n_mero_de_contrato`; por
  ello no debe tratarse como inventario confirmado de pliegos abiertos.
- Campos, propietario, actualizaciones, disponibilidad y semántica se deben
  tomar de la respuesta real de la API, no de suposiciones de diseño.
- El spike no infiere la completitud del expediente a partir de una descarga
  encontrada; una oportunidad puede requerir documentos complementarios.
- Un 429, 5xx, timeout o URL/redirección rechazada se registra como bloqueo o
  límite observable, no como ausencia de datos.
- Las descargas se limitan y no se conservan; validar formatos, antivirus,
  almacenamiento, OCR y retención corresponde a issues posteriores.

## Recomendación

**Recomendación: ajustar alcance y depender de carga manual de documentos
complementarios.** Se puede continuar con el diseño técnico de consulta de
metadatos de oportunidades desde `p6dx-8zbt`, pues la API, paginación y filtro
se comprobaron en una muestra real. Sin embargo, no se debe diseñar todavía una
obtención automática de expediente completo desde `dmgg-8hin`: la muestra no
confirmó relación con los procesos probados, su esquema apunta a documentos de
contratos y una descarga superó el límite conservador del spike.

Antes de una integración productiva, validar con Colombia Compra/EAG un conjunto
de oportunidades abiertas y sus pliegos autorizados, su clave de relación y los
hosts/tamaños aceptables. Hasta entonces, conservar la carga manual controlada
de documentos complementarios prevista en el caso de uso; esto no supone que
los documentos estén ausentes en SECOP II.
