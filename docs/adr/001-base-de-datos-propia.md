# ADR-001: Base de datos propia, sin Supabase

**Estado:** Aceptada
**Fecha:** 2026-09-23

## Contexto

El plan del MVP (v3.0, decisión A3 y fase F0) preveía un **Supabase
self-hosted**: Postgres + Auth + Storage en un stack aislado. El repositorio ya
tenía montado ese stack en `infra/supabase`, y también un entorno más simple en
`infra/dev` con Postgres y la API.

Al retomarlo aparecieron tres hechos:

1. El stack de Supabase estaba **pausado y con Kong en bucle de reinicio** (la
   imagen `kong:3.9.1` no trae `envsubst`, así que la plantilla de configuración
   no se renderizaba).
2. La autenticación **propia ya estaba implementada** —Argon2id, JWT, rotación de
   sesiones con detección de reutilización— y era la que usaban las rutas. La
   abstracción hacia Supabase Auth (`supabase_gateway.py`) estaba **referenciada
   pero no existía**.
3. El propósito declarado de Supabase en este proyecto era Auth y Storage, no
   Postgres: los datos ya vivían en un Postgres propio.

## Decisión

**Base de datos PostgreSQL propia en Docker, sin Supabase.** La autenticación
propia se mantiene. La extensión `pgvector` cubre la recuperación vectorial sobre
la misma base, así que no hace falta ningún servicio adicional.

## Consecuencias

**A favor**

- **Un solo stack en lugar de dos.** El repositorio tenía dos compose que
  solapaban; consolidarlos elimina la pregunta de cuál es el bueno.
- **Los vectores no cruzan un límite de confianza.** La recuperación consulta la
  misma base que el resto de los datos, sin proveedor externo que autorizar
  (coincide con la decisión B10 del plan).
- **Menos superficie operativa.** Un componente menos que puede caerse, y ningún
  Kong que renderizar.

**En contra, y lo que se asume**

- **Se pierde el `httpOnly` de las cookies de Supabase Auth.** Los tokens viajan
  en el cuerpo de la respuesta y el navegador tiene que guardarlos. Ver
  [ADR-006](006-tokens-en-sessionstorage.md).
- **RLS deja de ser una barrera.** El plan ya lo asumía (decisión A3: «FastAPI
  como capa de autoridad»). La autorización vive entera en la API, y por eso las
  rutas de negocio exigen identidad resuelta.
- **El stack de `infra/supabase` queda obsoleto.** No se ha borrado porque sus
  volúmenes contienen datos de una etapa anterior y borrarlos no es una decisión
  que corresponda tomar a este cambio.
