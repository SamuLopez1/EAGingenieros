# Caso de uso mínimo: análisis de una oportunidad de SECOP II

> **Estado:** propuesta del equipo para la issue #1. No constituye una
> validación empresarial, una aprobación de EAG ni evidencia de resultados de
> mejora.

## Propósito y límites

El caso mínimo permite que un analista de licitaciones convierta una oportunidad
procedente de SECOP II en un borrador revisable. El borrador contrasta los
requisitos identificados en los documentos de la oportunidad con el perfil y
las evidencias empresariales autorizadas de EAG.

El alcance termina cuando el borrador está listo para revisión humana. No cubre
la postulación de una oferta, la decisión empresarial, la generación del PDF
final ni el envío de correo. Tampoco permite registrar oportunidades de forma
manual: la oportunidad procede de SECOP II. La carga manual se limita a
documentos complementarios de esa oportunidad cuando SECOP II no permita
obtenerlos todos.

Esta propuesta sigue las restricciones de [CONTEXTO.md](CONTEXTO.md) y el
alcance de [MVP-01](issues/MVP-01.md).

## Historia del analista

Como analista de licitaciones de EAG, quiero revisar una oportunidad de SECOP
II con sus documentos disponibles y los documentos complementarios autorizados,
para obtener un borrador trazable de requisitos y su contraste con evidencias
de EAG, identificar faltantes y remitirlo a revisión humana antes de cualquier
decisión empresarial.

## Entradas

| Entrada | Origen | Uso en el caso mínimo |
| --- | --- | --- |
| Identificador y metadatos de la oportunidad | SECOP II | Identificar la oportunidad que se analiza; no se crea manualmente. |
| Documentos de la oportunidad | SECOP II | Extraer requisitos, condiciones, fechas, cantidades e indicadores. |
| Documentos complementarios | Carga manual autorizada, asociados a una oportunidad de SECOP II | Completar el expediente cuando los documentos no estén disponibles desde SECOP II. |
| Perfil empresarial de EAG | Registros persistentes autorizados | Contrastar experiencia, personal, capacidades, información financiera y documentos soporte. |
| Evidencia empresarial | Documentos y registros autorizados de EAG | Sustentar cada conclusión con documento, localizador, fragmento y versión. |

Los formatos previstos son PDF, DOCX y XLSX; un PDF escaneado puede requerir
OCR básico. Una muestra real autorizada y los documentos empresariales se
mantienen fuera de Git.

## Flujo propuesto

1. El analista consulta y selecciona una oportunidad procedente de SECOP II.
2. El sistema asocia los documentos disponibles desde SECOP II. El analista
   puede añadir únicamente documentos complementarios de esa misma oportunidad.
3. Se extraen requisitos y se conservan sus fuentes. Fechas, cantidades e
   indicadores se evalúan con reglas deterministas; la interpretación
   semántica queda señalada para revisión cuando corresponda.
4. Cada requisito se contrasta con el perfil y las evidencias autorizadas de
   EAG.
5. Para cada resultado se registra estado, explicación, documento, localizador
   (página, sección o celda), fragmento y versión de la evidencia.
6. El analista revisa, corrige o marca pendientes. La ausencia, ambigüedad o
   incompatibilidad de evidencia no se convierte en una afirmación de
   cumplimiento.
7. Se genera un borrador versionado, revisable por las personas autorizadas.
   No equivale a aprobación empresarial ni habilita un envío de correo.

## Salidas

- Matriz de requisitos con uno de estos estados:
  `cumple`, `cumple_parcialmente`, `no_cumple` o `revision_manual`.
- Evidencia trazable por requisito: documento, localizador, fragmento y versión.
- Lista de documentos, datos o decisiones faltantes.
- Observaciones y correcciones del analista.
- Borrador versionado listo para revisión humana.

## Reglas de interpretación propuestas

