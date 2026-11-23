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

## Expedientes privados

Aplicar `python -m alembic upgrade head` desde `apps/api`. El expediente se
abre dentro del detalle de la oportunidad. Administradores y analistas de EAG
pueden cargar, consultar y marcar versiones disponibles en revisión. Solo un
administrador puede volver a analizar archivos en cuarentena. Tanto los
metadatos como las descargas se autorizan por organización, oportunidad y
documento.

- PDF, DOCX y XLSX se validan por contenido, MIME y extensión. Los límites
  iniciales son 50 MiB por archivo y 300 MiB por expediente. Se pueden ajustar
  con `EAG_DOCUMENT_MAX_BYTES` y `EAG_DOSSIER_MAX_BYTES`.
- Los bytes se guardan en una tabla separada de PostgreSQL con RLS. Usar una
  conexión privada de backend como el rol propietario de la migración. Los
  clientes de Supabase carecen de permisos directos sobre las tablas.
- Configurar el host privado de clamd con `EAG_DOCUMENT_CLAMAV_HOST` y
  `EAG_DOCUMENT_CLAMAV_PORT`. La indisponibilidad deja el archivo en cuarentena.
  Ajustar `StreamMaxLength` del escáner al límite de archivo. Los documentos
  en ese estado quedan bloqueados para descarga y revisión.
- Configurar `EAG_DOCUMENT_DOWNLOAD_SECRET` con un secreto aleatorio de al
  menos 32 caracteres compartido por las instancias de backend. El enlace
  firmado dura 60 segundos y requiere la misma identidad autenticada y ruta. La firma viaja
  en el fragmento y la UI la envía como encabezado autenticado.
- En carga manual, reutilizar el tipo y el nombre del documento para agregar una
  versión. Repetir el último archivo idéntico conserva esa versión. La fecha
  de retención se calcula desde la carga y bloquea el acceso al vencer. La
  eliminación física y el tratamiento de copias se verifican en MVP-13.
- El aviso de pliego faltante se mantiene hasta que haya uno disponible.
  Las adendas se registran individualmente y la interfaz permite un expediente
  parcial.

### Asociaciones oficiales verificadas

`EAG_OFFICIAL_DOCUMENT_MANIFEST` apunta a un JSON privado configurado en el
servidor. Cada entrada incluye `id` UUID, `source_dataset` (`p6dx-8zbt`),
`source_id` exacto de la oportunidad en SECOP, `source_record_id` del
documento, `kind` (`pliego` o `adenda`), `title`, `filename`, `url` HTTPS
oficial, `verified_at` ISO 8601 con offset y `evidence` de la asociación.
El operador debe comprobar la correspondencia en la fuente oficial antes de
configurar una entrada. El cliente solo puede solicitar el UUID disponible
para la oportunidad. El backend comprueba dominio y dirección, fija la conexión
a la IP validada, revalida redirecciones y acota la descarga.

El spike de MVP-02 aún no acredita una relación general entre ambos datasets.
Con el manifiesto vacío, el catálogo ofrece la carga manual. La verificación
del modo oficial usa una asociación sintética.

### Verificación local

Ejecutar desde `apps/api` con las dependencias fijadas:

```powershell
python -m ruff check .
python -m mypy app
$env:EAG_TEST_POSTGRES = '1'
python -m pytest
Remove-Item Env:EAG_TEST_POSTGRES
```

Desde la raíz, con Vite, Chrome, Docker y la imagen local de PostgreSQL:

```powershell
python scripts/mvp06_preview.py --dossier --browser-cli $playwrightCli
```

`$playwrightCli` es la ruta de `playwright-cli.js`. El recorrido usa FastAPI,
Vite y PostgreSQL reales en loopback, con identidad y antivirus de fixture.
Carga un pliego en A, carga una adenda en B y vuelve a A para verificar su
listado y descargar el archivo exacto.

### Resultado

Ruff y mypy aprobaron. Pasaron 230 pruebas de API con PostgreSQL local habilitado,
44 pruebas web y 13 del spike. La migración de expediente revocó los permisos
directos de lectura de `anon` y `authenticated` y activó RLS en ambas tablas.

En Chrome se cargó un pliego sintético en A y una adenda sintética en B.
Al regresar a A solo apareció su pliego. El archivo descargado coincidió
byte por byte con lo cargado en A. Las pruebas de backend también rechazaron
descargas cruzadas, por otra organización o con una firma vencida.

Queda validar clamd con el servicio configurado por EAG y comprobar una
asociación oficial real antes de habilitar esa fuente en su entorno.

## Fuera de alcance

Enviar documentos a IA, hacer público el bucket o aceptar formatos sin validación.

## Modelo sugerido para programar

GPT-5.6 Terra · High. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa documentos privados con descarga acotada y carga manual. Incluye validación de archivo, cuarentena/antivirus, límites, SSRF y autorización. No proceses ni envíes a IA archivos no aprobados.
```
