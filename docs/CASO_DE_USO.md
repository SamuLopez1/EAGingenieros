# Caso de uso mínimo: análisis de una oportunidad de SECOP II

> **Estado:** propuesta del equipo para la issue #1. No constituye una
> validación empresarial, una aprobación de EAG ni evidencia de resultados de
> mejora.

## Propósito y límites

El caso mínimo permite que un analista de licitaciones convierta una oportunidad
procedente de SECOP II en un borrador revisable. El borrador contrasta los
requisitos identificados en los documentos de la oportunidad con el perfil y
las evidencias empresariales autorizadas de EAG.

El alcance termina cuando el analista entrega un borrador revisado y corregido,
con los pendientes explícitos, listo para una aprobación posterior. La salida
automática inicial no constituye por sí sola el final del caso. No cubre
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
de EAG, revisar y corregir sus resultados, identificar faltantes y remitirlo a
aprobación humana antes de cualquier decisión empresarial.

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

### Inventario mínimo propuesto para la primera muestra

Este inventario orienta la solicitud a EAG; no afirma que todos los documentos
ya existan o sean exigibles en toda oportunidad. Se solicita únicamente lo
necesario para los requisitos de la muestra, evitando datos personales ajenos
al análisis.

| Grupo | Campos y soportes mínimos propuestos |
| --- | --- |
| Oportunidad | ID y enlace oficial, entidad, objeto, modalidad, presupuesto y moneda, fechas relevantes y fecha de consulta; conservar como desconocido cualquier dato no disponible. |
| Expediente | Pliego o documento equivalente, anexos y modificaciones/adendas disponibles; nombre, origen, fecha de obtención, versión y estado de lectura de cada archivo. Registrar los documentos esperados pero ausentes. |
| Experiencia | Objeto y especialidad del contrato, rol de EAG, fechas, valor/moneda cuando el requisito lo use y certificado o soporte con localizador. |
| Personal | Identificador interno, rol propuesto, formación, experiencia y certificaciones/vigencias exigidas, con soportes. Un perfil incompleto no se interpreta como falta definitiva de capacidad. |
| Capacidades y equipos | Tipo, cantidad, características y disponibilidad acreditada cuando sea requerida, con soporte. |
| Finanzas y documentación empresarial | Período, valores o indicadores requeridos, unidad/moneda, soporte financiero y documentos legales solicitados por la oportunidad, con fecha y vigencia aplicable. |

Para cada grupo se registra versión, fuente, fecha de revisión y si la
información está completa para ese requisito. Ausente o desconocido no equivale
a cero. El inventario concreto y su suficiencia siguen pendientes de EAG.

### Precondiciones

- Analista autorizado y oportunidad identificada en SECOP II. No se presupone
  que la consulta o descarga oficial funcione antes de la prueba técnica #2.
- Identificar el conjunto de versiones del expediente y del perfil que se
  comparará. No es obligatorio tenerlo completo para registrar un caso, pero
  sus faltantes deben limitar expresamente las conclusiones.
- Autorización para usar la muestra y sus soportes. El permiso para analizarlos
  localmente no autoriza por sí solo enviarlos a un proveedor externo de IA.

## Flujo propuesto

1. El analista consulta y selecciona una oportunidad procedente de SECOP II.
2. El sistema asocia los documentos disponibles desde SECOP II. El analista
   puede añadir únicamente documentos complementarios de esa misma oportunidad.
3. Se extraen requisitos y se conservan sus fuentes. Fechas, cantidades e
   indicadores se evalúan con reglas deterministas; la interpretación
   semántica queda señalada para revisión cuando corresponda.
4. Cada requisito se contrasta con el perfil y las evidencias autorizadas de
   EAG.
5. Para cada requisito se conservan dos referencias separadas: su texto y fuente
   en el expediente de SECOP II, y las evidencias empresariales utilizadas para
   contrastarlo. Ambas incluyen documento, localizador (página, sección o celda),
   fragmento y versión, además del estado y su explicación. Si no hay evidencia
   empresarial, se registra el faltante; no se inventa una referencia.
6. El analista revisa, corrige o marca pendientes. La ausencia, ambigüedad o
   incompatibilidad de evidencia no se convierte en una afirmación de
   cumplimiento.