| Estado | Regla propuesta |
| --- | --- |
| `cumple` | Requiere evidencia suficiente, vigente cuando el requisito lo exija y compatible con **todas** las condiciones comprobables del requisito. |
| `cumple_parcialmente` | Hay evidencia suficiente de que se satisface una parte identificable del requisito, pero falta satisfacer o comprobar otra condición. La condición pendiente debe quedar explícita. |
| `no_cumple` | Requiere evidencia suficiente de incumplimiento de al menos una condición obligatoria; no se infiere solo por ausencia de documentos. |
| `revision_manual` | Se usa cuando el perfil o la evidencia está incompleta, es ambigua, contradictoria, ilegible o requiere interpretación humana. |

Estas reglas son una propuesta del equipo. La clasificación final y los umbrales
de cada tipo de requisito requieren validación de EAG.

## Escenarios sintéticos

Los tres escenarios siguientes son ficticios. No describen una oportunidad, un
perfil ni documentos reales de EAG.

| Escenario | Requisito y evidencia sintéticos | Resultado esperado | Razón verificable |
| --- | --- | --- | --- |
| Éxito | El requisito ficticio exige tres certificaciones identificadas (A, B y C) y vigentes. El perfil ficticio aporta tres certificados compatibles, con fecha y localizador verificables. | `cumple` | Existe evidencia suficiente y compatible para cada condición A, B y C. |
| Perfil incompleto | El requisito ficticio exige un indicador financiero de un período definido. El perfil ficticio no contiene el estado financiero de ese período. | `revision_manual` | Falta evidencia; la ausencia no prueba incumplimiento. |
| Incumplimiento | El requisito ficticio exige que el responsable técnico tenga una certificación obligatoria vigente. La evidencia ficticia identifica al responsable y demuestra que su certificación está vencida en la fecha aplicable. | `no_cumple` | Existe evidencia suficiente de incumplimiento de una condición obligatoria. |

## Protocolo propuesto de medición

El protocolo se aplicará a las mismas oportunidades, los mismos documentos
disponibles y el mismo resultado esperado versionado. No se compararán casos
distintos ni se tratará una salida propuesta por la aplicación como resultado
correcto sin revisión humana.

Antes de cada corrida, un revisor humano designado debe fijar el paquete de
evaluación: identificador de oportunidad, versión de cada documento, requisitos
esperados, estado esperado por requisito y evidencia esperada cuando exista.
Hasta que EAG designe a dicho revisor y autorice una muestra real, este protocolo
permanece pendiente de validación.

| Medida | Definición propuesta | Registro |
| --- | --- | --- |
| Tiempo transcurrido total | Tiempo de reloj desde que el paquete de evaluación queda disponible hasta que se entrega el borrador revisable. Incluye esperas y procesamiento automático. | Marca de inicio y fin. |
| Tiempo de procesamiento | Tiempo de reloj de las tareas de obtención, carga de documentos complementarios, extracción y comparación de la aplicación. | Eventos de inicio, fin y resultado de cada tarea. |
| Tiempo de revisión | Tiempo de trabajo humano dedicado a verificar requisitos, estados y evidencias del borrador. Excluye pausas sin actividad. | Registro de inicio, fin y participante. |
| Tiempo de corrección | Tiempo de trabajo humano dedicado a cambiar estados, evidencias u observaciones tras la revisión. Excluye pausas sin actividad. | Registro de inicio, fin, participante y tipo de cambio. |
| Trabajo humano total | Suma del tiempo humano de preparación permitida, revisión y corrección. No incluye espera ni procesamiento automático. | Suma de los registros humanos. |
| Errores frente al resultado esperado | Cantidad y tipo de diferencias entre el borrador y el paquete de evaluación: requisito omitido, estado incorrecto, evidencia incorrecta o falta de trazabilidad. | Lista de discrepancias revisada por humano. |

La línea base manual debe usar el mismo paquete y el mismo resultado esperado.
Se registrarán por separado su tiempo transcurrido y su trabajo humano. Cualquier
porcentaje de reducción se calculará solo después de contar con datos revisados;
el 60 % no es un compromiso ni un resultado confirmado.

