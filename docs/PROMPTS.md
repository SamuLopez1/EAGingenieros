# Prompts y uso eficiente de modelos

## Modelo recomendado

- **GPT-5.6 Luna, Medium:** opción habitual para tareas bien delimitadas, documentación, formularios y UI sobre contratos existentes. Low basta para ajustes de texto sencillos.
- **GPT-5.6 Terra, Medium:** integración SECOP, estructura del proyecto y procesamiento documental.
- **GPT-5.6 Terra, High:** permisos, archivos no confiables, extracción IA, comparación y operación; revisar si Medium ya es suficiente.
- **GPT-5.6 Sol:** reservar para un bloqueo difícil o revisión crítica que Terra no resuelva con evidencia. No usarlo por defecto ni elegir Ultra para todo.

Son recomendaciones para el agente que programa, no una selección del modelo de IA que analizará las licitaciones. No se modificó la configuración de modelos de la aplicación ni se iniciaron nuevas tareas automáticamente.

La documentación oficial consultada el 2 de septiembre de 2026 indica menor coste por token/crédito para Luna que para Terra/Sol; las cuotas y disponibilidad dependen del plan. Un modelo más económico no garantiza usar menos tokens ni obtener el menor coste total si necesita muchas correcciones. Mayor esfuerzo de razonamiento consume más tokens.

Fuentes: [modelos](https://learn.chatgpt.com/docs/models) y [consumo y tarifas](https://learn.chatgpt.com/docs/pricing). Verificar cambios antes de presupuestar; no confundir tarifas de API del producto con límites de la suscripción usada para programar.

## Cómo avanzar con control

1. Abrir una tarea por issue, dentro de este proyecto, y seleccionar el modelo sugerido si está disponible. No pegar toda la conversación: usar issue y archivos del repositorio.
2. Para revisar primero el enfoque, usar el prompt A. Cuando el alcance esté claro, usar B en esa misma tarea. Si la tarea es pequeña y está perfectamente definida, se puede ir directamente a B.
3. Revisar pruebas y diff antes de fusionar. Usar C para la revisión; subir de modelo solo cuando el riesgo lo justifique o haya un bloqueo concreto.
4. Tras dos intentos fallidos sobre el mismo problema, pedir un diagnóstico con evidencia; no repetir el prompt completo ni subir a máximo esfuerzo sin motivo.

### A. Analizar antes de editar

```text
Revisa la issue #NUMERO de SamuLopez1/EAGingenieros, AGENTS.md y docs/CONTEXTO.md. Inspecciona solo el código relevante y comprueba sus dependencias. No edites archivos todavía. Propón un plan breve con archivos a tocar, pruebas y riesgos. Señala supuestos y bloqueos reales. No amplíes el alcance a otras issues.
```

### B. Implementar lo revisado

```text
Implementa únicamente el plan revisado para la issue #NUMERO. Usa una rama exclusiva y preserva cambios ajenos. Aplica sus criterios de aceptación, reutiliza pruebas existentes y documenta cómo verificarlo. Puedes hacer commit, push y abrir un PR para revisión, pero no fusionarlo. Si un requisito necesita validación de EAG o acceso externo, déjalo explícitamente pendiente: no inventes resultados ni cierres la issue por haber creado un PR. Al terminar resume cambios, comandos y resultados, riesgos y siguiente paso.
```

### C. Revisar antes de fusionar

```text
Revisa el diff y las pruebas del PR de la issue #NUMERO frente a sus criterios de aceptación. Busca errores de comportamiento, permisos, pérdida de datos, evidencia inventada y pruebas insuficientes. No hagas cambios cosméticos ni edites archivos en esta revisión. Reporta hallazgos con archivo/línea, impacto y verificación sugerida. Si no encuentras hallazgos, indica qué comprobaste y qué no pudiste verificar. No fusiones el PR.
```

## Prompt específico de cada issue

Usar cada texto después de leer las reglas anteriores. Estos prompts permiten implementar directamente; si quieres aprobar primero el enfoque, antepone: “Solo analiza y propón el plan; aún no edites archivos”.

### #1 · Definir caso de uso mínimo y criterios de aceptación de EAG

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/1) · GPT-5.6 Luna · Medium

```text
Trabaja solo en la issue #1 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Redacta el caso de uso mínimo del analista y los criterios verificables. Usa un ejemplo sintético, separa hechos de supuestos y prepara las preguntas mínimas para EAG. No programes ni des por confirmada la muestra real.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #2 · Comprobar API SECOP II y disponibilidad real de documentos

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/2) · GPT-5.6 Terra · Medium

```text
Trabaja solo en la issue #2 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa únicamente el spike SECOP en Python: consulta acotada, filtros, verificación de relación con documentos y descarga segura de una muestra. Añade pruebas offline y ejecuta una comprobación real si hay acceso. Documenta límites y evidencia sin afirmar cobertura total. No construyas frontend ni IA.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #3 · Crear estructura base, contratos iniciales y CI

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/3) · GPT-5.6 Terra · Medium

