# EAG Ingenieros · MVP de preevaluación de licitaciones

Apoyo a la identificación, revisión y preevaluación de oportunidades de SECOP II. La decisión de participar permanece en manos de EAG.

## Estado

Repositorio en preparación: contiene el plan de implementación y el backlog, **todavía no una aplicación funcional**. La integración y la cobertura documental de SECOP deben comprobarse con una prueba técnica antes de construir el resto.

## Empezar

1. Consultar [contexto y alcance](docs/CONTEXTO.md).
2. Seguir el [backlog ordenado](docs/BACKLOG.md).
3. Copiar el prompt de la issue correspondiente desde [prompts de trabajo](docs/PROMPTS.md).
4. Implementar una issue por rama y PR; probar y revisar antes de pasar a la siguiente.

Las instrucciones breves para los agentes están en [AGENTS.md](AGENTS.md). Los documentos internos, datos reales, credenciales y entregables académicos locales no forman parte del repositorio.

## Estructura base local y acceso (MVP-03–04)

Requisitos comprobados en esta base: Python 3.14 y Node.js 24. No requiere
SECOP, Supabase, Redis, OpenAI, credenciales ni servicios de pago.

```powershell
# API (terminal 1)
python -m venv apps/api/.venv
Set-Location apps/api
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# UI (terminal 2, desde la raíz del repositorio)
npm ci --prefix apps/web
npm run dev --prefix apps/web
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run test --prefix apps/web
npm run build --prefix apps/web

# Smoke local API -> proxy Vite -> UI
python scripts/smoke_local.py
```

La API queda en `http://127.0.0.1:8000/health`; su OpenAPI está en
`/openapi.json` y la documentación interactiva en `/docs`. Por defecto CORS no
permite ningún origen. Para permitir una UI concreta, copiar
`apps/api/.env.example`, definir `EAG_CORS_ALLOWED_ORIGINS` con orígenes
explícitos y no añadir comodines. Consulte [ARQUITECTURA_BASE.md](docs/ARQUITECTURA_BASE.md)
para el contrato y la generación futura del cliente TypeScript.

### Acceso con correo y contraseña (usuarios provisionados)

La UI permite iniciar sesión con correo y contraseña mediante
`supabase.auth.signInWithPassword({ email, password })`, sin registro público.
La contraseña se entrega únicamente al SDK de Supabase, se vacía del formulario
al enviar y no se envía a la API propia ni se incorpora a logs o errores.
La UI conserva persistencia, eventos de sesión y cierre de sesión; solo muestra
acceso autenticado después de validar el JWT y los permisos en `/auth/session`.

El navegador solo usa `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY`.
Nunca añada claves de servicio, contraseñas, tokens ni datos personales a Git,
`VITE_*`, OpenAPI o logs. Sin configuración, la UI informa el pendiente.

**Login real pendiente:** un administrador autorizado debe provisionar el dummy
con contraseña, correo confirmado, perfil y membership de EAG con rol
administrador o analista; después probar el acceso con autorización. Esta tarea
no crea usuarios ni cambia contraseñas o datos de Supabase. La recuperación de
contraseña queda pendiente y no tiene interfaz en esta versión.

Se conservan las invitaciones administrativas, revocación, auditoría, roles,
RLS y todas las migraciones. El aprovisionamiento sigue siendo responsabilidad
del backend o de un administrador autorizado. El reenvío de invitaciones mantiene
la limitación documentada (501); SMTP y su validación siguen pendientes.

El cambio agiliza el entorno dummy, sin constituir validación de EAG. Según la
confirmación del usuario, Supabase rechaza la solicitud de magic link antes de
enviarlo: **el flujo passwordless no está integrado ni funcionando**. Se retiró
su solicitud de la UI. Consulte la [matriz de permisos](docs/MATRIZ_DE_PERMISOS.md),
la [arquitectura](docs/ARQUITECTURA_BASE.md) y el
[diagnóstico y comandos de verificación offline](docs/AUTH_DIAGNOSTICO.md).

Riesgo conocido: esta base no valida cobertura documental de SECOP. Mantiene el
spike y su recomendación de carga manual complementaria, sin convertirlos en
una integración productiva.

En Windows, una carpeta sincronizada por OneDrive puede mantener bloqueado un
binario nativo de Vite después de una ejecución interrumpida. Antes de repetir
`npm ci`, asegúrese de cerrar los procesos locales de desarrollo; este riesgo no
afecta los lockfiles ni autoriza omitir sus verificaciones.

## Spike técnico SECOP II (MVP-02)

El spike aislado consulta únicamente los recursos públicos candidatos de SECOP II,
con límites de muestra y sin persistir documentos descargados. Requiere Python
3.11 o superior y solo usa la biblioteca estándar.

```powershell
python -m unittest discover -s tests -p "test_*.py"
python scripts/secop_spike.py --process-limit 5 --document-limit 5 --page-size 2
```

El segundo comando realiza red y debe ejecutarse de forma explícita. Exporta
metadatos públicos mínimos en `output/secop-spike/`, carpeta ignorada por Git.
Para una comprobación acotada de URLs de documentos descubiertas en la muestra,
añada `--download-documents`; los bytes se leen en memoria, están limitados a
1 MiB por defecto y no se guardan. Un token opcional se entrega únicamente como
`SOCRATA_APP_TOKEN`; nunca se escribe en archivos ni se muestra en consola.

Los resultados, límites y recomendación de la comprobación están en
[docs/SECOP_SPIKE.md](docs/SECOP_SPIKE.md).

## Dirección técnica acordada

Python/FastAPI, React/TypeScript, PostgreSQL y servicios administrados. SECOP II desde la primera versión; carga manual de respaldo, OCR básico y revisión humana antes del informe final. Los proveedores y detalles operativos se concretarán en las issues de arquitectura e infraestructura; no hay recursos de pago provisionados.
