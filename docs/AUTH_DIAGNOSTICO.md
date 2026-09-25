# Diagnóstico de autenticación MVP-04

Alcance: issue #4, rama `codex/mvp-04-auth-roles`, PR #19 hacia `dev`.
El login y logout reales de la cuenta analista dummy, y el login real de la
cuenta administradora dummy, se comprobaron el 2026-09-24. La revocación real
y la revisión humana siguen pendientes.

## Login real del analista y diagnóstico JWKS (2026-09-24)

Después de introducir las credenciales únicamente en la UI local, Supabase
creó una sesión, pero `/auth/session` devolvió 401 y la UI mostró un error de
autorización. El diagnóstico del backend identificó
`PyJWKClientConnectionError`: el proceso API local, iniciado sin acceso de red,
no podía descargar el JWKS público. Una petición `urllib` desde ese mismo
entorno falló con `URLError`; la consulta pública JWKS con acceso de red
respondió con una clave ES256. No se registraron JWT ni claves.

Se corrigió la clasificación del error: si falla la descarga de JWKS, la API
devuelve 503 y no confunde indisponibilidad del proveedor con token inválido
(401). Una prueba offline cubre esa distinción. Con la API local ejecutada con
acceso de red, el mismo JWT produjo HTTP 200 en `/auth/session` y la UI mostró
"Sesión autenticada" con rol `analista` asignado por el servidor. Una recarga
conservó la sesión. Se cerró sesión desde la UI y otra recarga mostró el
formulario anónimo. Son comprobaciones reales contra el proveedor dummy, sin
guardar ni mostrar contraseña o token.

Después, el usuario inició sesión con la cuenta administradora dummy en la
misma UI. Se observó "Sesión autenticada" y rol `administrador` devuelto por
el servidor; una recarga conservó la sesión. No se leyó ni guardó la contraseña
o el JWT. No se probó aún una revocación real de sesión o membership. Esa
comprobación y la revisión humana impiden cerrar la issue.

## Incidente de disponibilidad del dummy (2026-09-24)

El panel de Supabase mostró `eag-mvp-auth-dummy` en estado **paused**. Se usó
`Resume project` con autorización del usuario. El panel pasó por `Restoration in
progress` y `Coming up`, y confirmó `Restoration complete`. Durante el arranque
JWKS respondió HTTP 502; después respondió 200 y Auth health respondió 200 con
la clave publicable. El panel terminó mostrando `Healthy`. Una consulta agregada
en SQL Editor confirmó las dos
cuentas sintéticas con correo confirmado, perfil y rol esperado. En ese momento
esto aún no demostraba login/logout con contraseña ni revocación real; el
login/logout analista se comprobó posteriormente como se indica arriba.

Se descubrió además un defecto de permisos independiente de la pausa: con la
clave de servidor, Auth Admin devolvió 200 pero `GET` de `invitations` en
PostgREST devolvió HTTP 403 / SQLSTATE `42501`. `has_table_privilege` confirmó
que `service_role` carecía de `SELECT` en esa tabla. También faltaba `SELECT`
para `authenticated` en `invitations` y `audit_events`, aunque las políticas RLS
reservan su lectura a administradores. Con autorización se aplicó al dummy la
migración `20260924000000_service_invitation_read.sql`: SQL Editor informó
éxito, `service_role` leyó `invitations` por PostgREST con HTTP 200 y la consulta
de privilegios devolvió `true` para las tres lecturas previstas, `false` para
`anon` y `false` para escritura de `authenticated` en invitaciones. No se
concedió lectura de auditoría a `service_role`.

En transacciones con `SET LOCAL ROLE authenticated`, una comprobación con el
analista sintético confirmó perfil, pertenencia y organización propios, sin
visibilidad de auditoría ni invitaciones; otra con el administrador confirmó la
lectura de las dos pertenencias de EAG y de auditoría. Ambas terminaron con
`ROLLBACK` y sin cambios de datos. Son pruebas SQL/RLS reales, no login E2E.

Un proyecto pausado puede responder HTTP 540; la API debe fallar cerrada con 503
si su consulta de pertenencia recibe un error del proveedor. Hay una prueba
offline sintética para ese caso y otra para negar un JWT ya emitido después de
retirar la pertenencia simulada. Ninguna sustituye la revocación real de Supabase.

