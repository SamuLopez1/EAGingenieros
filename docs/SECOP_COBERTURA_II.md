# Cobertura real de SECOP I frente a SECOP II · Segunda medición

> **Fecha:** 2026-09-23
> **Conjuntos:** SECOP I `f789-7hwg` · SECOP II `p6dx-8zbt`
> **Sustituye a:** [`SECOP_COBERTURA.md`](SECOP_COBERTURA.md), cuya cifra de
> 12 de 12 no se reproduce.

## Por qué hay una segunda medición

`SECOP_COBERTURA.md` concluyó que SECOP I no aportaba oportunidades nuevas,
con una muestra de 12 referencias: 12 de 12 ya estaban en SECOP II. Esa
conclusión decidía el alcance del MVP —no construir conector de SECOP I—, así
que se repitió la medición con una muestra mayor antes de darla por buena.

**No se reproduce.** Con 327 referencias el solapamiento es de 22,6 % como
mucho, y con la clave estricta es del 0 %. La conclusión operativa se invierte:
SECOP I sí aporta procesos recientes que no están en SECOP II.

## Esquemas reales

Leídos de `https://www.datos.gov.co/api/views/<dataset>.json`, no de la
documentación.

| | SECOP I `f789-7hwg` | SECOP II `p6dx-8zbt` |
| --- | --- | --- |
| Columnas | **79** | **59** |
| Identificador | `uid` | `id_del_proceso` |
| Referencia | `numero_de_proceso` | `referencia_del_proceso` |
| Entidad | `nombre_entidad` | `entidad` |
| NIT | `nit_de_la_entidad` | `nit_entidad` |
| Estado | `estado_del_proceso` | `estado_del_procedimiento` |
| Fecha | `fecha_de_cargue_en_el_secop` | `fecha_de_publicacion_del` |
| Valor | `cuantia_proceso` | `precio_base` |

El documento anterior decía 78 columnas en SECOP I. Son 79. La diferencia es
menor, pero indica que la cifra se tomó de una fuente secundaria y no del
conjunto.

## Medición 1 · Solapamiento por referencia

Muestra: 400 filas de SECOP I de 2026 (`anno_cargue_secop=2026`, orden
`uid DESC`), que dan 327 referencias únicas. Se pregunta a SECOP II por ellas
en un `$where ... IN (...)`, que es la consulta cruzada directa que el documento
anterior recomendaba.

| Comprobación | Resultado |
| --- | --- |
| Referencias de SECOP I consultadas | 327 |
| Presentes en SECOP II por referencia exacta | **74 (22,6 %)** |
| Solo en SECOP I | **253** |

Dirección inversa: 377 referencias de SECOP II, 89 presentes en SECOP I
(23,6 %).

### El 22,6 % es una cota superior, no un resultado

Al inspeccionar las coincidencias apareció el problema: **`referencia_del_proceso`
no es única en SECOP II.**

| Referencia | Filas en SECOP II |
| --- | --- |
| `001-2026` | **1139** |
| `017-2026` | 405 |
| `018-2026` | 393 |
| `SASI-001-2026` | 128 |

Son referencias genéricas que cada entidad reutiliza. Coincidir por referencia
sola no demuestra que sea el mismo proceso: puede ser el proceso `001` de 2026
de dos alcaldías distintas. Por eso el 22,6 % está inflado por falsos positivos
y el solapamiento real es menor.

## Medición 2 · Solapamiento con clave estricta (NIT, referencia)

Se exige además que coincida el NIT de la entidad, que sí es estable entre
plataformas (mismo formato de dígitos).

| Comprobación | Resultado |
| --- | --- |
| Pares (NIT, referencia) de SECOP I | 370 |
| Presentes en SECOP II con esa clave | **0** |
| Cobertura | **0,0 %** |

Los 74 aciertos por referencia sola **desaparecen** al añadir el NIT. Es decir:
eran coincidencias entre entidades distintas, no el mismo proceso.

### Unicidad de (NIT, referencia) en SECOP II

Sobre 3000 filas recientes: 2925 pares distintos, **39 pares que aún se repiten**
(hasta 20 filas para `891800498 · SASIGB0322025(PRESENTACIÓNDEOFERTA)`).

La pareja reduce la ambigüedad, no la elimina.

## Conclusión

**No existe una clave que permita fusionar automáticamente el mismo proceso
entre las dos plataformas.** Con la referencia sola se fusionarían procesos sin
relación; con (NIT, referencia) no se fusiona ninguno, ni siquiera los que sí lo
son, porque el formato de la referencia difiere entre plataformas.

Eso decide dos cosas en el código:

1. **SECOP I se ingiere.** Aporta procesos recientes que no están en SECOP II.
2. **No se fusiona nada automáticamente.** El sistema agrupa solo cuando
   coinciden NIT y referencia normalizada, presenta el grupo como *posible*
   duplicado y deja la decisión al analista. Fusionar en silencio afirmaría una
   equivalencia que esta medición no respalda.

Ver `apps/api/app/secop/sources.py`, función `grouping_key`, donde está la
misma justificación junto al código.

## Lo que esta medición NO demuestra

- **Cobertura completa de SECOP I.** Se muestrearon 400 filas de un conjunto
  mucho mayor, y solo de 2026.
- **Que el solapamiento sea 0 en todos los casos.** El 0 % es de esta muestra.
  Que no se encuentre la equivalencia no prueba que no exista: puede haber
  procesos presentes en ambas con la referencia escrita de otra forma.
- **Estabilidad temporal.** El Estado puede migrar procesos entre plataformas.
- **Que SECOP I sirva como fuente de contexto.** Tiene campos que SECOP II no
  publica —`valor_contrato_con_adiciones`, `nombre_del_represen_legal`,
  `plazo_de_ejec_del_contrato`— que podrían alimentar el perfil empresarial.
  Eso no se ha evaluado.

## Reproducir

Los scripts están versionados en `scripts/`:

```bash
python scripts/secop_cruce_referencia.py   # cruce por referencia, 12 filas
python scripts/secop_medir_cobertura.py    # 327 y 377 referencias, ambas direcciones
python scripts/secop_medir_clave.py        # unicidad y cruce con (NIT, referencia)
```

Hacen red contra `www.datos.gov.co`. Son de ejecución explícita, no forman parte
de la suite de pruebas: una prueba que dependa de que un servicio público
responda falla por motivos que no tienen que ver con el código.
