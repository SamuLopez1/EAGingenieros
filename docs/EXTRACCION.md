# Extracción de texto y OCR

> **Fase:** F6 · **HUs:** HU-16 a HU-19

El texto que produce este módulo alimenta la fragmentación y el índice
vectorial. Un fallo aquí no se manifiesta como error: se manifiesta como un RAG
que responde «no hay evidencia» sobre documentos que sí la contienen. Por eso
los fallos se declaran explícitamente en lugar de devolver texto vacío.

## Formatos soportados

| Formato | Tratamiento |
| --- | --- |
| PDF | Texto digital por página; OCR en las páginas sin texto suficiente |
| DOCX | Párrafos y **tablas** (los pliegos tabulan requisitos) |
| XLSX | Una página por hoja, filas con separador de columna |

## Cuándo se activa el OCR

El criterio es la **densidad de texto por página**, no el tipo de archivo: un PDF
escaneado y uno digital son indistinguibles por extensión. Por debajo de 80
caracteres por página se considera que la página es una imagen.

Se comprueba **por página**, no solo por documento: un pliego puede tener anexos
escaneados entre páginas digitales, y promediar ocultaría justo esas páginas.

Cada página conserva si su texto vino de OCR y con qué confianza. El texto
reconocido tiene más errores que el digital, y el analista debe poder saberlo
antes de confiar en una cita. Por debajo de 0.6 de confianza se advierte que
conviene revisar la página.

## Verificación ejecutada

### 25 pruebas con documentos reales

Se generan PDF, DOCX y XLSX de verdad en memoria, no dobles de prueba. En este
módulo un mock no probaría nada: lo que puede fallar es precisamente la
interacción con el formato.

### OCR sobre un PDF escaneado real

Se construyó un PDF que contiene solo una imagen —sin capa de texto— y se
procesó:

| Comprobación | Resultado |
| --- | --- |
| ¿Se detecta como escaneado? | Sí |
| Motivo declarado | «el PDF no tiene capa de texto: es un documento escaneado» |
| Páginas procesadas con OCR | `[1]` |
| Texto reconocido | «PLIEGO DE CONDICIONES / Requisito experiencia minima de cincoanos» |
| ¿Utilizable para indexar? | Sí |

El reconocimiento comete errores propios del OCR («cincoanos» sin espacio). Es
esperable y por eso cada página lleva su marca de OCR y su confianza.

### Cadena completa contra PostgreSQL con pgvector

PDF → extracción → fragmentación → índice → consulta → respuesta citada:

| Paso | Resultado |
| --- | --- |
| Extracción | 2 páginas, utilizable |
| Fragmentación | 2 fragmentos con localizador `pág. 1` y `pág. 2` |
| Indexación | 2 fragmentos con vector |
| Consulta «experiencia en interventoría» | score **1.00**, cita `Pliego · pág. 1` |
| Respuesta con cita | Evidencia confirmada, 1 afirmación sustentada |

## Defecto real encontrado y corregido

Al ejecutar la cadena completa, el segundo fragmento empezaba así:

```
ONDICIONES. El proponente debe acreditar experiencia...
```

**Cortado a mitad de palabra.** La causa: el retroceso del solapamiento se hacía
por número de caracteres (`start = end - overlap`), sin respetar límites de
palabra.

El efecto no es cosmético: la representación vectorial de un fragmento que
empieza con `ONDICIONES` es peor, y la cita que ve el analista empieza con texto
mutilado. Corregido buscando el límite de palabra **hacia adelante** desde el
retroceso, nunca hacia atrás, para no solapar más de lo pedido. Cubierto por dos
pruebas de regresión.

Es el mismo tipo de defecto que el del fragmento de 3.600 caracteres: apareció
solo al ejecutar la cadena completa con datos reales, no en las pruebas
unitarias de cada pieza por separado.

## Imagen de contenedor

El `Dockerfile` instala `tesseract-ocr`, `tesseract-ocr-spa` y `poppler-utils`, y
**verifica en tiempo de construcción** que el idioma español está presente. Sin
ese paquete, el OCR de un pliego en español devolvería texto basura sin dar
error, que es peor que fallar de forma visible.

## Límites

- **OCR acotado a 50 páginas.** Reconocer cientos de páginas escaneadas puede
  tardar minutos; superarlo se declara en las advertencias.
- **Sin detección de tablas en PDF.** Se extrae el texto en orden de lectura, que
  no conserva la estructura de una tabla. En DOCX y XLSX sí se conserva.
- **Sin antivirus ni cuarentena.** Este módulo extrae; validar el archivo es la
  fase F5 (HU-13) y todavía no está implementada. **No debe exponerse a archivos
  no confiables hasta entonces.**
- **Calidad de OCR no medida.** Se verificó que reconoce texto, no con qué
  precisión sobre pliegos reales.