Para diagnosticar una interrupción futura: revisar primero el estado del proyecto
en el panel; después probar salud/JWKS, login y `/auth/session` en ese orden. No
interpretar un fallo de DNS, HTTP 502 o 540 como contraseña incorrecta. No usar
la API de negocio ni afirmar disponibilidad hasta verificar la sesión completa.

## Cambio a correo y contraseña (2026-09-08)

Hecho confirmado por el usuario: UI, API, proxy, JWT/JWKS y configuración local
están operativos. Supabase rechaza la solicitud de magic link antes de enviarlo.
No se conoce aquí un código de error adicional y no se inventa su causa.
**El flujo passwordless no está integrado ni funcionando.** Se sustituye su
solicitud en la UI para agilizar el entorno dummy; no es una validación de EAG.

El login usa únicamente `supabase.auth.signInWithPassword({ email, password })`.
No crea cuentas. La contraseña va solo al SDK de Supabase: el formulario la vacía
al enviar, no la guarda en estado React ni en atributos HTML, y no la incorpora
a errores o logs. El adaptador sanitiza errores devueltos y excepciones del SDK.
Los mensajes no confirman existencia de correo, invitación o membership.

Se mantiene esta secuencia: sesión Supabase → evento de Auth → `getSession()` →
JWT a `/auth/session` → rol de la API. El SDK no concede permisos de EAG por sí
solo. Persistencia, refresh, suscripción, limpieza al desmontar y rechazo de
respuestas tardías siguen activos. La detección del callback de invitación
administrativa sigue cubierta; no se solicita magic link desde la UI.

No se consultaron valores de `.env`, claves, JWT, cuentas ni datos de Supabase
para implementar este cambio. No se crearon ni modificaron cuentas o contraseñas.

## Provisionamiento y validaciones restantes

Un administrador autorizado debe provisionar el usuario dummy con contraseña,
correo confirmado, perfil y membership de EAG con rol administrador o analista.
Las credenciales se introducen únicamente en la UI local, nunca en Git, mensajes,
capturas o logs. El flujo login → rol devuelto por API → recarga con sesión
persistida → logout ya se probó con la cuenta analista dummy. El login y la
persistencia se comprobaron también con la cuenta administradora dummy. Falta
la revocación real; las pruebas offline descritas abajo no sustituyen ese paso.

La recuperación de contraseña queda pendiente y no se implementa. Se conservan
backend de invitaciones, revocación, auditoría, roles, RLS y migraciones. SMTP,
reenvío de invitaciones (501), validación de revocación/refresh con el proveedor
y revisión humana mantienen sus pendientes. No se fusiona el PR ni se cierra la
issue; la aceptación de EAG no se presume.

## Evidencia histórica conservada

- En la sesión del 2026-09-07, `App` solo consultaba una vez la sesión. Una prueba
  offline reprodujo que un evento posterior no provocaba una nueva consulta.
  Se añadió suscripción y protección ante respuestas tardías.
- Un valor vacío de `VITE_API_BASE_URL` enviaba `/auth/session` al servidor web.
  Se reprodujo offline y se corrigió el fallback a `/api/auth/session`.
- El SDK instalado espera `initializePromise` dentro de `getSession()`. Las
  pruebas sintéticas anteriores de hash no demostraron integración passwordless.
  No se reprodujo una carrera de inicialización del SDK.
- Las rutas locales no fueron accesibles en la primera sesión. Un smoke aislado
  sí pasó; posteriormente se confirmó UI/health directa y proxy 200 y sesión
  anónima directa/proxy 401 con los procesos configurados.
- El 2026-09-08 se comprobó en el panel dummy: Site URL y única Redirect URL
  `http://127.0.0.1:5173`; Email habilitado; registro público y acceso anónimo
  desactivados. Consulta agregada: un usuario Auth, un perfil y una membership
  de administrador de EAG; RLS habilitada. No se exportaron identidades.
- Bajo el rol SQL `authenticated`, perfil y membership fallaron con SQLSTATE
  `42501`, `permission denied for table profiles/organization_memberships`.
  Faltaba SELECT, aunque existían políticas RLS. El resolver convierte la
  denegación de PostgREST en 403.
