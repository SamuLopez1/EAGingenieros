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

## Lenguajes y stack

Dos lenguajes escriben la aplicación; el resto son configuración e infraestructura.

| Capa | Lenguaje | Tecnología |
| --- | --- | --- |
| API | **Python** 3.12 (imagen) · 3.14 (desarrollo) | FastAPI · Pydantic · SQLAlchemy · Alembic · LangGraph · pgvector |
| Web | **TypeScript** (`.ts` y `.tsx`) | React 19 · Vite · React Router · TanStack Query · CSS con tokens |
| Datos | **SQL** dentro de migraciones Alembic | PostgreSQL 17 + pgvector (HNSW) |
| Estilos | **CSS** | Tokens propios derivados de `docs/design/DESIGN.md` |
| Infra | **YAML** · Dockerfile · nginx | Docker Compose · GitHub Actions |
| Documentación | **Markdown** | `docs/` |

Medición real del repositorio, sin archivos generados ni dependencias instaladas
(`python3 scripts/contar_lenguajes.py`). «Código» excluye líneas en blanco y de
comentario: informar solo del total infla la cifra.

| Lenguaje | Archivos | Código | Comentario |
| --- | ---: | ---: | ---: |
| Python | 99 | 11 706 | 2 951 |
| TypeScript (TSX) | 13 | 1 623 | 217 |
| Markdown | 32 | 2 416 | — |
| CSS | 3 | 895 | 97 |
| TypeScript | 11 | 526 | 201 |
| HTML | 2 | 475 | — |
| YAML | 3 | 184 | 63 |
| Dockerfile | 4 | 63 | 42 |
| Nginx | 1 | 41 | 26 |
| Otros (JSON, INI, TOML, Mako, JS) | 9 | 187 | 95 |
| **Total** | **177** | **18 116** | **3 692** |

Es una fotografía, no un valor vivo: cambiar este mismo README altera la fila de
Markdown, así que las cifras se desvían solas. Para el número actual, ejecutar el
script.

En Python, la API son ~67 archivos y las pruebas ~15. Las pruebas son cerca de
un tercio de las líneas de Python, porque el repositorio exige una prueba
reproducible antes de tocar la red. En TypeScript, el frontend reparte 24
archivos entre `pages/` (pantallas), `design/` (componentes y tokens), `auth/`
(sesión) y `api/` (contrato HTTP).

## Stack completo en Docker (recomendado)

Levanta base de datos, API y web con un comando. **Base de datos propia
(PostgreSQL + pgvector); no usa Supabase ni ningún servicio administrado.**

```bash
cp .env.example .env      # y definir POSTGRES_PASSWORD y EAG_JWT_SECRET

# Generar el secreto de firma de sesiones:
openssl rand -base64 48   # pegar en EAG_JWT_SECRET

docker compose up -d --build
docker compose ps
```

| Servicio | Dirección | Contenedor |
| --- | --- | --- |
| Web | http://127.0.0.1:8082 | `eag-app-web` |
| API | http://127.0.0.1:8132/api/health · `/docs` para OpenAPI | `eag-app-api` |
| PostgreSQL | `127.0.0.1:5446` (solo inspección) | `eag-app-db` |

El proyecto de Compose se llama `eag-app` y no comparte contenedor, red,
volumen ni puerto con ningún otro stack de la máquina. Aislamiento deliberado:
`eag-app-net`, `eag-app-db-data`, puertos 5446 / 8132 / 8082.

La API aplica las migraciones de Alembic al arrancar. Si fallan, el contenedor
no arranca: es preferible a servir una API contra un esquema incompleto.

**Crear el primer administrador.** No hay registro público; las cuentas se crean
por invitación. Sin una cuenta no se puede entrar, porque todas las rutas de
negocio exigen sesión:

```bash
docker compose exec api python -m scripts.crear_admin \
  --email analista@eag.example --password 'una-contraseña-larga' --role administrador
```

**Sincronizar las fuentes.** Desde la interfaz, en *Oportunidades* o en
*Fuentes*. También por HTTP:

```bash
# SECOP II (fuente principal)
curl -X POST 'http://127.0.0.1:8132/api/v1/sync-runs?limit=50' \
  -H "Authorization: Bearer <access_token>"

# SECOP I
curl -X POST 'http://127.0.0.1:8132/api/v1/sync-runs?dataset=f789-7hwg&limit=50' \
  -H "Authorization: Bearer <access_token>"
```

Para detener solo este stack, sin tocar otros: `docker compose down`. Los datos
permanecen en el volumen `eag-app-db-data`.

### Por qué una sola fuente de rutas

El navegador habla únicamente bajo `/api`. Es el prefijo real de FastAPI
(`/api/v1/...`, `/api/health`) y lo único que el proxy cubre, en desarrollo
(Vite) y en el contenedor (nginx). Ninguno de los dos reescribe el prefijo, así
que desarrollo y despliegue resuelven exactamente las mismas rutas.

## Estructura base local (MVP-03)

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
