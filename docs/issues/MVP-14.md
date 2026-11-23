# [MVP-14] Ejecutar una evaluación académica del MVP

## Objetivo

Validar utilidad y riesgos con usuarios antes de dar por terminado el MVP.

## Dependencias

- MVP-13
- #23 y #24 para validar encaje, disponibilidad y margen en el piloto
  completo. Se pueden ensayar antes los tramos disponibles.

Usar una empresa ficticia, cuentas de prueba y documentos públicos o sintéticos identificados.

## Trabajo incluido

- Preparar al menos dos oportunidades con revisión manual y declarar la fuente y las limitaciones.
- Medir tiempos del flujo manual y asistido con mismo alcance y registrar errores por campo/falsos cumplimientos.
- Ejecutar UAT con analista/administrador, registrar incidencias, capacitación y manual breve.
- Validar con Comercial, Talento Humano y Finanzas el encaje, la
  disponibilidad y los supuestos de costos y margen.
- Entregar decisión go/no-go, pendientes y plan de seguimiento validado por responsables.

## Criterios de aceptación

- [ ] Hay protocolo y evidencia real diferenciados; no se simulan resultados ni aprobación del usuario.
- [ ] Comparación de tiempos incluye revisión/correcciones y comunica tamaño de muestra y limitaciones.
- [ ] Se acuerdan umbrales de aceptación antes de evaluar; 60% no se trata como garantía.
- [ ] Incidencias críticas de seguridad o falsos cumplimientos no resueltos bloquean lanzamiento.
- [ ] Se registra la decisión académica del equipo, el resultado y el checklist de ejecución.
- [ ] El piloto completo documenta las validaciones y pendientes de
  Comercial, Talento Humano y Finanzas.

## Verificación

El [guion del piloto](PILOTO-14.md) contiene las pruebas de aceptación y la
[bitácora y acta](PILOTO-14-BITACORA.md) registra tiempos, correcciones y
decisiones. Ejecutar el recorrido con muestra y participantes autorizados.
Registrar las mediciones y la evaluación humana al completar la sesión.

## Fuera de alcance

Inventar datos del piloto o lanzar por completar el calendario.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Prepara y ejecuta el piloto solo con datos y usuarios autorizados. Compara contra revisión manual, mide errores y tiempo total y entrega go/no-go con evidencia. Si faltan datos, deja listo el protocolo y no inventes resultados ni cierres la issue.
```
