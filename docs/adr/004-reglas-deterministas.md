# ADR-004: Condiciones objetivas por aritmética, no por relevancia

**Estado:** Aceptada
**Fecha:** 2026-09-24

## Contexto

El grafo de análisis decidía el estado de un requisito con una sola señal: la
puntuación de relevancia de la evidencia recuperada. Si un fragmento de la
empresa superaba el umbral, el estado propuesto era `cumple`.

Eso funciona para condiciones interpretables —«capacidad técnica acreditada»—,
pero **falla en las objetivas**. Ante el requisito:

> «El proponente debe acreditar mínimo cinco (5) años de experiencia»

un fragmento que hablara de experiencia con buena puntuación producía `cumple`
**aunque la empresa tuviera tres años**. Los números no se comparaban nunca: el
sistema no leía el «cinco» ni sabía cuántos años tenía la empresa.

Es un **falso cumplimiento**, y es el error más caro que este sistema puede
cometer: el analista lo llevaría al informe y la empresa se presentaría a una
licitación que no cumple. HU-42 lo trata como bloqueante del lanzamiento.

El defecto estaba oculto por las pruebas: el requisito de ejemplo contenía «cinco
años», que es una condición objetiva, y el test comprobaba el camino semántico.
Al introducir las reglas, esas pruebas empezaron a fallar y señalaron el problema.

## Decisión

**Las condiciones objetivas se comparan con aritmética y la recuperación
semántica no interviene.** Un módulo de reglas (`app/analysis/rules.py`) extrae
del texto años, cantidades, plazos y valores indexados, y los compara con los
valores conocidos de la empresa.

Tres desenlaces, y la distinción entre ellos es el punto:

| Situación | Estado | Por qué |
| --- | --- | --- |
| El dato de la empresa no consta | `revision_manual` | «No consta» no es «no alcanza» |
| El dato consta y satisface | `cumple` | Aritmética verificable |
| El dato consta y no satisface | `no_cumple` | Incumplimiento **demostrado** |

**Cuando hay condiciones objetivas y falta el dato, no se cae a la comparación
semántica.** Dejarlo hacerlo reintroduciría el defecto por la puerta de atrás: un
fragmento sobre «experiencia» volvería a proponer un cumplimiento sin saber
cuántos años tiene la empresa.

## Consecuencias

**A favor**

- **El falso cumplimiento desaparece** en todo lo que sea comparable por
  números, que en un pliego es la mayor parte de los requisitos habilitantes.
- **`no_cumple` empieza a significar algo.** Antes solo podía venir de una
  persona. Ahora el sistema puede demostrar un incumplimiento, y lo hace con los
  dos valores a la vista.
- **Cada cálculo es auditable.** Se guardan entradas, regla, resultado y motivo
  (HU-29), así que el veredicto se puede reproducir y discutir.

**En contra, y lo que se asume**

- **La extracción es conservadora y a veces no reconoce una condición.** Si no
  identifica con seguridad el número y su unidad, no inventa nada y el requisito
  cae a la vía semántica. Es deliberado: una condición inventada produciría un
  veredicto seguro sobre una lectura falsa del requisito.
- **El resultado depende de que el perfil empresarial tenga los datos cargados.**
  Sin años registrados, un requisito de experiencia queda en revisión manual. No
  es una limitación del sistema sino del dato, y así se declara.
- **«Cumple parcialmente» no se asigna automáticamente.** HU-31 lo condiciona a
  que exista un criterio validado de divisibilidad, que todavía no existe.

## Regla transversal que se respeta

    Dato desconocido → revisión manual. Nunca incumplimiento.

Confundir «no consta el patrimonio» con «el patrimonio no alcanza» rechazaría
oportunidades válidas, que es tan grave como aceptar una inválida.
