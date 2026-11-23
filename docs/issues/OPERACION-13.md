# Operación de expedientes EAG

Procedimiento de la [issue #13](https://github.com/SamuLopez1/EAGingenieros/issues/13).
Aplica al esquema 20261122000011, sobre #12. Ensayar con datos sintéticos y en
un destino aislado. Registrar hora UTC, entorno, SHA, revisión de la base,
resultado y responsable de cada paso. Guardar solo códigos, conteos y
referencias de respaldo en la bitácora.

| Responsable propuesto | Acción y evidencia |
| --- | --- |
| Operación / DBA | Provisionar secretos, almacenamiento privado, planificación, alertas y backups. Ejecutar dry-run, purga, restauración y rollback. Registrar revisión, códigos de salida, conteos y tiempos medidos. |
| Seguridad / administración EAG | Aprobar aislamiento, crear dos cuentas sintéticas con sus roles, verificar superficie pública, controlar accesos a secretos, backups y registro de purgas. Revocar las cuentas al acabar el ensayo. |
| Comercial / responsable de datos EAG | Autorizar el expediente de prueba y validar que desaparece el derivado vencido y permanecen los maestros autorizados. Aprobar plazos de conservación. |
| Dirección EAG | Autorizar proveedores, gasto y salida a producción. |

## Qué expira

- Cada versión se vence 30 días después de su ingestión, desde su marca
  UTC del servidor. A la hora límite deja de poder descargarse y de aportar
  evidencia. Una recarga idéntica vigente conserva su plazo. La selección,
  extracción, comparación o aprobación tampoco renuevan el plazo.
- La purga elimina metadatos, bytes privados y OCR por cascada. El análisis
  determinista se calcula en la petición y el PDF se genera en el momento,
  sin archivos persistidos. Comparación, correcciones, aprobación y auditoría
  de envío vencen según su plazo registrado, que para una comparación con
  documentos toma la fecha más próxima. El PDF de una aprobación vencida deja
  de estar disponible. Los números de revisión purgados quedan reservados.
- Los temporales de OCR de un proceso terminado se limpian al cerrar el worker.
  La purga recoge temporales abandonados con marca propia tras una hora en el
  volumen configurado. Cada host de extracción necesita cobertura para su volumen.
- El catálogo público, los perfiles maestros versionados y sus evidencias
  quedan fuera de esta purga. Su plazo y accesos requieren política de EAG.
  El registro de purgas conserva tipo, referencias internas y hora sin títulos,
  correos, hashes de documentos ni textos. Se conservan sus referencias para
  evitar reutilizar números de revisión y se conserva una copia externa firmada
  para recuperación. Si se integran #23, #24 o #34, revisar sus derivados,
  añadir cobertura de retención y comprobar el historial de migraciones conjunto.
- Copias de PostgreSQL y WAL/PITR sobreviven a un borrado en la base. Operación
  debe cifrarlas, mantenerlas inaccesibles a la aplicación, acordar su plazo con
  EAG y confirmar la eliminación de copias vencidas en el proveedor. La purga
  tampoco retira PDFs que ya descargó un usuario. Seguridad valida su tratamiento.

## Purga y alertas

Configurar en el almacén de secretos del ejecutor **EAG_DATABASE_URL**,
**EAG_RETENTION_LEDGER_ID** (UUID distinto por entorno) y
**EAG_RETENTION_LEDGER_SECRET** (aleatorio, al menos 32 caracteres).
Guardar **LEDGER** como ruta absoluta a un archivo en un volumen privado
durable, separado de los backups de la base. El volumen debe admitir
reemplazo atómico y escritura durable. Restringir acceso al ejecutor y DBA.
Mantener una copia recuperable de su versión más reciente y de la clave,
con ACL y versionado independientes. Verificar la última versión contra la
bitácora de Operación antes de restaurar. La firma verifica integridad y
entorno, y la base detecta si faltan purgas ya conocidas. Un backup viejo no
puede detectar por sí solo que también se le dio un registro viejo.

Configurar **EAG_EXTRACTION_SCRATCH_ROOT** en worker y ejecutor a un directorio
privado, dedicado y existente. Dar acceso de escritura exclusivamente a esas
identidades. Conservar el mismo volumen al reiniciar el worker. Mantener
sincronización UTC de los hosts. Ejecutar desde apps/api, con la revisión
confirmada por Operación.

~~~bash
python -m alembic current
python -m app.operations.retention dry-run
python -m app.operations.retention purge --ledger "$LEDGER"
python -m app.operations.retention dry-run
~~~

Se propone una ejecución por hora en UTC, con un operador por ambiente. Repetir los lotes si quedan vencidos y monitorizar tiempo total.
El máximo por llamada es 250 documentos, 250 revisiones y 250 envíos.
Alertar si sale con error, falta una ejecución, quedan vencidos dos periodos
consecutivos, el archivo firmado se acerca a 8 MB o los contadores de
extracciones fallidas, reservas vencidas o correo pendiente de conciliación
se mantienen. Monitorizar el último estado de sincronización del catálogo y la
salud del worker. Evaluar el umbral y capacidad en staging con volumen esperado.
Registrar salida y contadores, sin volcados de tablas, cuerpos HTTP, cabeceras
de autorización ni trazas SQL con parámetros. Operación revisa la cola de
extracción y Comercial concilia envíos inciertos antes de reintentar.

Si falla tras guardar el registro y antes del commit, cerrar el acceso de
recuperación, confirmar el registro externo más reciente y ejecutar **replay**
antes de repetir **purge**. Un error o falta de registro durante recuperación
impide habilitar tráfico. Inicializar el registro solo en una base nueva y
confirmada sin purgas previas.

## Restauración y rollback

1. Operación aísla una **base nueva vacía**. La API, DNS, worker y correo del
   entorno activo siguen fuera de ese destino. Se usa el mismo major de
   PostgreSQL y un backup verificado del origen. Usar perfiles de conexión
   libpq privados, autenticación TLS y credenciales por gestor de secretos.
   Confirmar el destino de recuperación con psql antes de importar. **DUMP**
   apunta a un archivo privado cifrado en reposo.
2. Restaurar. Para un backup anterior a #13, migrar con la versión aprobada
   de la aplicación. El ejecutor usa EAG_DATABASE_URL de la base de
   recuperación, nunca del origen. Usar el registro de purgas vigente del
   origen con su UUID y clave. Reaplicar antes de conectar API y workers.
3. Volver a ejecutar **replay** y confirmar cero eliminaciones. Purgar lo que
   haya vencido desde el backup y repetir hasta cero. Verificar un informe
   eliminado con HTTP 409, que desaparecieron bytes y OCR, y que pueden
   consultarse un documento vigente y un maestro autorizado. Validar roles,
   control de caché y conteos con la muestra sintética. Solo entonces aprobar
   conexión al nuevo destino. Registrar duraciones medidas de la operación
   y pérdida de datos observada contra objetivos acordados con EAG.

~~~bash
pg_dump --dbname=service=eag-origen --format=custom --file="$DUMP"
psql service=eag-recuperacion -Atc 'SELECT current_database()'
pg_restore --dbname=service=eag-recuperacion --exit-on-error --no-owner "$DUMP"
python -m alembic current
python -m alembic upgrade 20261122000011
python -m app.operations.retention replay --ledger "$LEDGER"
python -m app.operations.retention replay --ledger "$LEDGER"
python -m app.operations.retention purge --ledger "$LEDGER"
python -m app.operations.retention dry-run
~~~

Para rollback, pausa escrituras, worker, programación de purga y entregas.
Conserva un backup y el registro externo vigente. Operación puede ensayar el
binario anterior **en el clon aislado** manteniendo el esquema ampliado.
La versión #12 ignora las marcas de revisiones purgadas, así que no se debe
servir informes ni permitir comparaciones o envíos desde esa versión tras
haber purgado. Mantén mantenimiento en esos flujos hasta volver a una versión
que respete las marcas. Los comandos de downgrade siguientes son para la
base de ensayo aislada, con registro externo conservado y una segunda persona
de Operación verificando destino y alcance.

~~~bash
python -m alembic downgrade 20261122000010
python -m alembic current
python -m alembic upgrade 20261122000011
python -m app.operations.retention replay --ledger "$LEDGER"
python -m app.operations.retention dry-run
~~~

Si la revisión o el registro fallan la validación, mantener el clon aislado.
Reanudar servicios y programación solo después de reaplicar y repetir el smoke.

## Acceso a staging

Seguridad provisiona el frontend, API y proyecto Auth de staging, separados
de producción. Usa dos cuentas de prueba distintas de la misma organización,
una **analista** y una **administradora**, con contraseña aleatoria entregada
mediante gestor de secretos. Crear y confirmar usuarios solo en el proyecto
de prueba. Asignar perfiles y membresías desde el operador del proyecto
siguiendo [la fixture de roles del dummy](../../supabase/tests/provision_dummy_password_users.sql)
como referencia, con los IDs autorizados de staging. Revocar después del
ensayo. Mantener desactivado el alta pública y limitar las URLs de retorno.
Esta prueba por contraseña no acredita envío ni aceptación de una invitación.

Configurar mediante el gestor de secretos **EAG_STAGING_API_URL**
(origen HTTPS), **EAG_STAGING_ANALYST_TOKEN** y **EAG_STAGING_ADMIN_TOKEN**
(JWT de usuario recientes). El comando solo hace GET, valida estados y emite
conteos por código HTTP sin cuerpo ni usuario. El informe aprobado opcional
debe ser sintético y pertenecer a esa organización.

~~~bash
python -m app.operations.staging_smoke
python -m app.operations.staging_smoke --opportunity "$OPPORTUNITY" --revision "$REVISION"
~~~

En la URL web, abrir modo privado, comprobar que pide autenticación,
iniciar sesión con cada rol, recargar y cerrar sesión. Verificar que analista
descarga el PDF aprobado y recibe 403 en la bandeja de administración.
Validar que anónimo recibe 401, y que ambas cuentas reciben 403 para otra
organización. Revisar desde el panel de despliegue que la clave privilegiada
está únicamente en el backend, sin imprimir valores, y que las rutas y hosts
de datos privados no están expuestos desde el navegador. Verificar en el
proyecto DB los grants de tablas privadas, RLS y que la URL del bucket, si
existe, no permite leer objetos sin autorización. Este esquema guarda el
expediente en PostgreSQL. Registrar códigos y hallazgos sin capturas que
incluyan claves, datos personales o el contenido del expediente.

## Ensayo reproducible y pendientes de salida

Desde apps/api con el entorno Python del repo y Docker con la imagen local
postgres:17.6-bookworm:

~~~powershell
python -m ruff check .
python -m mypy app
python -m pytest -o addopts='' -q
$env:EAG_TEST_POSTGRES = '1'
python -m pytest -o addopts='' -q -s tests/test_retention_postgres.py tests/test_postgres_sync_integration.py
Remove-Item Env:EAG_TEST_POSTGRES
~~~

Ruff y mypy completaron sin errores. La suite API offline aprobó 266 pruebas y
omitió 12 por opción de integración o disponibilidad de herramientas. Se
aprobaron 11 pruebas en PostgreSQL y 13 en la suite raíz con unittest.

| Criterio | Evidencia de laboratorio |
| --- | --- |
| Caducidad y purga | SQLite y reloj controlado a un microsegundo del plazo y al vencer. Descarga privada 200/410, PDF 200/409. Se eliminaron un expediente/OCR, dos revisiones y un envío sintético. Se preservaron el expediente B vigente, perfil, evidencia y catálogo. Una aprobación nueva recibe un número mayor y el enlace anterior devuelve 409. |
| Fallos y temporales | Una transacción malograda conserva el registro firmado y exige reaplicarlo. Se rechazaron firma y entorno incorrectos. El barrido retiró solo el temporal abandonado y marcado. |
| Recuperación y rollback | PostgreSQL real 17.6, CLI con dry-run/purge/replay, pg_dump y pg_restore previos a la purga en una base nueva. Las filas reaparecieron en la copia aislada y replay las eliminó. Downgrade .000011 a .000010, upgrade y doble replay sin resurrección. Roles anon y authenticated sin permisos sobre el registro, aun con grants predeterminados. No se usó SECOP, expedientes de EAG ni correo real. |
| Acceso | El smoke se ejecutó contra FastAPI ASGI con usuarios simulados. Confirmó 15 comprobaciones, incluyendo 401 sin sesión, 403 para otra organización o bandeja como analista y descarga privada 200 con sesión. Falta verificar la URL pública de staging, sus roles persistentes y la configuración del despliegue. |

También se ejecutó un ensayo separado con el Supabase dummy autorizado y la API
local. El probe previo confirmó el proyecto dummy. Se creó una cuenta analista
temporal mediante Auth Admin (200), se asignó la membresía (204), y el login
por contraseña respondió 200. La API local respondió 401 sin sesión, 200 con
la cuenta, 403 al intentar una acción administrativa y 403 para otra
organización. RLS devolvió una fila propia. Tras revocar, la API devolvió 403
con el mismo token, RLS devolvió cero filas, el refresh respondió 400 y
Auth Admin confirmó 404 para la cuenta retirada. El ensayo conservó solo
auditoría sintética de la fixture. La API no estaba desplegada en staging y
el ensayo real no incluyó un administrador nuevo. El rol administrador se
ejercitó en ASGI con la fixture offline.

Pendientes de revisión antes de habilitar expedientes de EAG:

- Operación y Seguridad deben confirmar URL y proyecto aislado de staging,
  instalar API/frontend, crear las dos cuentas en ese proyecto y ejecutar los smokes
  en ese destino. La consulta a GitHub solo devolvió el entorno copilot y
  cero despliegues del repositorio. El comando de staging salió con código 2
  al faltar el origen HTTPS y ambos JWT.
- EAG debe aprobar la política de maestros, auditoría y backups, los objetivos
  de recuperación, los costes de hosting/cron, PostgreSQL/PITR, almacenamiento,
  OCR, alertas y correo, y los responsables nominales.
- Si EAG autoriza un proveedor de IA, fijar tratamiento y retención
  contractuales, modelo y volumen, y acreditar el borrado fuera de EAG. El
  ensayo usa el adaptador offline y no acredita el tratamiento de terceros.
- Confirmar la integración y revisión humana de #12, incluida su validación
  con buzón autorizado. Completar la validación de staging con mínimos
  privilegios antes de liberar #13.