- Se aplicó con autorización `20260908000000_auth_read_grants.sql`: SELECT sobre
  profiles, organization_memberships y organizations sujeto a RLS, sin escrituras
  ni grants a anon. La comprobación equivalente a
  `supabase/tests/auth_read_access.sql` pasó en PostgreSQL real: acceso propio
  permitido, sujeto ajeno y anon sin filas protegidas, sin cambio de membership.
  Esta evidencia SQL no sustituye un JWT real desde navegador.
- JWKS público accesible, una clave ES256, sin registrar material de clave ni kid.
- La revisión automática bloqueó un experimento de generación de magic link por
  requerir acceso interno a clave/correo contra la restricción del usuario. No se
  ejecutó. Ese experimento se abandona; no es un paso del nuevo login.
- Antes de este cambio, CI API/web estaba verde en `7d35844`; Git estaba limpio.
  La dependencia #3 seguía abierta, sin dar por concluida su aceptación.

## Pruebas offline y comandos

Las pruebas usan únicamente placeholders no válidos, cuentas de ejemplo y mocks.
Cubren credenciales correctas simuladas → sesión SDK → `/auth/session` → rol del
servidor (ignorando el rol del cliente), errores genéricos, sesión ausente,
401/403/503, logout, no registro público y ausencia de contraseña en peticiones
a la API propia, logs, errores, HTML serializado, health y OpenAPI. No se guardan
snapshots de credenciales. Se conservan las pruebas de JWT/firma/ES256, issuer,
audience, expiración, roles, escalada, aislamiento, CORS y secretos.

Desde la raíz, sin cargar el `.env` de `apps/api`:

```powershell
$env:PYTHONPATH = 'apps/api'
& apps/api/.venv/Scripts/python.exe -m ruff check apps/api
& apps/api/.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app
& apps/api/.venv/Scripts/python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests
python -m unittest discover -s tests -p 'test_*.py'
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
```

Para impedir que Vite/Vitest carguen `.env`, usar un wrapper recreable e ignorado:

```powershell
New-Item -ItemType Directory -Force apps/web/node_modules/.cache | Out-Null
Set-Content apps/web/node_modules/.cache/eag-verification.config.ts 'import config from "../../vite.config.ts"; export default { ...config, envDir: false };'
npm run test --prefix apps/web -- --config node_modules/.cache/eag-verification.config.ts
npm run build --prefix apps/web -- --config node_modules/.cache/eag-verification.config.ts
```

El smoke de este cambio usa procesos temporales en puertos 18000/15173, API con
cwd aislado y Vite con el wrapper sin `.env`. Comprueba health, OpenAPI, UI,
proxy y 401 anónimo. No contacta Supabase ni consume sesiones existentes.
Comando ejecutado: `python tmp/smoke_password_offline.py` (wrapper local ignorado).
Resultado: correcto. La primera creación del wrapper falló porque no existía
`tmp`; se creó esa carpeta y se repitió correctamente, sin leer `.env`.

Resultados finales: lint y typecheck web correctos; 22 pruebas web; ruff y mypy
correctos; 21 pruebas API; 11 pruebas spike; build correcto; smoke aislado correcto.
Persisten dos avisos de deprecación de Starlette/httpx/anyio, sin fallos.
No se ejecutaron pruebas de red contra Supabase durante este cambio.

## Conservación y limpieza

No se eliminan archivos. Se sustituye el método de login y sus pruebas/textos,
y se retira solo la variante magic-link de la prueba de callback, conservando la
invitación administrativa. Se retiran instrucciones operativas de diagnóstico
passwordless obsoletas, conservando arriba sus fallos y evidencia histórica.
No se borran spike, pruebas de autorización, migraciones, lockfiles, CI,
`.env.example`, `.gitignore` ni archivos de arquitectura. Los wrappers y salidas
locales son recreables y ya están ignorados; no se leen ni borran `.env`.

## Fuentes oficiales

- [signInWithPassword](https://supabase.com/docs/reference/javascript/auth-signinwithpassword)
- [Eventos de autenticación](https://supabase.com/docs/reference/javascript/auth-onauthstatechange)
- [Inicialización](https://supabase.com/docs/reference/javascript/auth-initialize)
- [Invitaciones administrativas](https://supabase.com/docs/reference/javascript/auth-admin-inviteuserbyemail)