## Criterios de aceptación de este documento

- El documento describe una oportunidad originada en SECOP II y limita la carga
  manual a documentos complementarios asociados a ella.
- Contiene entradas, flujo, salidas, exclusiones y una historia del analista.
- Incluye escenarios sintéticos de éxito, perfil incompleto e incumplimiento,
  con reglas explícitas para `cumple`, `revision_manual` y `no_cumple`.
- Distingue las reglas propuestas por el equipo de las decisiones que requiere
  validar EAG.
- Define un protocolo que compara las mismas oportunidades, documentos y
  resultados esperados; separa procesamiento, revisión, corrección, tiempo
  transcurrido y trabajo humano.
- No presenta porcentajes de mejora, aprobación empresarial ni resultados de
  una prueba como hechos confirmados.
- Incluye pendientes con responsable propuesto, siguiente acción y estado.

## Comportamientos que la aplicación deberá demostrar posteriormente

Los siguientes son comportamientos futuros de la aplicación; no son evidencia
de que ya estén implementados ni criterios de aprobación de este documento.

- Solo permite analizar oportunidades identificadas desde SECOP II y asociarles
  documentos complementarios autorizados.
- Conserva la trazabilidad y la versión de evidencia para cada requisito.
- No marca `cumple` sin evidencia suficiente y compatible con todas las
  condiciones aplicables.
- No marca `no_cumple` solo porque falte información; ante perfil incompleto
  usa `revision_manual`.
- Permite revisión y corrección humana antes del informe final; cambios
  posteriores invalidan una aprobación previa.
- Registra los eventos necesarios para medir procesamiento, revisión,
  corrección, tiempo transcurrido, trabajo humano y discrepancias frente al
  resultado esperado.

## Pendientes de validación con EAG

| Pregunta | Responsable propuesto por rol | Siguiente acción | Estado |
| --- | --- | --- | --- |
| ¿Qué oportunidad real autorizada y qué documentos se usarán para validar el caso? | Área Comercial y Contratación, con autorización de Gerencia | Seleccionar una muestra autorizada y custodiarla fuera de Git. | Pendiente de EAG |
| ¿Qué campos y documentos del perfil de EAG son obligatorios en la primera muestra? | Áreas técnica, financiera, talento humano y documental | Entregar un inventario mínimo de campos, fuentes y vigencias. | Pendiente de EAG |
| ¿Quién define el resultado esperado y resuelve discrepancias de la medición? | Gerencia, con apoyo de Comercial y Contratación | Designar revisor humano y reglas de desempate. | Pendiente de EAG |
| ¿Qué condiciones determinan `cumple_parcialmente` para experiencia, personal, finanzas y documentación? | Áreas aportantes, coordinadas por Comercial y Contratación | Acordar una tabla de clasificación por tipo de requisito. | Pendiente de EAG |
| ¿Quién puede revisar y aprobar el borrador antes del informe final? | Gerencia | Designar roles autorizados y sustituciones permitidas. | Pendiente de EAG |
| ¿Cuál es el inicio y fin operativo de cada medición y cómo se registra el trabajo humano? | Comercial y Contratación | Validar el protocolo y un formato de registro de tiempos. | Pendiente de EAG |
| ¿Qué reglas de acceso, conservación y eliminación aplican a la muestra y sus respaldos? | Gerencia y área documental | Definir responsable, origen del plazo y tratamiento de respaldos antes de producción. | Pendiente de EAG |

## Exclusiones explícitas

- Registro manual de oportunidades.
- Postulación o envío automático de propuestas.
- Decisión autónoma de viabilidad, aprobación empresarial o adjudicación.
- Afirmar integración real con SECOP II, resultados de prueba o mejoras de
  tiempo antes de ejecutarlas y revisarlas.
- Incorporar al repositorio expedientes reales, documentos internos, datos
  personales o secretos.
