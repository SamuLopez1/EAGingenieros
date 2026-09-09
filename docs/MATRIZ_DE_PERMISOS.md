# Matriz de permisos inicial

> Estado: contrato técnico de MVP-04. No confirma que EAG haya configurado
> Supabase, creado usuarios ni autorizado una matriz empresarial definitiva.

La única organización inicial prevista es `EAG`, con identificador técnico
`00000000-0000-0000-0000-000000000001` en la migración. Ese identificador no
representa un dato de negocio ni un usuario real.

| Acción | Anónimo | Analista | Administrador | Servidor con clave de servicio |
| --- | --- | --- | --- | --- |
| Consultar `/health` y OpenAPI | Sí | Sí | Sí | Sí |
| Consultar la sesión y su pertenencia a EAG | No, 401 | Solo la propia | Solo la propia | Solo para operación controlada |
| Consultar datos de otra organización | No | No, 403 | No, 403 | Solo en procedimientos de backend explícitos |
| Iniciar sesión con correo y contraseña | Solo ante Supabase, con cuenta previamente provisionada; sin registro público | Para su propia cuenta | Para su propia cuenta | No aplica |
| Crear, reenviar o revocar invitaciones | No | No, 403 | Sí, solo mediante API de backend | Sí, únicamente después de la autorización API y auditoría |
| Cambiar rol, organización o permisos propios | No | No | No | No directamente: solo flujo de backend revisado |
| Escribir membresías, perfiles, invitaciones o auditoría mediante cliente | No | No | No | Sí, con validaciones de backend |
| Leer membresías, invitaciones y auditoría | No | Solo su membresía | Solo la organización EAG | Solo operación controlada |

## Aplicación técnica

- FastAPI exige un bearer JWT validado con JWKS, firma `RS256` o `ES256`, expiración,
  issuer y audience. Un token ausente, vencido, con firma o claims inválidos
  devuelve 401; un token válido sin pertenencia o sin permiso devuelve 403.
- El backend resuelve organización y rol después de verificar el token. No usa
  claims de rol u organización enviados por navegador, URL o cuerpo de la
  petición.
- Los cuerpos de invitación rechazan campos adicionales: no aceptan `role` ni
  `organization_id`. La organización deriva de la pertenencia del administrador.
- La migración activa RLS y no define políticas de escritura para clientes
  autenticados. Perfiles, membresías, invitaciones y auditoría se cambian por
  backend; los controles de UI son solo una ayuda visual.
- La tabla de auditoría prevista registra acciones de invitación y membresía,
  actor, objetivo y organización. No debe incluir tokens, cabeceras
  `Authorization`, claves ni correos en `metadata`.

## Supabase y revocación: comprobaciones y pendientes

El 2026-09-06 se creó el proyecto dummy `eag-mvp-auth-dummy`, se aplicó la
migración inicial y se comprobó que su JWKS público usa `ES256`. Se desactivó
el registro público y se configuró la URL local autorizada. Una consulta de
metadatos confirmó RLS habilitado y una política en cada una de las tablas
`profiles`, `organization_memberships`, `invitations` y `audit_events`. No hay
datos de EAG, SMTP, claves locales, usuarios ni credenciales de prueba
autorizadas. La segunda migración de RPCs se aplicó sin filas de resultado; la
prueba E2E permanece pendiente.

La creación y revocación usan ahora una pasarela Supabase real cuando el backend
recibe su clave de servicio local. El reenvío no se simula: la API devuelve 501
porque Supabase no documenta una operación de reenvío de invitaciones. Esta es
una limitación que debe resolverse con EAG antes de cerrar la issue como completa.

La validación JWT local comprueba firma y expiración, pero no consulta Supabase
en cada solicitud para saber si una sesión se revocó. Por ello una revocación
en el proveedor **no se declara inmediata** para un access token ya emitido:
su alcance depende de su TTL, la política de refresh y el mecanismo de bloqueo
que EAG/Supabase aprueben. La revocación en esta API elimina primero la membresía,
por lo que su resolución de sesión y RLS rechazan el acceso inmediatamente; un
JWT ya emitido no queda criptográficamente inválido hasta su expiración. Antes
de producción se debe probar: eliminación de membresía, expiración/refresh,
cierre global de sesión, revocación de una invitación y trazabilidad de auditoría.
