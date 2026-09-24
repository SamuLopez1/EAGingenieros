# ADR-003: Aprobar congela una firma, no marca un estado

**Estado:** Aceptada
**Fecha:** 2026-09-24

## Contexto

HU-33 pide que un aprobador autorice «una versión concreta del análisis», y
HU-34 que la aprobación deje de habilitar el informe «cuando cambien entradas o
resultados». La decisión A4 del plan ya proponía congelar en lugar de invalidar,
pero sin concretar cómo.

El análisis del MVP se devolvía **en la respuesta HTTP y no se guardaba en
ninguna parte**. Sin persistencia, ni aprobar una versión ni bloquear un informe
eran posibles: no había nada que aprobar ni nada cuyo cambio detectar.

Hay dos formas de cumplir HU-34 y no son equivalentes:

- **Marcar y perseguir:** guardar «aprobado» en una fila y, en cada cambio
  posterior —documento, perfil, requisito, evidencia, decisión—, acordarse de
  bajar la marca.
- **Firmar y comparar:** guardar la firma de lo aprobado y, al preguntar si sigue
  vigente, recalcular la firma y compararla.

La primera depende de que el sistema detecte **todos** los cambios posibles. Cada
vía nueva de modificación es un olvido potencial, y el fallo es silencioso: un
informe emitido con evidencia que ya cambió.

## Decisión

**Aprobar congela una firma.** La aprobación guarda:

- la firma (`snapshot_signature`) de los documentos con su versión, la versión
  del perfil empresarial y las decisiones del análisis;
- el detalle legible de esa firma, para poder explicar al analista **qué** cambió.

La aprobación está vigente mientras la firma recalculada coincida. Un cambio
posterior no «invalida» nada retroactivamente: hace que la firma deje de
coincidir, y el informe se bloquea solo.

## Consecuencias

**A favor**

- **No hay que enumerar los cambios posibles.** Cualquier modificación que entre
  en la firma la rompe, incluidas las que se añadan en el futuro, sin tocar el
  código de invalidación.
- **La aprobación es reproducible.** Dos personas pueden recalcular la firma y
  llegar al mismo resultado, así que la vigencia es verificable y no una
  afirmación del sistema.
- **Se cumple A4 sin invalidar nada.** El histórico de aprobaciones no se
  modifica nunca, lo que encaja con la regla de que una decisión humana no se
  reescribe.

**En contra, y lo que se asume**

- **La firma hay que definirla con cuidado.** Si deja fuera algo que importa, un
  cambio real no la rompe y el informe se emite con evidencia vieja. Es el punto
  débil de esta opción y por eso el detalle de la firma se guarda: permite
  auditar qué se consideró parte de lo aprobado.
- **El mensaje al analista es más pobre que con invalidación explícita.** «La
  firma no coincide» no dice qué cambió por sí solo; hay que comparar el detalle
  guardado con el estado actual para explicarlo.
- **Aprobar no es decidir participar.** Se deja constancia explícita en el
  registro para que nadie lea la aprobación como una decisión de negocio.

## Lo que la salida automática nunca hace

La corrección humana de un requisito se guarda como **fila nueva** en
`analysis_reviews`, nunca modificando la propuesta del sistema. Si se
sobrescribiera, sería imposible medir en qué discrepa el sistema de la persona,
que es justo lo que el piloto necesita para decidir si la herramienta sirve
(HU-32, HU-42).
