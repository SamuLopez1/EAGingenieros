# Registros de decisión de arquitectura (ADR)

Cada archivo documenta una decisión que **no es obvia leyendo el código**: qué se
decidió, con qué evidencia y qué se acepta a cambio. El código dice qué hace el
sistema; estos registros dicen por qué hace eso y no otra cosa, que es lo que se
pierde cuando alguien nuevo —o el mismo equipo seis meses después— revisa el
repositorio.

Formato tomado del proyecto `agentes-asobares`, que ya lo usa en producción.
Cada registro lleva estado, fecha, contexto, decisión y consecuencias.

| # | Decisión | Estado |
| --- | --- | --- |
| [001](001-base-de-datos-propia.md) | Base de datos propia, sin Supabase | Aceptada |
| [002](002-secop-i-sin-fusion-automatica.md) | Ingerir SECOP I y no fusionar duplicados | Aceptada |
| [003](003-aprobacion-por-snapshot.md) | Aprobar congela una firma, no marca un estado | Aceptada |
| [004](004-reglas-deterministas.md) | Condiciones objetivas por aritmética, no por relevancia | Aceptada |
| [005](005-ia-desactivada-por-defecto.md) | La IA arranca desactivada | Aceptada |
| [006](006-tokens-en-sessionstorage.md) | Tokens de sesión en `sessionStorage` | Aceptada, con pendiente |

## Añadir un registro

Numeración correlativa, nombre en minúsculas con guiones, y el estado como uno
de: **Propuesta**, **Aceptada**, **Rechazada**, **Sustituida por NNN**. Un
registro aceptado no se edita para cambiar la decisión: se escribe uno nuevo que
la sustituye y se marca el anterior. Reescribir el pasado impide entender por qué
el sistema llegó a donde está.
