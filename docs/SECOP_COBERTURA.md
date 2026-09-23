# ¿Se justifica sincronizar SECOP I? Medición con datos reales

> **Fecha:** 2026-09-18
> **Pregunta:** ¿aporta SECOP I oportunidades que no estén ya en SECOP II?
> **Conjuntos:** SECOP I `f789-7hwg` · SECOP II `p6dx-8zbt`

> ## ⚠️ CORRECCIÓN POSTERIOR — la conclusión de este documento no se reproduce
>
> Una medición con una muestra mayor (327 referencias de SECOP I de 2026 frente
> a 377 de SECOP II) **no confirma la cifra de 12 de 12**. Ver
> [`SECOP_COBERTURA_II.md`](SECOP_COBERTURA_II.md). Resumen:
>
> | Medición | Solapamiento SECOP I → SECOP II |
> | --- | --- |
> | Este documento (12 referencias) | 100 % |
> | Muestra de 327 referencias, solo referencia | 22,6 % (cota superior) |
> | Muestra de 370 pares, (NIT, referencia) | **0 %** |
>
> Además, `referencia_del_proceso` **no es única en SECOP II**: el valor
> `001-2026` aparece 1139 veces. Eso convierte la coincidencia por referencia
> en un generador de falsos positivos, y explica por qué la cifra alta de este
> documento no se sostiene.
>
> **La conclusión operativa se invierte:** SECOP I sí aporta procesos recientes
> que no están en SECOP II. El resto de este documento se conserva como
> registro del trabajo, pero no debe usarse para decidir el alcance.

## Conclusión

**No de forma significativa para el alcance del MVP.** Los procesos recientes de
SECOP I ya están en SECOP II. La épica E12 se reduce a un filtro de interfaz y
una decisión de arquitectura, no a una integración nueva.

## Medición

### Procesos recientes (2026) — lo que importa operativamente

| Comprobación | Resultado |
| --- | --- |
| Procesos de SECOP I en 2026 (muestra) | 100 filas, 95 referencias únicas |
| De 12 referencias, presentes en SECOP II | **12 de 12** |
| Solo en SECOP I | **0** |

### Procesos históricos (muestra con offset 500)

| Comprobación | Resultado |
| --- | --- |
| Rango de años de la muestra | 2018 a 2026 |
| De 15 referencias, presentes en SECOP II | **5 de 15** (33 %) |

Los procesos antiguos se solapan menos, pero son precisamente los que no
interesan: un proceso de 2019 no es una oportunidad a la que presentarse.

### Entidades

| Comprobación | Resultado |
| --- | --- |
| Entidades de SECOP II presentes en SECOP I | 10 de 12 (83 %) |
| NIT compartidos | Sí, formato idéntico de 9 dígitos |

El solapamiento de entidades es alto, lo cual es esperable: son las mismas
entidades estatales contratando. Pero compartir entidad no implica compartir
procesos.

## Un error de medición que corregí

La primera medición dio **2 coincidencias de 297 referencias** y sugirió que las
plataformas eran disjuntas. Era falso, y el error tiene una causa concreta que
conviene registrar porque ya apareció antes en este proyecto:

**`$order` sobre un campo con valores nulos sesga la muestra.** Ordenar por
`fecha_de_publicacion_del DESC` devuelve primero las filas sin fecha, y ordenar
por `nit_de_la_entidad DESC` devolvió 500 filas de **una sola entidad**. En
ambos casos la comparación de conjuntos se hizo sobre datos que no
representaban la población.

La medición fiable es la **consulta cruzada directa**: tomar identificadores de
una plataforma y preguntar a la otra si los tiene. No depende del orden ni de
que la muestra sea representativa.

## Diferencias de esquema que sí importan

Verificado sobre respuestas reales:

| | SECOP I | SECOP II |
| --- | --- | --- |
| Campos | 78 | 59 |
| Entidad | `nombre_entidad` | `entidad` |
| NIT | `nit_de_la_entidad` | `nit_entidad` |
| Proceso | `numero_de_proceso` | `referencia_del_proceso` |
| Estado | `estado_del_proceso` | `estado_del_procedimiento` |
| Fecha de carga | `fecha_de_cargue_en_el_secop` | `fecha_de_publicacion_del` |
| Valor | `cuantia_proceso` | `precio_base` |

**Los esquemas no son equivalentes.** Normalizar `nombre_entidad` a `entidad`
es una decisión defendible; asumir que `cuanto_proceso` y `precio_base` miden lo
mismo no lo es. El detalle debe mostrar solo los campos realmente disponibles en
cada plataforma.

## Recomendación

**No construir un conector de SECOP I en el MVP.** Lo que sí conviene:

1. **Preservar el origen por oportunidad** y mostrarlo en el listado. Si algún
   día se ingiere SECOP I, el modelo ya lo soporta sin migración.
2. **No afirmar cobertura de SECOP I** en la interfaz. Declarar solo lo que está
   efectivamente sincronizado.
3. **Reconsiderar E12**: sus 6 HUs bajan de prioridad. HU-59 (sincronizar
   SECOP I) pasa a P2 y solo tiene sentido si aparece evidencia de procesos
   recientes que no estén en SECOP II.
4. **Mantener HU-60 a HU-64** como contrato de arquitectura multi-fuente: son
   baratas de cumplir ahora (preservar origen, declarar cobertura) y caras de
   añadir después.

## Lo que esta medición no demuestra

- **Cobertura completa.** Las muestras son de cientos de filas sobre conjuntos
  mucho mayores. Que 12 de 12 procesos recientes estén en SECOP II no prueba que
  la cobertura sea del 100 %.
- **Que SECOP I no sirva para otra cosa.** Contiene campos que SECOP II no
  tiene —`nombre_del_represen_legal`, `plazo_de_ejec_del_contrato`,
  `valor_contrato_con_adiciones`— que podrían ser útiles para el perfil
  empresarial o el análisis de contratos históricos. Como fuente de
  *oportunidades* no aporta; como fuente de *contexto de contratación* podría.
- **Estabilidad temporal.** La relación entre plataformas puede cambiar si el
  Estado migra procesos entre ellas.