```text
Trabaja solo en la issue #3 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Crea solo la estructura ejecutable FastAPI + React/TypeScript y CI tomando en cuenta el spike. Fija comandos de instalación, lint, pruebas y build, y comprueba health API→UI. Mantén la base pequeña; no agregues módulos futuros.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #4 · Implementar autenticación, roles y aislamiento de datos

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/4) · GPT-5.6 Terra · High

```text
Trabaja solo en la issue #4 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa autenticación por invitación y dos roles, verificando permisos en servidor y datos. Prioriza pruebas negativas de acceso y escalada de privilegios. No marques listo el proveedor real si solo se probaron mocks.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #5 · Persistir oportunidades y sincronizar SECOP de forma idempotente

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/5) · GPT-5.6 Terra · Medium

```text
Trabaja solo en la issue #5 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa persistencia y sincronización SECOP a partir del spike. Demuestra idempotencia, actualizaciones y recuperación de fallos. Usa contratos reales verificados y no añadas análisis documental.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #6 · Construir listado, filtros y detalle de oportunidades

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/6) · GPT-5.6 Luna · Medium

```text
Trabaja solo en la issue #6 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa listado, filtros guardados y detalle usando exclusivamente la API existente. Usa estilo EAG y estados de carga/vacío/error. Prueba navegación, permisos y accesibilidad; evita añadir un dashboard fuera de alcance.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #7 · Incorporar descarga y carga manual seguras de documentos

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/7) · GPT-5.6 Terra · High

```text
Trabaja solo en la issue #7 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa documentos privados con descarga acotada y carga manual. Incluye validación de archivo, cuarentena/antivirus, límites, SSRF y autorización. No proceses ni envíes a IA archivos no aprobados.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #8 · Extraer texto de PDF, DOCX y XLSX con OCR básico

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/8) · GPT-5.6 Terra · Medium

```text
Trabaja solo en la issue #8 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Añade extracción por formato y OCR básico con trazabilidad y límites de recursos. Prueba escaneados, archivos corruptos y texto vacío. Mantén esta etapa independiente de IA y de evaluación de cumplimiento.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #9 · Registrar perfil y evidencias empresariales de EAG

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/9) · GPT-5.6 Luna · Medium

```text
Trabaja solo en la issue #9 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa perfil empresarial con evidencias, vigencias y versiones usando almacenamiento y permisos existentes. Usa datos sintéticos y distingue información pendiente de verificada. No desarrolles aún el comparador.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #10 · Extraer requisitos con IA y evidencia verificable

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/10) · GPT-5.6 Terra · High

```text
Trabaja solo en la issue #10 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa únicamente extracción estructurada detrás de un adaptador. Verifica evidencia contra el texto, resistencia a instrucciones embebidas y límites de coste. Usa mocks para unitarias y separa evaluación real autorizada. No decidas si EAG participa.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #11 · Comparar requisitos y habilitar revisión y aprobación humana

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/11) · GPT-5.6 Terra · High

```text
Trabaja solo en la issue #11 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Implementa comparación explicable y revisión humana, con estados tipados y aprobación versionada. Demuestra que evidencia insuficiente requiere revisión y que cualquier cambio invalida aprobación. No implementes envíos todavía.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #12 · Generar informe PDF aprobado y enviar correo controlado

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/12) · GPT-5.6 Luna · Medium

```text
Trabaja solo en la issue #12 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Genera PDF a partir de análisis aprobado y añade envío controlado por correo. Verifica permisos, vigencia, deduplicación y render visual. Usa una bandeja de prueba y no envíes información real sin autorización.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #13 · Validar retención, operación, recuperación y despliegue seguro

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/13) · GPT-5.6 Terra · High

```text
Trabaja solo en la issue #13 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Audita y completa operación, purga y recuperación sobre el MVP existente. Prueba los 30 días con reloj controlado, backups/restauración y acceso en staging. Documenta bloqueos y no declares producción lista si faltan autorización o pruebas.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```

### #14 · Ejecutar piloto con EAG, medir resultados y decidir lanzamiento

[Issue](https://github.com/SamuLopez1/EAGingenieros/issues/14) · GPT-5.6 Luna · Medium

```text
Trabaja solo en la issue #14 de SamuLopez1/EAGingenieros. Lee AGENTS.md y docs/CONTEXTO.md, comprueba las dependencias y conserva el alcance de la issue.
Prepara y ejecuta el piloto solo con datos y usuarios autorizados. Compara contra revisión manual, mide errores y tiempo total y entrega go/no-go con evidencia. Si faltan datos, deja listo el protocolo y no inventes resultados ni cierres la issue.
Entrega pruebas y resultados reales, documentación breve y PR sin fusionar. Señala cualquier criterio pendiente; no lo marques cumplido por usar un mock.
```