7. El analista entrega el borrador revisado y corregido, con sus pendientes y
   versiones identificados. Se registra quién revisó, cuándo y el motivo de las
   correcciones. No equivale a aprobación empresarial ni habilita un envío de correo.

### Alternativas y límites de la revisión

- **Documentos no disponibles:** permitir su carga manual asociada al mismo ID
  de SECOP II. Un fallo de descarga no demuestra ausencia de requisitos; sin
  fuentes suficientes, registrar revisión incompleta y no emitir conclusión global.
- **Archivo ilegible, cifrado o extracción/OCR fallidos:** mostrar el fallo y
  solicitar un soporte legible o revisión humana. Texto vacío no equivale a
  expediente sin requisitos. No ocultar fallos como análisis exitoso.
- **Cambios de documentos, adendas o perfil:** crear una nueva versión de análisis,
  conservar la referencia de la anterior dentro de su política de retención y
  repetir las revisiones afectadas. No mezclar versiones ni reutilizar una
  aprobación anterior. Contradicciones sin resolver requieren revisión humana.
- **Requisito posiblemente no aplicable:** conservarlo con justificación y
  `revision_manual` hasta resolver su aplicabilidad; no descartarlo ni añadir
  silenciosamente un quinto estado. La forma de registrar una exclusión validada
  queda pendiente de acuerdo con EAG.

## Salidas

- Matriz de requisitos con uno de estos estados:
  `cumple`, `cumple_parcialmente`, `no_cumple` o `revision_manual`.
- Fuente del requisito y evidencia empresarial trazables por separado: documento,
  localizador, fragmento y versión, o faltante explícito para la evidencia empresarial.
- Lista de documentos, datos o decisiones faltantes.
- Observaciones y correcciones del analista.
- Borrador versionado revisado por el analista, listo para aprobación posterior;
  los pendientes no resueltos permanecen visibles.

## Reglas de interpretación propuestas

| Estado | Regla propuesta |
| --- | --- |
| `cumple` | Requiere evidencia suficiente, vigente cuando el requisito lo exija y compatible con **todas** las condiciones comprobables del requisito. |
| `cumple_parcialmente` | Se reserva para un requisito divisible cuya evaluación parcial esté expresamente admitida por el criterio de la oportunidad y validada por el revisor. Se conocen y documentan las partes satisfechas y no satisfechas; no hay evidencia faltante o ambigua que impida evaluarlo. No equivale a superar un requisito obligatorio. |
| `no_cumple` | Requiere evidencia suficiente de incumplimiento de al menos una condición obligatoria; no se infiere solo por ausencia de documentos. |
| `revision_manual` | Se usa cuando el perfil o la evidencia está incompleta, es ambigua, contradictoria, ilegible o requiere interpretación humana. |

Estas reglas son una propuesta del equipo. La clasificación final y los umbrales
de cada tipo de requisito requieren validación de EAG.

Para evitar resultados incompatibles: una condición obligatoria de un requisito
compuesto con incumplimiento demostrado conduce a `no_cumple`, aunque otras
condiciones se cumplan; conservar también cualquier incertidumbre adicional.
Sin incumplimiento obligatorio demostrado, la información insuficiente conduce
a `revision_manual`. Solo con información suficiente se considera `cumple` o
el caso restringido de `cumple_parcialmente`. Mientras no se haya acordado cuándo
admitir evaluación parcial, no asignarla automáticamente. Estos estados son por
requisito; no implican por sí solos una decisión global de participar.

## Escenarios sintéticos

Los tres escenarios siguientes son ficticios. No describen una oportunidad, un
perfil ni documentos reales de EAG.

Para comprobar la trazabilidad del ejemplo de éxito: el documento ficticio
`PLIEGO-DEMO`, versión 1, página 4, contiene “Se requieren A, B y C vigentes al
01/09/2026”; los soportes ficticios `CERT-A`, `CERT-B` y `CERT-C`, versión 1,
página 1 de cada uno, identifican la certificación correspondiente y una vigencia
que incluye esa fecha. Son referencias ilustrativas, no archivos reales ni una
prueba ejecutada.

