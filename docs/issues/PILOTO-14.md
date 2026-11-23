# Piloto EAG · Guion de aceptación

Issue [#14](https://github.com/SamuLopez1/EAGingenieros/issues/14). Estado del
piloto empresarial **pendiente**. Usar la [bitácora](PILOTO-14-BITACORA.md) en
el espacio privado de EAG. El [caso de uso](../CASO_DE_USO.md) define la
revisión humana y la comparación entre métodos.

## Preparación

| Responsable propuesto | Entrega antes de la sesión |
| --- | --- |
| Gerencia y responsable de datos | Aprueban alcance, finalidad, muestra, perfiles de acceso, conservación y tratamiento externo. Designan a quien firma la decisión final y a quien arbitra discrepancias. |
| Comercial y Contratación | Selecciona las oportunidades, asigna analistas y aporta el flujo manual vigente, los filtros y la evidencia de encaje que se usará. |
| Talento Humano | Entrega disponibilidad autorizada y versionada por cargo, dedicación y periodo. Distingue cobertura verificada, sin cobertura y pendiente de confirmar. |
| Finanzas | Entrega supuestos, moneda, costos, fuentes y reglas de comparación. Decide cómo tratar impuestos, retenciones y costos de personal. |
| Operación y Seguridad | Habilitan staging HTTPS, una cuenta analista y una administradora, una identidad de otra organización para pruebas cuando esté disponible y un buzón de prueba autorizado. Verifican migraciones, servicio de extracción, límites y procedimiento de recuperación. |
| Facilitador/a y revisor/a | Congelan entradas, entrenan a usuarios con un caso sintético y acuerdan umbrales antes de abrir las corridas. El revisor custodia la referencia y la usa después para evaluar los dos métodos. |

Preparar al menos **20 oportunidades revisadas manualmente** si EAG autoriza
y aporta esa muestra. Si aporta menos, registrar el número, causas, sesgos y
alcance de las conclusiones. Elegir dentro de la muestra casos con cierre
conocido y desconocido, documento oficial y carga manual, PDF escaneado,
adendas contradictorias, falta de evidencia, brecha de personal y costos
indispensables faltantes. Un caso alternativo sintético puede ejercitar una
rama rara en el ensayo técnico y queda fuera de las métricas empresariales.

Para cada oportunidad fijar fecha de corte, copia de la vista de catálogo,
documentos y versiones accesibles, versión del perfil, disponibilidad y
costos que ambos métodos pueden usar. El revisor prepara en privado la
referencia por campo y requisito, con estado, fuente, versión y localizador.
Cuando falte evidencia, la referencia conserva ese faltante. Fijar también
los criterios de determinación de plazos, encaje y margen.

Para la práctica sin datos de EAG, preparar una ficha sintética con
pliego que exija un residente al 60 % durante un intervalo conocido y un
perfil con 40 % confirmado en ese mismo intervalo. La brecha esperada es
20 puntos porcentuales. En otra ficha omitir la disponibilidad y comprobar
que queda pendiente de confirmar. Como ejercicio financiero, usar ingreso
de 100 y costos de 70 en una sola moneda. El escenario completo debe dar
utilidad de 30 y margen de 30 %. Quitar el costo de contratación y
comprobar que el escenario vuelve a quedar pendiente. Estos valores son
entradas de entrenamiento.

La muestra, la referencia, los resultados y la bitácora diligenciada quedan
en el espacio de EAG con acceso limitado. En Git y en los logs usar códigos de
caso y conteos. Aplicar el [procedimiento de operación](OPERACION-13.md).
Usar el adaptador offline mientras EAG no autorice expresamente el proveedor
externo y su tratamiento de datos. Acordar origen, buzón y destinatarios antes
de activar correo real.

## Guion de la sesión

1. **Apertura y formación.** Confirmar la revisión desplegada y que
   Operación completó el smoke de staging. Repasar roles, protección de
   documentos, significado de los estados y cómo registrar tiempos.
   Mostrar un caso sintético y practicar una corrección y su comprobación
   en el historial. Dejar esta formación fuera de los tiempos de análisis.
2. **Línea base manual.** El analista aplica el flujo actual sobre las
   entradas fijadas. Registra búsqueda, obtención de documentos, revisión,
   contraste, correcciones de las tres áreas y entrega del informe interno.
3. **Flujo asistido.** El analista entra al catálogo, abre la ficha, prepara el
   expediente, revisa extracción y requisitos y pulsa **Comparar con EAG**.
   Comercial revisa evidencia y encaje. Talento Humano valida disponibilidad
   y brechas. Finanzas compara escenarios y documenta costos pendientes.
   El administrador registra correcciones justificadas y revisiones, aprueba
   la versión vigente y habilita el PDF. Verificar entrega al buzón autorizado
   cuando esté dentro del alcance de la sesión.
4. **Conciliación.** Conservar las salidas inicial y final de ambos métodos
   en el espacio privado. Compararlas con la referencia. Acordar discrepancias,
   registrar decisiones y repetir el control afectado si se modifica una
   entrada. Repetir una comprobación crítica después de corregirla.
5. **Cierre.** Revisar tiempos y calidad, tramitar incidentes y completar el
   acta. Gerencia registra y firma la decisión a partir de la validación de
   Comercial, Talento Humano, Finanzas y Seguridad.

Para medir el **recorrido completo**, iniciar ambos relojes cuando el
participante recibe la consigna, acceso a la misma vista de catálogo y
entradas autorizadas con la misma fecha de corte. Terminar al entregar
el informe revisado al destino interno acordado, con pendientes explícitos.
Incluir obtención, carga o asociación de archivos, contraste, revisión,
correcciones, reintentos y esperas. Si se mide solo análisis, empezar desde
el expediente y perfil preparados y reportar esa medición por separado.
Usar analistas distintos de experiencia comparable o alternar el orden de
los métodos entre casos. Registrar qué información pudo transferirse
entre corridas.

## Pruebas de aceptación

Ejecutar los controles de fallo o fuera de alcance con un caso de prueba
aislado. Registrar revisión desplegada, rol, caso, resultado observado y
referencia de evidencia en cada fila. Usar **aprobada**, **fallida**,
**bloqueada** o **fuera de alcance** según la ejecución. Un bloqueo conserva
condición, responsable y acción requerida.

| ID | Acción del participante | Resultado esperado y evidencia |
| --- | --- | --- |
| UAT-01 · Acceso | Abrir staging sin sesión, entrar como analista y administrador, intentar consultar otra organización y una acción de aprobación como analista. | Sesión requerida, roles correctos, organización ajena y acción administrativa denegadas. Registrar códigos y rol, sin tokens. |
| UAT-02 · Catálogo | Revisar fecha de sincronización, filtrar por entidad, ubicación, modalidad y cierre cuando haya datos. Abrir A, volver, abrir B y comprobar ambos enlaces oficiales. | Filtros conservados, fichas y referencias distintas. Distinguir estado oficial y vigencia abierta, cerrada, vencida o desconocida al corte. Registrar fecha de recepción cuando esté disponible y señalar fechas ausentes. |
| UAT-03 · Expediente | Abrir una asociación oficial validada, cargar manualmente un documento y una adenda cuando falte la fuente y volver de B a A. Probar cuarentena con fixture aprobada para el ensayo. | A y B conservan documentos propios con origen, versión e ID de oportunidad. El archivo en cuarentena queda excluido del uso y de la descarga. |
| UAT-04 · Extracción | Procesar PDF digital y escaneado, DOCX y XLSX donde estén en la muestra. Abrir las citas y provocar un fallo o cobertura insuficiente con una fixture aislada. | Texto con página, sección o celda comprobable y vínculo a versión. OCR o fallo visible. La cobertura insuficiente queda pendiente de revisión. |
| UAT-05 · Requisitos | Generar resumen y requisitos tipados desde el expediente seleccionado. Contrastar requisito dudoso, una adenda contradictoria y un expediente incompleto. | Las citas corresponden a sus versiones. Contradicción y omisiones quedan señaladas, sin derivar cumplimiento automático. |
| UAT-06 · Perfil y matriz | Comparar A y B con el perfil vigente. Abrir evidencia del pliego y evidencia empresarial. Comparar historial del perfil y corregir un estado con justificación. | Resultados y fuentes propios de cada ficha. Evidencia débil como revisión manual. La corrección autorizada conserva actor, fecha, revisión y motivo. El perfil conserva el historial. |
| UAT-07 · Encaje y personal | Comercial valida la línea de servicio con su evidencia. Talento Humano verifica un cargo con cobertura, otro con brecha parcial o 0 % verificado y otro con disponibilidad desconocida. Probar periodos solapados. | Dedicación y periodos trazables, brechas previsibles por intervalo y propuesta de evaluar contratación o reasignación. La disponibilidad desconocida queda por confirmar y Talento Humano registra una decisión. |
| UAT-08 · Margen | Finanzas captura un escenario base y uno alternativo con ingreso, costos directos e indirectos, personal, contratación y contingencia en la moneda acordada. Quitar un costo indispensable y probar ingreso cero en un escenario separado. | La utilidad equivale a ingreso menos costos y el margen a utilidad sobre ingreso. Si falta un costo, cálculo pendiente. Con ingreso cero, margen indefinido. El presupuesto publicado aparece como referencia salvo un supuesto explícito y justificado. El costo de personal se cuenta una vez. |
| UAT-09 · Aprobación y cambios | Aprobar humanamente una revisión. En ensayos aislados, cambiar pliego, adenda o perfil. Comprobar las consecuencias en informe y resultados dependientes. | Cada cambio invalida la aprobación afectada; el PDF anterior queda bloqueado y escenarios ligados se muestran desactualizados. Guardar nueva revisión y aprobación con evidencias vigentes. |
| UAT-10 · Informe y correo | Abrir PDF vigente con cuenta autorizada, contrastar la versión aprobada y rechazar acceso anónimo. Intentar un destinatario fuera de la lista en la prueba técnica y repetir el envío a un buzón autorizado. | PDF privado con versión, fecha, aprobador, citas y pendientes. Destino no autorizado bloqueado antes del proveedor. Registrar idempotencia en la bandeja y confirmar recepción en el buzón real autorizado, sin capturar el cuerpo. |
| UAT-11 · Operación | Operación demuestra caducidad, restauración y rollback al equipo en un destino aislado con la versión integrada. Verificar acceso posterior a los contenidos de prueba. | Datos vencidos inaccesibles, purga reaplicada al restaurar y maestros preservados. Anotar referencia del runbook, revisión y comandos, con evidencia depurada. |
| UAT-12 · Decisión de negocio | Comercial, Talento Humano y Finanzas validan o dejan pendiente su parte. Presentar comparación manual/asistida y conflictos a Gerencia. | Acta por área con decisión, evidencia, versión y pendientes. Acción, responsable, plazo y comprobación siguiente para cada condición. Decisión firmada por Gerencia. |

## Medición y acta

- Medir tiempo transcurrido como **fin menos inicio** e incluir esperas.
  Medir trabajo humano en minutos-persona por fase y por participante.
  Registrar procesamiento y esperas por separado. Evitar duplicar periodos
  solapados de una misma persona. Conservar los tiempos totales y las
  correcciones antes de calcular comparaciones.
- Usar solo pares con iguales entradas, alcance y criterio de finalización
  para calcular diferencias de tiempos. Informar incompletos, fallidos,
  reintentos y motivos por separado. Calcular para reloj y esfuerzo humano
  la mediana de las diferencias manual menos asistido por caso. Para
  porcentajes usar **100 × (manual − asistido) / manual** por par,
  excluyendo denominador cero y explicitando el número de pares. Reportar
  tamaño, rango y limitaciones. El 60 % queda como hipótesis sin validar.
- Comparar cada salida inicial y final contra la referencia. Contar por
  campo requisitos omitidos, inventados, estados erróneos, citas incorrectas
  y faltantes no advertidos. Marcar falso cumplimiento cuando el resultado
  afirma que se cumple un requisito sin evidencia suficiente. Reportar su
  número y el total de requisitos marcados como cumplidos. Informar
  requisitos que siguen en revisión manual y la cobertura evaluada.
- Acordar antes de medir los máximos admisibles de error y pendientes,
  criterios de utilidad y objetivos de tiempo y esfuerzo. Incidentes
  críticos de seguridad o falsos cumplimientos sin resolver bloquean el
  lanzamiento. Una prueba bloqueada conserva su motivo y el alcance que
  dejó sin comprobar. Solo Gerencia registra go/no-go con evidencia de las
  tres áreas y de Seguridad.

## Comprobaciones técnicas previas

Ejecutadas el 23 de noviembre de 2026. Las identidades y los documentos son
de fixture. El envío de correo de los tests se simula. Son dos revisiones
de código distintas; la integración para el piloto completo debe probarse
sobre un solo SHA desplegado que contenga #13, #23 y #24.

| Revisión | Comando desde apps/api | Resultado |
| --- | --- | --- |
| [#13 · af097de](https://github.com/SamuLopez1/EAGingenieros/pull/37) | python -m pytest -q tests/test_auth.py tests/test_catalog_filters.py tests/test_dossier.py tests/test_extraction.py tests/test_extraction_jobs.py tests/test_profile.py tests/test_requirements.py tests/test_comparison.py tests/test_reports.py tests/test_retention.py | 88 aprobadas, 1 omitida por configuración de OCR real. |
| #13 · af097de | EAG_TEST_POSTGRES=1 python -m pytest -q tests/test_retention_postgres.py | 1 aprobada en PostgreSQL local desechable. Se repitió tras iniciar Docker Desktop, que inicialmente no tenía el motor disponible. |
| [#24 · 80803ae](https://github.com/SamuLopez1/EAGingenieros/pull/33), con [#23 · f396869](https://github.com/SamuLopez1/EAGingenieros/pull/32) | python -m pytest -q tests/test_staffing.py tests/test_margin.py | 14 aprobadas. |

Para repetir el ensayo de navegador con identidades y datos sintéticos,
usar los comandos de la revisión correspondiente. Los dos scripts usan
la misma familia de puertos locales, así que se ejecutan por separado.
El [runbook de #13](OPERACION-13.md) especifica los preparativos y el smoke
de acceso HTTPS para el despliegue autorizado.

~~~powershell
# Desde la raíz de #13
python scripts/mvp06_preview.py --dossier --extraction --comparison --report --browser-cli RUTA_A_PLAYWRIGHT_CLI

# Desde la raíz de #24, que incluye #23
python scripts/mvp06_preview.py --dossier --extraction --comparison --staffing --margin --browser-cli RUTA_A_PLAYWRIGHT_CLI
~~~

**Pendiente de ejecución empresarial.** Los PR de las dependencias siguen
en borrador. No consta un staging desplegado ni una referencia a la
autorización de usuarios, expedientes y buzón. El smoke
`python -m app.operations.staging_smoke` devolvió código 2 al faltar el
origen HTTPS y los JWT de ambas cuentas. Los tiempos empresariales,
correcciones del piloto y decisiones de las áreas quedan sin registrar hasta
que se ejecute con EAG.

## Checklist de puesta en marcha

- [ ] Staging integrado identificado por SHA y migración, permisos y
  recuperación verificados por Operación y Seguridad.
- [ ] Muestra, participantes, roles, buzón, alcance y tratamiento aprobados.
- [ ] Formación y umbrales registrados antes de medir. Pares y denominadores
  validados por el revisor.
- [ ] Acta con encaje, disponibilidad y margen revisada por las áreas y
  controles críticos resueltos.
- [ ] Go/no-go de Gerencia, responsables y plazos anotados. Conservar o
  eliminar los registros del piloto según autorización de EAG.
