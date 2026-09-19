# Validación y cuarentena de archivos

> **Fase:** F5 · **HUs:** HU-13, HU-12

Es la única barrera entre contenido no confiable y el resto del sistema. Sus
decisiones son deliberadamente conservadoras porque un archivo que pasa esta
puerta llega al extractor, al OCR y al modelo de lenguaje.

## La regla que gobierna el módulo

**Un fallo del antivirus no equivale a archivo limpio.**

Si el antivirus no responde, el archivo queda **sin analizar**, no aprobado.
Tratar la indisponibilidad como aprobación convierte una caída de
infraestructura en una vía de entrada sin protección. Es el error más común en
este tipo de control y el más difícil de detectar, porque no produce ningún
síntoma visible.

Hay dos modos, y la diferencia importa:

| Configuración | Antivirus caído | Resultado |
| --- | --- | --- |
| `EAG_REQUIRE_ANTIVIRUS=true` | Se rechaza el archivo | Recomendado si se reciben archivos de fuera |
| `EAG_REQUIRE_ANTIVIRUS=false` | Se acepta, **declarando** que no se analizó | Solo para entornos controlados |

En ambos casos el resultado lleva `scanned: false`, de modo que quien consume la
respuesta sabe si hubo análisis real.

## Comprobaciones, en orden de coste

1. **Nombre seguro** — se descarta cualquier componente de ruta.
2. **Tamaño** — acotado antes de leer nada.
3. **Firma peligrosa** — se miran los primeros bytes: `MZ` (PE), `ELF`, Mach-O,
   shebang, PHP, y el formato OLE que delata documentos con macros.
4. **Tipo real por contenido** — nunca por extensión ni por el MIME declarado:
   ambos los controla quien sube el archivo.
5. **Coherencia** entre lo declarado y lo real.
6. **Estructura interna** — en ZIP (DOCX y XLSX lo son): rutas que escapan,
   bombas de descompresión, macros y ejecutables anidados.
7. **Antivirus** — cuando está disponible.

Las comprobaciones baratas van primero: un ejecutable renombrado se rechaza sin
gastar un análisis de antivirus.

## Verificación ejecutada

### 39 pruebas con archivos reales

Se construyen PDF, DOCX, XLSX y ZIP reales, incluidos ZIP con rutas escapadas,
bombas de descompresión y documentos con `vbaProject.bin`. No se simulan las
comprobaciones: lo que puede fallar es la interacción con el formato.

### Antivirus real: ClamAV en contenedor

| Caso | Resultado |
| --- | --- |
| EICAR suelto | **Detectado**: `Eicar-Test-Signature` |
| DOCX con EICAR incrustado | **Detectado** (ClamAV descomprime el ZIP) |
| PDF legítimo | Limpio |
| Antivirus caído + `require_antivirus` | **Rechazado**: `antivirus_no_disponible` |
| Antivirus caído sin exigirlo | Aceptado con `scanned=false` y aviso |

## Hallazgo: ClamAV no analiza dentro de un PDF

Durante la verificación, un PDF que contenía la cadena EICAR **pasó el
análisis**. Se comprobó con la línea de comandos de ClamAV, fuera de este
código:

```
$ clamdscan /tmp/t.pdf
/tmp/t.pdf: OK
```

No es un defecto de la integración: **ClamAV no descomprime ni analiza el
contenido interno de un PDF por defecto.** El mismo contenido dentro de un DOCX
—que es un ZIP— sí se detecta, porque ClamAV descomprime los ZIP.

Consecuencia práctica: un PDF puede transportar contenido malicioso y pasar el
antivirus. Las defensas que quedan para ese caso son las otras capas —el tipo
real por contenido, los límites de tamaño y, sobre todo, que el PDF nunca se
ejecuta: se extrae su texto y se descarta—. Extraer texto de un PDF malicioso
sigue siendo un riesgo para el parser, y por eso conviene mantener actualizada
la librería de extracción.

## Lo que sigue sin cubrirse

- **Análisis de PDF en profundidad.** Sería necesario un motor específico o
  convertir el PDF a imágenes antes de procesarlo. No está implementado.
- **Sandbox de extracción.** El parser de PDF corre en el mismo proceso que la
  API. Un fallo de la librería afectaría al servicio completo; aislarlo en un
  proceso aparte con límites de memoria y tiempo es la mitigación natural.
- **Análisis de macros en profundidad.** Se detecta su presencia y se rechaza el
  documento, pero no se inspecciona qué hacen.
- **Lista de tipos ampliada.** Hoy son PDF, DOCX y XLSX. ZIP se rechaza como
  formato de subida aunque se inspeccione su estructura cuando aparece como
  DOCX o XLSX.