| Escenario | Requisito y evidencia sintéticos | Resultado esperado | Razón verificable |
| --- | --- | --- | --- |
| Éxito | El requisito ficticio exige tres certificaciones identificadas (A, B y C) y vigentes. El perfil ficticio aporta tres certificados compatibles, con fecha y localizador verificables. | `cumple` | Existe evidencia suficiente y compatible para cada condición A, B y C. |
| Perfil incompleto | El requisito ficticio exige un indicador financiero de un período definido. El perfil ficticio no contiene el estado financiero de ese período. | `revision_manual` | Falta evidencia; la ausencia no prueba incumplimiento. |
| Incumplimiento | El requisito ficticio exige que el responsable técnico tenga una certificación obligatoria vigente. La evidencia ficticia identifica al responsable y demuestra que su certificación está vencida en la fecha aplicable. | `no_cumple` | Existe evidencia suficiente de incumplimiento de una condición obligatoria. |

En el tercer caso se supone expresamente que los soportes están completos para
la persona evaluada y la fecha aplicable, y no existe una renovación acreditada
pendiente de incorporar. La conclusión se refiere a esa versión del perfil, no
a la imposibilidad definitiva de EAG de presentar otra persona o evidencia.

## Protocolo propuesto de medición

El protocolo se aplicará a las mismas oportunidades, los mismos documentos
disponibles y el mismo resultado esperado versionado. No se compararán casos
distintos ni se tratará una salida propuesta por la aplicación como resultado
correcto sin revisión humana.

Antes de cada corrida, un revisor humano designado debe fijar las entradas:
identificador de oportunidad, versiones del expediente y del perfil empresarial,
y una fecha de corte común. Por separado prepara una referencia de evaluación
con requisitos esperados, estados y evidencias justificadas. Esta referencia no
se entrega al analista ni a la aplicación antes del análisis; se usa después
para evaluar y evitar que conocer las respuestas favorezca artificialmente un método.
Hasta que EAG designe a dicho revisor y autorice una muestra real, este protocolo
permanece pendiente de validación.

| Medida | Definición propuesta | Registro |
| --- | --- | --- |
| Tiempo transcurrido total | Tiempo de reloj desde que las entradas versionadas están disponibles para el participante hasta que entrega el borrador revisado y corregido con pendientes explícitos. Incluye revisión, corrección, esperas y procesamiento automático. | Marca de inicio y fin y criterio común de finalización. |
| Tiempo de procesamiento | Duración de tareas automáticas de extracción y comparación dentro de la corrida. Si se solapan, sus duraciones no se suman para inferir tiempo total de reloj. | Eventos de inicio, fin y resultado de cada tarea. |
| Tiempo de análisis humano | Trabajo activo de lectura, identificación de requisitos, cálculo, contraste y redacción inicial. Se mide en ambos métodos, especialmente en la línea base manual. | Inicio, fin, participante y actividad, sin contar esperas inactivas. |
| Tiempo de revisión | Tiempo de trabajo humano dedicado a verificar requisitos, estados y evidencias del borrador. Excluye pausas sin actividad. | Registro de inicio, fin y participante. |
| Tiempo de corrección | Tiempo de trabajo humano dedicado a cambiar estados, evidencias u observaciones tras la revisión. Excluye pausas sin actividad. | Registro de inicio, fin, participante y tipo de cambio. |
| Trabajo humano total | Suma de minutos-persona de preparación dentro de la corrida, análisis, revisión y corrección. Las actividades de una persona no se cuentan dos veces; participantes simultáneos sí aportan esfuerzo separado. No incluye espera inactiva ni procesamiento automático. | Registros por participante y actividad. |
| Errores frente a la referencia | Discrepancias antes y después de la corrección: requisitos omitidos o inventados, estado incorrecto, evidencia incorrecta y falta de trazabilidad. Destacar falsos cumplimientos: `cumple` sin respaldo suficiente según la referencia revisada. | Conservar salida inicial y revisada; anotar tipo, requisito, revisión humana y resolución. |

Esta primera medición compara **análisis**, no búsqueda ni descarga: la preparación
del expediente, el perfil y la referencia ocurre antes del inicio. Registrar su
coste por separado, sin atribuir al sistema un ahorro de extremo a extremo.
Si después se evalúa el flujo completo, acordar otro protocolo con inicio desde
la búsqueda e incluir obtención, carga y preparación en ambos métodos.

