# [MVP-02] Comprobar API SECOP II y disponibilidad real de documentos

## Objetivo

Resolver el principal riesgo técnico con un script pequeño y evidencia reproducible.

## Dependencias

- MVP-01

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Implementar un spike Python aislado que consulte una muestra acotada, permita filtrar y exporte metadatos JSON/CSV a una carpeta ignorada.
- Verificar esquema y propietario de p6dx-8zbt y dmgg-8hin, relación entre IDs y cobertura de pliegos de procesos abiertos.
- Comprobar descarga autorizada de archivos de una muestra, con timeout, límite de tamaño, validación de URL/redirecciones y sin cargar documentos a IA.
- Documentar fecha, consultas, IDs públicos, tipos de documentos, resultados y limitaciones en docs/SECOP_SPIKE.md.

## Criterios de aceptación

- [ ] El script y sus instrucciones funcionan desde entorno limpio; token opcional/requerido según verificación, siempre en entorno y nunca en logs.
- [ ] Hay pruebas offline de filtros, paginación, respuesta vacía, errores 429/5xx y URL no permitida.
- [ ] Una ejecución de red acotada deja evidencia de éxitos y fallos; un mock no cuenta como integración real.
- [ ] Se distingue descarga encontrada de expediente completo; no se presupone cobertura de oportunidades abiertas.
- [ ] El informe recomienda continuar, ajustar alcance o usar carga manual según resultados; si no hay acceso, permanece explícitamente pendiente.

## Verificación

Pruebas unitarias offline y comando separado opt-in para el smoke test real. Redactar resultados antes de elegir estrategia documental.

## Fuera de alcance

Frontend, base de datos productiva, OCR, OpenAI, scraping del portal y sincronización masiva.

## Modelo sugerido para programar

GPT-5.6 Terra · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa únicamente el spike SECOP en Python: consulta acotada, filtros, verificación de relación con documentos y descarga segura de una muestra. Añade pruebas offline y ejecuta una comprobación real si hay acceso. Documenta límites y evidencia sin afirmar cobertura total. No construyas frontend ni IA.
```
