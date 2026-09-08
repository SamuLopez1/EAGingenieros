# Diagnóstico de autenticación MVP-04 (2026-09-07, America/Bogota)

Alcance: issue #4, rama `codex/mvp-04-auth-roles`, PR #19 hacia `dev`.
No se considera resuelto el login real ni se cierran los criterios E2E.

## Evidencia y arreglo mínimo

- Estado inicial Git limpio. Issue #4 abierta; PR #19 abierto hacia `dev`.
  CI previo: trabajos `api` y `web` correctos.
  La dependencia #3 sigue abierta en GitHub; su aceptación no se da por concluida.
- `App` consultaba la sesión una sola vez. Una prueba offline falló porque un
  evento posterior no provocaba una segunda consulta. Ahora escucha los cambios
  de Auth, difiere la consulta fuera del callback y descarta respuestas anteriores
  a un cambio de sesión. Cancela temporizador y suscripción al desmontar.
- Con `VITE_API_BASE_URL` vacío se solicitaba `/auth/session` al servidor web:
  reproducción offline con ruta esperada `/api/auth/session` y ruta obtenida
  `/auth/session`. Ahora los valores vacíos usan el proxy local.
- Los errores HTTP 401, 403 y 503 se distinguían únicamente en Network. La UI ahora
  muestra mensajes locales por estado y permite cerrar la sesión desde el error.
  No muestra cuerpos de respuesta, errores de Supabase, JWT ni datos personales.
- En `@supabase/auth-js` instalado, `getSession()` espera `initializePromise`.
  Pruebas con el SDK real, hash sintético y HTTP simulado verifican que invitación
  y magic link se consumen antes de resolver la sesión y se guardan en storage.
  No se reprodujo una carrera de inicialización del SDK. Son pruebas offline,
  **no integración con Supabase**.

## Flujo y comprobaciones externas pendientes

1. **Redirección:** la documentación previa registra Site URL y Redirect URL
   `http://127.0.0.1:5173`. No se revalidó el panel Supabase en esta sesión.
   Comprobar allí el origen y ruta exactos del callback y del redirect de invitación.
   `localhost` y `127.0.0.1`, puertos y perfiles de navegador tienen almacenamiento
   diferente aunque se use el mismo computador. No copiar el enlace completo.
2. **Invitación / magic link:** el backend invita mediante `/auth/v1/invite` y
   después ejecuta `record_eag_invitation` para perfil y membership de analista.
   Invitar directamente desde el panel Auth no ejecuta esa RPC. La UI solicita
   magic links para usuarios existentes con `shouldCreateUser: false`; esto no
   asigna roles ni membership. Revisar si el dummy fue provisionado por el panel
   o por el backend; su ausencia de membership es una hipótesis, no un hallazgo.
3. **Callback / sesión:** el cliente actual usa el flujo implicit predeterminado,
   con detección de URL, persistencia y refresh habilitados. No cambiar a PKCE
   como solución genérica: el backend de invitaciones actual no inicia un
   desafío PKCE ni guarda un verificador en el navegador del destinatario.
   Si se recibe `code`, comprobar el flujo que lo generó y la presencia del
   verificador en el mismo origen; el intercambio explícito corresponde a un
   flujo PKCE configurado. No intercambiar dos veces un código ya consumido por
   el SDK. Registrar solo: callback hash/code/ninguno, sesión sí/no y estado HTTP.
4. **JWT / API:** el código valida firma ES256 o RS256, expiración, issuer,
   audience y sub mediante JWKS. Las pruebas offline firman tokens sintéticos y
   cubren firma, expiración, issuer y audience incorrectos, además de ES256.
   Falta comprobar con el proceso dummy que issuer coincide exactamente con
   `<Supabase URL>/auth/v1`, audience con `authenticated`, JWKS con
   `<Supabase URL>/auth/v1/.well-known/jwks.json`, algoritmo permitido y reloj/exp
   válidos. Hacer comparaciones booleanas dentro del proceso autorizado; nunca
   exportar JWT, claves, claims personales o valores de `.env`.
