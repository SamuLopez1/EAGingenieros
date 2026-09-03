# [MVP-03] Crear estructura base, contratos iniciales y CI

## Objetivo

Disponer de una base pequeña ejecutable y comprobada, adaptada al resultado del spike.

## Dependencias

- MVP-02

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear apps/api y apps/web con FastAPI y React/TypeScript; elegir y fijar versiones compatibles.
- Documentar decisiones breves de arquitectura, configuración por entorno, OpenAPI y manejo uniforme de errores.
- Añadir lint, pruebas, typecheck y build a CI; ejemplos de entorno sin valores reales.
- Documentar arranque local y health check sin conexiones de pago obligatorias.

## Criterios de aceptación

- [ ] API expone health check y UI mínima verifica comunicación; no hay pantallas de negocio ficticias.
- [ ] Instalación y comandos reproducibles con lockfiles o equivalentes; CI verifica backend y frontend.
- [ ] OpenAPI se sirve y se define cómo generar el cliente TypeScript; sin duplicar tipos manualmente sin justificación.
- [ ] Secretos y documentos quedan fuera de Git; CORS se restringe por entorno.
- [ ] Se conservan los entregables del spike y no se introducen todos los servicios del roadmap de forma prematura.

## Verificación

Smoke API, prueba de render básica, lint/typecheck/build y ejecución del workflow en GitHub.

## Fuera de alcance

Módulos de negocio, IA, credenciales reales y despliegue público sin autenticación.

## Modelo sugerido para programar

GPT-5.6 Terra · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Crea solo la estructura ejecutable FastAPI + React/TypeScript y CI tomando en cuenta el spike. Fija comandos de instalación, lint, pruebas y build, y comprueba health API→UI. Mantén la base pequeña; no agregues módulos futuros.
```
