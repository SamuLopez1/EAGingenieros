# [MVP-10] Extraer requisitos con IA y evidencia verificable

## Objetivo

Convertir texto en requisitos estructurados sin perder fuente ni control de coste.

## Dependencias

- MVP-08

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear adaptador de proveedor y esquema tipado para requisitos, categorías y evidencia.
- Versionar prompts/esquemas y registrar modelo/configuración sin contenido sensible en logs.
- Limitar tokens, tamaño de lotes, reintentos, concurrencia y coste; evitar llamadas repetidas por hash/versión.
- Validar fragmentos/localizadores contra texto fuente y tratar instrucciones en documentos como datos no confiables.

## Criterios de aceptación

- [ ] Salida inválida, evidencia inexistente o texto ambiguo se rechaza o deriva a revisión manual.
- [ ] No hay cumplimiento final generado por esta etapa; solo requisitos y advertencias.
- [ ] Pruebas incluyen prompt injection documental, alucinación de fuente, truncamiento y error del proveedor.
- [ ] Existe evaluación sobre conjunto sintético/revisado y smoke opt-in real con coste observado.
- [ ] Modelo configurable, secretos en backend y envío interno condicionado a autorización; documentación actual del proveedor verificada.

## Verificación

Marca una versión del pliego y de cada adenda «En revisión» en el expediente y completa
su extracción. Pulsa «Generar resumen y requisitos». El API publica
`POST /api/v1/opportunities/{opportunity_id}/requirements`, con respuesta privada.
Cada hallazgo incluye la cita literal, el documento, la versión, el SHA-256 y el
localizador. El adaptador offline reconoce rótulos explícitos de objeto, entregables,
plazos, alertas, habilitantes, criterios evaluables y obligaciones de ejecución. Los
campos sin evidencia quedan pendientes. Los avisos de adendas conservan ambas citas
cuando se detecta un cambio en la misma materia. Revisa la precedencia manualmente.

El análisis limita el lote a 80 fragmentos y 12.000 bytes UTF-8 y la respuesta a 80
hallazgos. La caché de proceso conserva hasta 16 resultados por huella de oportunidad,
organización, versión y contenido de origen, con vigencia de hasta cinco minutos y
acotada por la retención del documento. El contrato y el adaptador exponen su versión.

### Verificación offline

Desde `apps/api`, ejecuta `python -m pytest tests/test_requirements.py`. El caso
anotado sintético cubre objeto, plazo, entregable y los tres tipos de requisitos,
con una adenda que cambia el cierre. Otros casos prueban aislamiento, evidencias
inventadas, instrucciones documentales, truncamiento y errores con transporte simulado.

### Proveedor real, optativo

El smoke independiente envía una única fixture sintética incorporada. Requiere
autorización explícita, una credencial en `OPENAI_API_KEY`, un modelo compatible con
Responses y Structured Outputs, las tarifas vigentes de ese modelo y un presupuesto.

```text
python -m app.documents.requirements_smoke --authorized-synthetic --model MODELO --input-usd-per-million TARIFA_ENTRADA --output-usd-per-million TARIFA_SALIDA --max-usd PRESUPUESTO
```

El adaptador usa un límite previo estimado, 1.200 tokens de salida, una petición por
ejecución, sin herramientas ni reintentos. Imprime únicamente el uso reportado,
el coste calculado a partir de las tarifas indicadas y el resultado de la fixture.
`store=false` controla el almacenamiento de la respuesta. El producto usa el
adaptador offline y el smoke no acepta archivos privados.

La ejecución real queda pendiente de una credencial y un presupuesto expresamente
autorizados. Referencias verificadas en la documentación oficial de
[Responses](https://developers.openai.com/api/reference/resources/responses/methods/create)
y [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Fuera de alcance

Elegir el modelo de producción por el modelo usado para programar, enviar internos sin permiso o afirmar exactitud sin medición.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa únicamente extracción estructurada detrás de un adaptador. Verifica evidencia contra el texto, resistencia a instrucciones embebidas y límites de coste. Usa mocks para unitarias y separa evaluación real autorizada. No decidas si EAG participa.
```