La línea base manual usa las mismas entradas y se evalúa contra la misma referencia,
sin disponer anticipadamente de ella. Evitar que la misma persona repita un caso
conociendo el resultado; si no se puede evitar, documentar el sesgo y alternar el
orden de los métodos entre casos. Registrar experiencia de los participantes,
herramientas, incidencias, fallos y reintentos. No excluir corridas fallidas sin
informarlas ni comparar un borrador incompleto con uno completo como si fueran equivalentes.

Para cada corrida registrar ID, método, versiones de entradas, participante por
rol o seudónimo, tiempos, estado de finalización y discrepancias iniciales y
residuales. Informar tamaño de muestra, número de requisitos de referencia y
conteos de errores por tipo; no presentar una tasa sin su denominador. Los
desacuerdos con la referencia se resuelven por el revisor y se documentan antes
de calcular resultados. Una salida que marque todo como `revision_manual` tampoco
demuestra éxito: informar pendientes, requisitos resueltos y esfuerzo posterior.

Si se dispone de pares válidos, calcular por separado para reloj y trabajo humano:
`reducción (%) = 100 × (tiempo_manual − tiempo_asistido) / tiempo_manual`.
Con tiempo manual cero no se calcula porcentaje; un valor negativo representa
aumento. Informar diferencias absolutas, casos comparables y método de agregación.
El 60 % no es un compromiso ni un resultado confirmado. Umbrales de calidad y
mejora deberán acordarse antes del piloto, no elegirse después de ver los resultados.

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
- Conserva por separado la fuente del requisito y la evidencia empresarial,
  las versiones del expediente/perfil y los faltantes que limiten la comparación.
- No marca `cumple` sin evidencia suficiente y compatible con todas las
  condiciones aplicables.
- No marca `no_cumple` solo porque falte información. Si esta impide evaluar y
  no hay incumplimiento obligatorio demostrado, usa `revision_manual`.
- Permite revisión y corrección humana antes del informe final; cambios
  posteriores invalidan una aprobación previa.
- Expone errores de lectura/extracción e incertidumbres sin convertirlos en
  ausencia de requisitos ni en cumplimiento.
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
| ¿Cómo se acredita y registra que un requisito no aplica? | Comercial y Contratación, con apoyo del área competente | Acordar justificación, evidencia y tratamiento dentro de los estados existentes antes de implementar exclusiones. | Pendiente de EAG |
| ¿Quién puede revisar y aprobar el borrador antes del informe final? | Gerencia | Designar roles autorizados y sustituciones permitidas. | Pendiente de EAG |
| ¿Cuál es el inicio y fin operativo de cada medición y cómo se registra el trabajo humano? | Comercial y Contratación | Validar el protocolo y un formato de registro de tiempos. | Pendiente de EAG |
| ¿Qué umbrales de calidad, errores y mejora permiten aceptar el piloto? | Gerencia y Comercial y Contratación | Acordarlos antes de medir; mantener cualquier porcentaje como propuesta hasta su aceptación. | Pendiente de EAG |
| ¿Se permite transmitir la muestra y sus soportes a un proveedor externo de IA? | Gerencia y responsable designado de la información | Documentar autorización específica, datos permitidos, proveedor y condiciones antes de transmitir; mientras tanto usar datos sintéticos o el trabajo local autorizado. | Pendiente de EAG |
| ¿Qué reglas de acceso, conservación y eliminación aplican a la muestra y sus respaldos? | Gerencia y área documental | Definir responsable, origen del plazo y tratamiento de respaldos antes de producción. | Pendiente de EAG |

La entrega de este borrador documental no espera esas respuestas, pero tampoco
las sustituye. Se puede avanzar a la prueba técnica #2 con datos públicos y el
caso provisional; la issue #1 permanece abierta hasta completar su revisión y
la validación empresarial pendiente. Este documento no implementa otras issues.

## Exclusiones explícitas

- Registro manual de oportunidades.
- Postulación o envío automático de propuestas.
- Decisión autónoma de viabilidad, aprobación empresarial o adjudicación.
- Afirmar integración real con SECOP II, resultados de prueba o mejoras de
  tiempo antes de ejecutarlas y revisarlas.
- Incorporar al repositorio expedientes reales, documentos internos, datos
  personales o secretos.
