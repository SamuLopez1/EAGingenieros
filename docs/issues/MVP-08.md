# [MVP-08] Extraer texto de PDF, DOCX y XLSX con OCR básico

## Objetivo

Obtener texto trazable sin confundir fallos de extracción con ausencia de requisitos.

## Dependencias

- MVP-07

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear pipeline por formato y activar OCR solo cuando el PDF no tenga texto suficiente.
- Preservar documento, página/sección/celda y versión como localizadores.
- Procesar en tareas con timeout, límites de páginas/recursos, reintentos e indicadores de calidad.
- Exponer estados de extracción y advertencias al analista.

## Criterios de aceptación

- [ ] Fixtures sintéticas PDF textual, escaneado, DOCX y XLSX producen texto y localizadores verificables.
- [ ] Archivo corrupto, cifrado o exceso de presupuesto termina con error visible y recuperable.
- [ ] OCR de mala calidad o texto vacío se marca para revisión; no produce éxito silencioso.
- [ ] Reprocesamiento por hash/versión evita trabajo innecesario sin mezclar versiones.
- [ ] Pruebas offline no requieren OpenAI y comandos de OCR documentan dependencias del sistema.

## Verificación

Pruebas por formato, límites y fallos; inspección manual de localizadores en una muestra autorizada fuera de Git.

## Fuera de alcance

Extracción semántica de requisitos o evaluación de cumplimiento.

## Modelo sugerido para programar

GPT-5.6 Terra · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Añade extracción por formato y OCR básico con trazabilidad y límites de recursos. Prueba escaneados, archivos corruptos y texto vacío. Mantén esta etapa independiente de IA y de evaluación de cumplimiento.
```
