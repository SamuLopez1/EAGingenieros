# [MVP-14] Ejecutar piloto con EAG, medir resultados y decidir lanzamiento

## Objetivo

Validar utilidad y riesgos con usuarios antes de dar por terminado el MVP.

## Dependencias

- MVP-13

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Preparar al menos 20 oportunidades revisadas manualmente si EAG autoriza y aporta muestra; justificar limitaciones.
- Medir tiempos del flujo manual y asistido con mismo alcance y registrar errores por campo/falsos cumplimientos.
- Ejecutar UAT con analista/administrador, registrar incidencias, capacitación y manual breve.
- Entregar decisión go/no-go, pendientes y plan de seguimiento validado por responsables.

## Criterios de aceptación

- [ ] Hay protocolo y evidencia real diferenciados; no se simulan resultados ni aprobación del usuario.
- [ ] Comparación de tiempos incluye revisión/correcciones y comunica tamaño de muestra y limitaciones.
- [ ] Se acuerdan umbrales de aceptación antes de evaluar; 60% no se trata como garantía.
- [ ] Incidencias críticas de seguridad o falsos cumplimientos no resueltos bloquean lanzamiento.
- [ ] Se registra aceptación o rechazo por EAG; manual y checklist de puesta en marcha están listos.

## Verificación

Recorrido extremo a extremo con muestra autorizada, métricas reproducibles y acta UAT. Sin usuarios/datos se entrega protocolo pero issue queda pendiente.

## Fuera de alcance

Inventar datos del piloto o lanzar por completar el calendario.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Prepara y ejecuta el piloto solo con datos y usuarios autorizados. Compara contra revisión manual, mide errores y tiempo total y entrega go/no-go con evidencia. Si faltan datos, deja listo el protocolo y no inventes resultados ni cierres la issue.
```
