# Base de conocimiento y recuperación (RAG)

> **Fases:** F9 y F10 · **HUs:** HU-49 a HU-58

## La regla que gobierna el módulo

**El sistema responde solo con fragmentos recuperados de los documentos de la
empresa, y cita documento, página y fragmento textual.** Sin fragmento que supere
el umbral de relevancia, responde que no hay evidencia en lugar de completar con
conocimiento general.

No es una preferencia de diseño. El producto decide si una empresa se presenta a
una licitación pública: un sistema que completa con conocimiento plausible cuando
no encuentra evidencia produce afirmaciones de capacidad empresarial que la
empresa no tiene. En contratación pública eso tiene consecuencias legales.

## Cómo se garantiza

En lugar de pedir al modelo que responda y comprobar después si alucinó, la
respuesta se construye **desde** los fragmentos:

1. **Se recupera evidencia.** Sin fragmentos sobre el umbral, no se llama al
   modelo. No se gasta una llamada para que improvise.
2. **Se pide al modelo que se limite** a los fragmentos entregados, numerados,
   citando el número que sustenta cada afirmación.
3. **Cada cita se verifica** contra los fragmentos realmente entregados. Una
   cita a un número que no se entregó se descarta: es la firma de una invención.
4. **Si ninguna afirmación queda sustentada, se degrada a «sin evidencia»**,
   aunque el modelo haya respondido algo.

El paso 3 es el que marca la diferencia. Sin él, el sistema podría citar un
documento plausible que nunca se recuperó, y la cita daría apariencia de rigor a
una invención.

## Verificación ejecutada

### Pruebas offline — 144 en total, 32 nuevas para el RAG

```bash
cd apps/api
python -m pytest        # 144 pasan, 1 omitida con motivo
python -m ruff check .
python -m mypy app
```

### Búsqueda vectorial contra PostgreSQL 17 real con pgvector 0.8.6

Se creó un índice con tres fragmentos y se consultó:

| Consulta | Resultado |
| --- | --- |
| «experiencia en interventoría» | Recupera el fragmento correcto, **score 1.000** |
| Fragmentos no relacionados | Descartados por el umbral |
| «certificaciones ISO de calidad» | **Sin evidencia**; respuesta degradada, 0 afirmaciones |

La última fila es la que importa: ante una consulta cuya respuesta no está en los
documentos, el sistema declara ausencia en lugar de inventar.

### El índice HNSW sí se usa

Comprobación con `EXPLAIN` sobre 5.200 fragmentos:

```
Limit
  ->  Index Scan using ix_chunk_embedding_hnsw on knowledge_chunks
        Order By: (embedding <=> ...)
```

**Con 200 filas el planificador usaba `Seq Scan`, y era correcto:** el índice
ocupaba 168 kB frente a los 24 kB de la tabla, así que recorrerla entera salía
más barato. No era un defecto de configuración sino una decisión de coste. A
partir de volumen realista el índice se usa. Conviene saberlo para no
malinterpretar un `EXPLAIN` durante el desarrollo.

## Defecto real encontrado y corregido

**Un texto de 3.600 caracteres producía un único fragmento de 3.701**, con el
tamaño objetivo configurado en 600. La causa: el bucle acumulaba líneas y solo
cortaba al superar el límite, pero un texto **sin saltos de línea** —frecuente en
extracciones de PDF— entra como una sola línea gigante y nunca dispara el corte.

El efecto habría sido silencioso y grave: la búsqueda devolvería el documento
entero como «fragmento», la cita perdería precisión y el coste de embeddings se
dispararía. Corregido y cubierto por pruebas: ahora 3.600 caracteres producen 7
fragmentos de ~600.

## Estructura de datos

| Tabla | Para qué |
| --- | --- |
| `knowledge_documents` | Material permanente de la empresa, versionado |
| `knowledge_chunks` | Fragmentos con localizador y vector |
| `rag_query_log` | Consultas, fragmentos usados y coste estimado |

### Decisiones que se reflejan en el esquema

- **El modelo de representación se guarda por fragmento** y la búsqueda filtra
  por él. Mezclar vectores de modelos distintos devuelve resultados sin sentido y
  **sin error visible**: la distancia entre espacios vectoriales diferentes no
  significa nada. Reindexar con otro modelo es una migración de datos, no un
  cambio de esquema.
- **Base de conocimiento separada del expediente de oportunidad.** Los
  documentos de empresa son permanentes; los de una oportunidad se purgan a los
  30 días. Mezclarlos borraría evidencia empresarial que debe durar, o dejaría
  que un certificado vencido siguiera sustentando cumplimientos.
- **Los documentos se versionan en lugar de sobrescribirse**, para que un
  análisis ya aprobado siga apuntando a la evidencia que usó.
- **Localizador obligatorio.** Un fragmento sin localizador resoluble es una
  afirmación que no se puede auditar.

## Protección frente a instrucciones embebidas

Un pliego o un contrato puede contener texto dirigido a un sistema automático
(«ignora las instrucciones anteriores»). El módulo lo detecta y lo **registra**,
pero no lo elimina: podría ser contenido legítimo y el analista debe verlo. El
prompt declara además que los fragmentos son datos, nunca instrucciones.

## Lo que no se ha verificado

- **Calidad de recuperación con documentos reales.** Las pruebas usan un
  generador de vectores determinista, no un modelo de representación real. El
  umbral de 0.35 es un punto de partida sin calibrar.
- **Elección del modelo de embeddings.** No se ha comparado ninguno sobre
  documentos del dominio.
- **Extracción de texto.** El RAG consume texto; producirlo es la fase F6 (OCR),
  todavía no implementada.
- **Coste real por consulta.** El registro existe, pero sin modelo conectado no
  hay medidas.
