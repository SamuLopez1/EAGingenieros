# ADR-005: La IA arranca desactivada

**Estado:** Aceptada
**Fecha:** 2026-09-24

## Contexto

HU-27 exige configurar el proveedor de IA y sus límites, y condiciona el envío
de documentos internos a «autorización empresarial específica». HU-41 añade que
`store=false` de un proveedor **no** equivale por sí solo a retención cero.

Activar la IA implica enviar texto de pliegos —y, en las fases siguientes,
documentos de la empresa con datos financieros y hojas de vida— a un servicio de
terceros. Es una decisión de negocio con consecuencias legales, no un detalle de
configuración.

## Decisión

**`EAG_AI_ENABLED=false` por defecto.** Activar la IA requiere una acción
explícita, y el sistema declara en cada momento si está activa y por qué no lo
está.

El modo de fallo se evita por diseño: arrancar con IA activada convertiría una
decisión de negocio en un efecto secundario de desplegar.

## Consecuencias

**A favor**

- **Ningún despliegue envía datos a un tercero por olvido.** El estado por
  defecto es el seguro.
- **El sistema es útil sin IA.** Las reglas deterministas comparan condiciones
  objetivas ([ADR-004](004-reglas-deterministas.md)) y la recuperación local
  busca evidencia en la base propia. Sin IA no se interpreta lenguaje natural,
  pero el flujo funciona y se puede probar entero.
- **El motivo de la indisponibilidad se declara.** «La IA no está disponible»
  tiene tres causas distintas —desactivada, sin clave, proveedor mal escrito— y
  el sistema devuelve cuál es en lugar de un booleano.

**En contra, y lo que se asume**

- **Un despliegue nuevo no analiza requisitos con IA hasta que alguien la
  active.** Es intencionado, pero significa que la demostración del flujo
  completo exige un paso de configuración consciente.
- **Sin presupuesto configurado no hay tope**, y se declara como tal en lugar de
  presentar un control que no existe. Cuando el tope se alcanza, las llamadas se
  **omiten** y quedan registradas como `omitida_por_presupuesto`: no se lanza una
  excepción hacia arriba ni se devuelve una respuesta vacía disfrazada de
  resultado. Así el análisis continúa por las vías que no cuestan dinero y nadie
  confunde un límite presupuestario con una avería.

## Medición y coste

Adoptado del proyecto `agentes-asobares`, que ya lo tiene en producción:

- **Una fila por llamada** en `ai_usage`, incluidas las fallidas: el proveedor
  cobra la entrada aunque la salida se trunque, así que no registrarlas dejaría
  el gasto real por debajo del calculado.
- **La medición nunca rompe el flujo.** No todos los proveedores devuelven `usage`
  con la misma forma; ante la duda se registra cero con `usage_reported=false`.
  Perder la medida de una llamada es un problema menor que perder el análisis.
- **Un modelo sin tarifa conocida deja el coste en NULL, nunca en cero.** Cero
  afirmaría que la llamada fue gratis; el gasto calculado es entonces una cota
  inferior, y eso se declara con `unpriced_calls`.
- **El tope se comprueba antes de gastar**, no después. Un límite que solo se
  revisa al terminar informa de un exceso que ya ocurrió.
- **La caché incluye modelo y versión de prompt** en su clave, así que cambiar de
  modelo la invalida por construcción en lugar de depender de que alguien se
  acuerde de purgarla. Solo se guardan respuestas **ya validadas**: una inválida
  en caché se reutilizaría indefinidamente como si fuera buena.
