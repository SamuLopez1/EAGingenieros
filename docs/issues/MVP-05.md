# [MVP-05] Persistir oportunidades y sincronizar SECOP de forma idempotente

## Objetivo

Convertir el spike aprobado en un conector operacional, sin duplicados.

## Dependencias

- MVP-02
- MVP-04

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Normalizar oportunidades y preservar ID, URL, fuente y fechas originales mediante migraciones.
- Construir cliente oficial con filtros permitidos, paginación, timeout, reintentos limitados y manejo de cuota.
- Crear sincronización manual y diaria propuesta a las 06:00 America/Bogota con ventana de 7 días validada contra el esquema real.
- Registrar estado y métricas de cada ejecución; restringir disparo manual.

## Criterios de aceptación

- [ ] Repetir ejecución o reintentar un lote no duplica oportunidades.
- [ ] Se actualizan cambios tardíos usando el campo temporal realmente disponible.
- [ ] Consultas y filtros se validan; no hay concatenación insegura de consultas recibidas del cliente.
- [ ] Una falla parcial queda visible y puede retomarse sin ocultar errores.
- [ ] Pruebas cubren paginación, deduplicación, updates, 429, timeout y autorización; hay smoke real separado.

## Verificación

Contratos con fixtures mínimas públicas/anonimizadas, pruebas de BD y dos sincronizaciones sobre la misma muestra.

## Fuera de alcance

OCR, extracción con IA y descargas ilimitadas.

## Modelo sugerido para programar

GPT-5.6 Terra · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa persistencia y sincronización SECOP a partir del spike. Demuestra idempotencia, actualizaciones y recuperación de fallos. Usa contratos reales verificados y no añadas análisis documental.
```
