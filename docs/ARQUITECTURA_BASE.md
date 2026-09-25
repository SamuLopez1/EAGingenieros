# Decisiones de estructura base

## Alcance de MVP-03

La estructura contiene una API FastAPI y una UI React/Vite mínimas para validar
configuración y comunicación local. No contiene autenticación, persistencia,
oportunidades, integración productiva SECOP, documentos, OCR, IA ni servicios
de pago.

El spike permanece en `scripts/secop_spike.py` y `docs/SECOP_SPIKE.md` como
evidencia. Sus resultados permiten considerar `p6dx-8zbt` para metadatos, pero
no autorizan una integración documental ni sustituyen la carga manual de
documentos complementarios.

## Contrato y cliente

FastAPI publica el contrato en `/openapi.json` y la interfaz en `/docs`. El
contrato `HealthResponse` vive en la API y se publica a través de OpenAPI.

La UI no declara una copia manual de ese tipo: mientras el contrato es mínimo,
verifica en tiempo de ejecución que la respuesta tiene los campos esperados. Al
añadir más endpoints, generar el cliente TypeScript desde `openapi.json` en una
issue posterior, por ejemplo con `openapi-typescript` o un generador equivalente
fijado con lockfile. El código generado debe ser la fuente de tipos del cliente;
no mantener tipos duplicados a mano.

## Configuración y seguridad

- La API usa `EAG_` como prefijo y expone en `/health` solo estado, versión y
  entorno; nunca devuelve configuración, credenciales ni tokens.
- CORS se habilita únicamente si `EAG_CORS_ALLOWED_ORIGINS` contiene orígenes
  explícitos. La ausencia de la variable no permite ningún origen.
- Vite usa `/api` y un proxy local para desarrollo. Una URL externa de API se
  define exclusivamente por `VITE_API_BASE_URL`; no se incluyen URLs privadas.
- Los ejemplos `.env.example` no contienen valores reales. Entornos virtuales,
  `node_modules`, salidas y archivos de trabajo siguen ignorados por Git.

## Autenticación, roles y aislamiento (MVP-04)

Supabase es el proveedor previsto. En el proyecto dummy de desarrollo
`eag-mvp-auth-dummy` se comprobó el JWKS público el 2026-09-06: expone una
clave `ES256`. La API valida JWT por JWKS configurables y acepta únicamente
firmas `RS256` o `ES256`, además de expiración, issuer, audience y `sub`, antes de resolver una
pertenencia. El rol y la organización no se toman de claims ni de datos del
cliente: se resuelven después de validar el token.

La organización inicial prevista es EAG, con roles `administrador` y
`analista`. La migración en `supabase/migrations/20260904000000_auth_roles_rls.sql`
crea perfiles, membresías, invitaciones, auditoría mínima y políticas RLS. La
 migración posterior `20260906000000_invitation_rpcs.sql` añade RPCs atómicas
 para registrar una invitación de analista y revocarla; se aplicó en el proyecto
 dummy el 2026-09-06 sin filas de resultado. No
concede escrituras a clientes autenticados; cualquier cambio de rol,
organización o invitación queda reservado a backend y debe registrarse.
Consulte la [matriz de permisos](MATRIZ_DE_PERMISOS.md).

La UI usa solo `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY`, que son
configuración publicable. La clave `EAG_SUPABASE_SERVICE_ROLE_KEY` se reserva
para el proceso backend y nunca debe tener prefijo `VITE_`, aparecer en OpenAPI
o registrarse. Sin configuración externa, la UI indica el pendiente y las rutas
de invitación responden de forma explícita sin enviar correos.

### Login y configuración del dummy

La UI usa exclusivamente `supabase.auth.signInWithPassword({ email, password })`
para cuentas ya provisionadas. La contraseña no pasa por FastAPI: solo el JWT
obtenido llega a `/auth/session`, que determina rol y organización. Se conserva
`onAuthStateChange`, se difiere la consulta fuera de su callback y se ignoran
respuestas de sesiones anteriores. Se conservan persistencia, refresh, cierre de
sesión y detección del callback de las invitaciones administrativas.

El formulario usa un campo `password` no controlado, lo vacía al enviar y no
copia su contenido a estado persistente, atributos HTML, errores o logs. El
adaptador sustituye tanto errores devueltos como excepciones del SDK por un
mensaje genérico, sin confirmar existencia de correo, invitación o membership.
La API no incorpora un endpoint que reciba credenciales.

El usuario confirma que UI, API, proxy, JWT/JWKS y configuración local están
operativos, y que Supabase rechaza el magic link antes de enviarlo. Se cambia el
acceso para agilizar el dummy; no se declara passwordless integrado ni validación
de EAG. No se consultaron `.env` ni datos de Supabase durante este cambio.

En comprobaciones previas se confirmaron registro público y acceso anónimo
desactivados, Email habilitado, y `http://127.0.0.1:5173` como Site/Redirect URL.
También se aplicó `20260908000000_auth_read_grants.sql`: otorga SELECT en perfil,
membership y organización a `authenticated`, sujeto a RLS. La prueba SQL real
mostró acceso propio permitido y acceso ajeno/anónimo bloqueado.

El dummy ya tiene cuentas sintéticas provisionadas con contraseña, correo
confirmado, perfil y membership de EAG. Se comprobaron login, recarga y logout
reales del analista, y login y recarga reales del administrador, sin registrar
credenciales. La revocación real y la recuperación de contraseña quedan
pendientes; no se añade registro, recuperación, OAuth ni MFA.
SMTP y el flujo administrativo de invitaciones conservan sus pendientes propios.

La creación de invitaciones reales usa `POST /auth/v1/invite` desde el backend
con la clave de servicio y registra perfil, membresía de `analista`, invitación
y auditoría mediante RPC. Una revocación primero elimina la membresía y después
el usuario de Auth; por tanto bloquea RLS y el backend antes de retirar tokens de
refresh. Los access tokens ya emitidos siguen siendo JWT válidos hasta `exp`,
aunque no pueden resolver una membresía en esta aplicación. Supabase no documenta
un reenvío de invitación seguro; la ruta devuelve 501 en vez de simularlo.
