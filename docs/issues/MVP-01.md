# [MVP-01] Definir caso de uso mínimo y criterios de aceptación de EAG

## Objetivo

Convertir el alcance acordado en un caso comprobable, sin inventar validación empresarial.

## Dependencias

Ninguna.

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Redactar historia del analista desde una oportunidad hasta un borrador revisable.
- Documentar entradas, salidas, exclusiones y preguntas pendientes en docs/CASO_DE_USO.md.
- Definir protocolo de medición manual y automática sobre las mismas oportunidades.

## Criterios de aceptación

- [ ] Existe una historia con ejemplo sintético claramente identificado y escenarios de éxito, documentación incompleta y no cumplimiento.
- [ ] Se especifica qué documentos y campos necesita aportar EAG; la muestra real se guarda fuera de Git.
- [ ] Se distingue propuesta del equipo de decisiones aprobadas por EAG; los pendientes tienen responsable y siguiente acción.
- [ ] Los criterios incluyen trazabilidad, revisión humana y cómo medir tiempo/error; no se presenta el 60% como resultado probado.

## Verificación

Revisión documental de consistencia con CONTEXTO.md. La redacción puede entregarse en PR, pero la aceptación empresarial queda pendiente hasta recibir evidencia.

## Fuera de alcance

Código de producto, servicios de pago o supuesta aprobación de EAG.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Redacta el caso de uso mínimo del analista y los criterios verificables. Usa un ejemplo sintético, separa hechos de supuestos y prepara las preguntas mínimas para EAG. No programes ni des por confirmada la muestra real.
```
