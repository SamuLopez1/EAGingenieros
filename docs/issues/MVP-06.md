# [MVP-06] Construir listado, filtros y detalle de oportunidades

## Objetivo

Entregar el primer flujo visible y útil al analista, con datos reales del backend.

## Dependencias

- MVP-05

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Crear listado paginado, filtros y detalle con enlace oficial y fecha de última sincronización.
- Definir filtros guardados administrables para EAG usando campos disponibles.
- Aplicar identidad visual sobria EAG, diseño responsive y navegación accesible.
- Mostrar carga, vacío, error y datos desactualizados sin inventar métricas.

## Criterios de aceptación

- [ ] Filtros, orden y paginación funcionan contra la API y se prueban con resultados conocidos.
- [ ] Detalle conserva ID y fuente de SECOP, y permite volver al listado sin perder filtros.
- [ ] No quedan datos mock en la ruta de producción.
- [ ] Campos tienen etiquetas y controles usables con teclado; se comprueba pantalla estrecha.
- [ ] Solo usuarios autorizados modifican configuración compartida de filtros.

## Verificación

Pruebas de filtros/componentes y E2E listado→detalle→volver con capturas de escritorio/móvil.

## Fuera de alcance

Dashboard de métricas inventadas, extracción documental y recomendaciones IA.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa listado, filtros guardados y detalle usando exclusivamente la API existente. Usa estilo EAG y estados de carga/vacío/error. Prueba navegación, permisos y accesibilidad; evita añadir un dashboard fuera de alcance.
```
