# [MVP-07] Incorporar descarga y carga manual seguras de documentos

## Objetivo

Reunir archivos utilizables sin abrir acceso público ni asumir expedientes completos.

## Dependencias

- MVP-05
- MVP-06

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Implementar descarga según evidencia del spike y carga manual de respaldo por oportunidad.
- Aplicar lista de tipos, firma/MIME, tamaño, antivirus/cuarentena y nombres seguros; bloquear macros/ejecutables.
- Almacenar de forma privada con URLs firmadas breves y autorización por recurso.
- Mantener hash, versión, origen, estado, faltantes y fecha de retención por archivo.

## Criterios de aceptación

- [ ] Se puede cargar un documento cuando la descarga oficial falta; el expediente puede quedar incompleto.
- [ ] Límites propuestos 50 MB/archivo y 300 MB/oportunidad son configurables y probados.
- [ ] Bloquea SSRF en URL y redirecciones, path traversal, tipo simulado y archivos rechazados por antivirus; ZIP se rechaza si no se implementan límites seguros.
- [ ] No se procesa archivo en cuarentena; fallo del escáner no se interpreta como archivo limpio.
- [ ] Hay pruebas de permisos de lectura/descarga y de rechazo seguro; no se registra contenido sensible.

## Verificación

Fixtures sintéticas de archivo válido, inválido, exceso de tamaño, redirección insegura y antivirus no disponible.

## Fuera de alcance

Enviar documentos a IA, hacer público el bucket o aceptar formatos sin validación.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa documentos privados con descarga acotada y carga manual. Incluye validación de archivo, cuarentena/antivirus, límites, SSRF y autorización. No proceses ni envíes a IA archivos no aprobados.
```
