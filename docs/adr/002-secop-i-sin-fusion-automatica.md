# ADR-002: Ingerir SECOP I y no fusionar duplicados entre plataformas

**Estado:** Aceptada
**Fecha:** 2026-09-23
**Sustituye a:** la conclusión de `docs/SECOP_COBERTURA.md`

## Contexto

El plan del MVP decidía **no** construir conector de SECOP I, con este
argumento (fase F3 y decisión B12):

> «12 de 12 procesos recientes de SECOP I ya están en SECOP II, así que
> sincronizar SECOP I no aporta oportunidades nuevas.»

Esa cifra decidía el alcance de una épica completa, así que se repitió la
medición con una muestra mayor antes de darla por buena. **No se reproduce.**
Detalle completo en [`../SECOP_COBERTURA_II.md`](../SECOP_COBERTURA_II.md).

| Medición | Solapamiento SECOP I → SECOP II |
| --- | --- |
| El documento original (12 referencias) | 100 % |
| 327 referencias, coincidencia por referencia | 22,6 % (cota superior) |
| 370 pares (NIT, referencia) | **0 %** |

La causa del 22,6 %: **`referencia_del_proceso` no es única en SECOP II.**
`001-2026` aparece **1139 veces**; son referencias genéricas que cada entidad
reutiliza. Los aciertos por referencia sola eran colisiones entre entidades
distintas, y desaparecen al exigir que coincida también el NIT.

## Decisión

**Dos decisiones, y la segunda importa tanto como la primera.**

1. **SECOP I se ingiere.** Aporta procesos recientes que no están en SECOP II.
2. **No se fusiona nada automáticamente.** El sistema agrupa solo cuando
   coinciden el NIT y la referencia normalizada, presenta el grupo como
   *posible* duplicado y deja la decisión al analista.

La segunda se sigue de la primera medición: si con la referencia sola se
fusionarían procesos sin relación y con (NIT, referencia) no se fusiona ninguno,
entonces **no existe una clave que garantice la equivalencia**. Fusionar en
silencio sería afirmar algo que la medición no respalda.

## Consecuencias

**A favor**

- El listado declara de qué plataforma viene cada fila, con la cobertura de cada
  una declarada con datos y no con una frase fija.
- El sistema nunca descarta una oportunidad por creerla duplicada de otra que no
  lo es. El error caro aquí es asimétrico: fusionar de más esconde una
  oportunidad real.

**En contra, y lo que se asume**

- **El analista puede ver el mismo proceso dos veces.** Es el precio de no
  fusionar sin evidencia. La marca de «posible duplicado» reduce el ruido, pero
  no lo elimina.
- **Los esquemas no son equivalentes y no se fuerzan.** `precio_base` (SECOP II)
  y `cuantia_proceso` (SECOP I) miden cosas distintas, así que cada uno conserva
  su etiqueta en la interfaz en lugar de compartir una columna «valor».
- **La medición necesita validación humana.** Contradice un documento previo del
  propio repositorio; el 0 % es de una muestra y no prueba que no existan
  procesos presentes en ambas con la referencia escrita de otra forma. Debe
  contrastarse con casos que alguien *sepa* que están en las dos plataformas.

## Nota sobre el documento sustituido

`SECOP_COBERTURA.md` se conserva con una corrección al inicio en lugar de
borrarse. Reescribirlo habría ocultado que la conclusión original existió y que
estuvo a punto de decidir el alcance del proyecto.
