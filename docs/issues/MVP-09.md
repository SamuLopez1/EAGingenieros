# [MVP-09] Registrar perfil y evidencias empresariales de EAG

## Objetivo

Proveer una fuente empresarial versionada para comparaciones posteriores.

## Dependencias

- MVP-04
- MVP-07

Las dependencias requieren su resultado técnico aceptado. En MVP-02 se puede avanzar con el borrador del caso y datos públicos mientras EAG valida la muestra; eso no sustituye la aceptación empresarial.

## Trabajo incluido

- Modelar experiencia, contratos/certificados, personal, equipos, datos financieros y legales con vigencias.
- Crear formularios y API con validación de campos y evidencias privadas.
- Registrar versión, fecha, autor, historial y estado pendiente/verificado según revisión humana.
- Documentar diferencia entre retención de perfil maestro y documentos de oportunidad.

## Criterios de aceptación

- [ ] Administrador gestiona perfil; analista accede según matriz acordada; pruebas validan permisos en backend.
- [ ] Datos numéricos/fechas se validan sin confundir desconocido con cero.
- [ ] Cada capacidad usada como evidencia tiene documento/localizador o se marca pendiente.
- [ ] Editar crea versión e historial sin modificar silenciosamente análisis anteriores.
- [ ] Se usan fixtures sintéticas; ningún dato real de EAG se siembra en Git.

## Verificación

En el menú de sesión, abre «Perfil empresarial». El catálogo sigue siendo la pantalla de
entrada. Un administrador puede añadir, editar, retirar registros de la nueva versión y
adjuntar evidencia. El analista puede consultar las versiones y descargar las evidencias
del perfil de su propia organización. Esta matriz técnica sigue el precedente de lectura
compartida y escritura administrativa. EAG debe confirmar ese acceso para uso operativo.

- El API publica `GET/PUT /api/v1/company-profile`, el historial en `/versions` y la carga
  y descarga autenticada en `/evidence`. Una edición conserva la versión anterior con fecha
  y autor. Un guardado basado en una versión desactualizada devuelve `409`.
- Adjunta PDF, DOCX o XLSX con antivirus disponible. Registra un localizador y marca
  «Verificado por revisión humana» tras contrastar la evidencia. La carga sola deja el
  registro pendiente. Para verificar disponibilidad se requieren cargo, dedicación y
  ambas fechas. El cero se conserva como valor explícito.
- Perfil y evidencia son registros maestros privados. Se conservan con sus versiones,
  independientemente de la retención del expediente. EAG debe definir la política de
  conservación y eliminación del maestro antes de producción.

Desde `apps/api` aplica `python -m alembic upgrade head` en la rama de perfil y ejecuta
`python -m pytest -q tests/test_profile.py`. Para PostgreSQL real desechable con Docker
e imagen local `postgres:17.6-bookworm`, ejecuta
`EAG_TEST_POSTGRES=1 python -m pytest -q tests/test_postgres_sync_integration.py -k profile`.
Las pruebas usan identidad, antivirus y documentos sintéticos.

MVP-08 y MVP-09 se desarrollan desde la revisión de #7 de forma independiente. Si se
integran ambas migraciones en paralelo, la rama de integración necesita una revisión
de unión de Alembic antes de aplicar `upgrade head`.

## Fuera de alcance

Asumir que documentos cargados certifican automáticamente capacidad o cumplimiento.

## Modelo sugerido para programar

GPT-5.6 Luna · Medium. Sugerencia, no cambio automático de configuración. Escalar solo ante dificultad demostrada. El modelo de IA del producto se elige aparte mediante evaluaciones.

## Prompt para empezar

```text
Lee AGENTS.md, docs/CONTEXTO.md y esta issue. Verifica dependencias y estado Git; trabaja en una rama exclusiva. Explica un plan breve y resuelve solo este alcance. Reutiliza pruebas existentes y lee únicamente archivos relevantes. Al terminar, informa cambios, comandos y resultados reales, riesgos y pendientes. Puedes hacer commit/push y abrir PR para revisión; no fusiones ni cierres la issue por el mero envío del PR.

Implementa perfil empresarial con evidencias, vigencias y versiones usando almacenamiento y permisos existentes. Usa datos sintéticos y distingue información pendiente de verificada. No desarrolles aún el comparador.
```