5. **Perfil / membership / RLS:** la API consulta `organization_memberships` usando
   el JWT validado y la clave publicable; exige exactamente una pertenencia válida.
   No deriva el rol del navegador. En SQL, la política permite leer la pertenencia
   propia; la función de administrador usa `security definer` para evitar recursión.
   No se ejecutó RLS real en esta sesión. Un 403 de `/auth/session` puede significar
   membership ausente, respuesta inválida o 401/403 de PostgREST. El perfil no se
   consulta en ese endpoint: su ausencia por sí sola no explica ese 403.
   EAG debe confirmar, sin devolver identificadores: perfil presente, membership
   única de EAG y rol administrador/analista; después comprobar que esa misma
   consulta pasa bajo el JWT del usuario, no solo bajo service_role.
6. **Red / CORS:** sin URL explícita, la UI usa el proxy `/api` de Vite hacia
   `127.0.0.1:8000`. Para una API en otro origen, permitir explícitamente el origen
   de la UI y Authorization en el preflight. El backend ya lo contempla y tiene
   pruebas offline de CORS. No se inspeccionaron valores de `.env`.

Las cinco rutas iniciales de UI, health y sesión (directa/proxy) no fueron
accesibles desde las herramientas, incluso tras repetir fuera del sandbox.
Se levantaron procesos temporales aislados sin configuración Supabase para el
smoke; health respondió y sesión anónima dio 401 en API y proxy. Se terminaron
solo esos procesos. Esto no verifica la sesión del navegador del usuario.

## Verificación reproducible sin leer `.env`

Desde la raíz, las pruebas Python usan el cwd de la raíz y `PYTHONPATH=apps/api`:

```powershell
$env:PYTHONPATH = 'apps/api'
& apps/api/.venv/Scripts/python.exe -m ruff check apps/api
& apps/api/.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app
& apps/api/.venv/Scripts/python.exe -m pytest -c apps/api/pyproject.toml apps/api/tests
python -m unittest discover -s tests -p 'test_*.py'
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
```

Resultados: ruff y mypy correctos; API 20 pruebas; spike 11 pruebas. Dos avisos
existentes de deprecación Starlette/httpx/anyio, sin fallos.

Para que Vite/Vitest no carguen los `.env` locales, se creó un wrapper recreable
ignorado (no cambia la configuración de desarrollo):

```powershell
New-Item -ItemType Directory -Force apps/web/node_modules/.cache | Out-Null
Set-Content apps/web/node_modules/.cache/eag-verification.config.ts 'import config from "../../vite.config.ts"; export default { ...config, envDir: false };'
npm run test --prefix apps/web -- --config node_modules/.cache/eag-verification.config.ts
npm run build --prefix apps/web -- --config node_modules/.cache/eag-verification.config.ts
```

Resultados finales web: lint, typecheck, 19 pruebas y build correctos.
La revisión de los siete archivos del cambio y el escaneo de patrones no detectaron
credenciales ni datos personales; las direcciones e identificadores de pruebas son
sintéticos. `git diff --check` pasó. Solo `.env.example` aparece en los archivos
versionados de configuración de entorno.

El smoke ejecutado fue `python tmp/offline_auth_smoke.py`, un wrapper local
ignorado de `scripts/smoke_local.py` que añade ese `--config` al proceso Vite y
verifica 401 en `/auth/session` y `/api/auth/session`. Resultado: correcto.
Para repetir manualmente: iniciar uvicorn desde la raíz con
`--app-dir apps/api` y Vite desde `apps/web` con ese `--config`; comprobar health,
UI y ambos endpoints anónimos y cerrar los procesos temporales.

## Limpieza conservadora

`git ls-files` no encontró caches, dist, cobertura, node_modules ni entornos
virtuales versionados. `git check-ignore` confirmó ambos `.env` locales ignorados.
Lista de candidatos materiales a eliminar: **vacía**. No se borró ningún archivo
ni fue necesario ampliar `.gitignore`. Los wrappers locales, dist y caches de las
comprobaciones son recreables y ya están ignorados. Se conservaron el spike,
pruebas, migraciones, documentación, lockfiles, CI y `.env.example`.

## Fuentes oficiales consultadas

- [Inicialización del cliente](https://supabase.com/docs/reference/javascript/auth-initialize)
- [Eventos de autenticación](https://supabase.com/docs/reference/javascript/auth-onauthstatechange)
- [Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [Flujo implicit](https://supabase.com/docs/guides/auth/sessions/implicit-flow)
- [Flujo PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow)
- [Invitación administrativa](https://supabase.com/docs/reference/javascript/auth-admin-inviteuserbyemail)

Pendiente: ejecutar login, recarga, refresh/logout reales con la cuenta dummy,
verificar membership/RLS y revisar humanamente el PR. No hay aprobación de EAG.
