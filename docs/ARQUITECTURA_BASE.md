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

Supabase es el proveedor previsto, sin afirmar que exista un proyecto o una
integración real configurada. La API valida JWT por JWKS configurables y exige
firma `RS256`, expiración, issuer, audience y `sub` antes de resolver una
pertenencia. El rol y la organización no se toman de claims ni de datos del
cliente: se resuelven después de validar el token.

La organización inicial prevista es EAG, con roles `administrador` y
`analista`. La migración en `supabase/migrations/20260904000000_auth_roles_rls.sql`
crea perfiles, membresías, invitaciones, auditoría mínima y políticas RLS. No
concede escrituras a clientes autenticados; cualquier cambio de rol,
organización o invitación queda reservado a backend y debe registrarse.
Consulte la [matriz de permisos](MATRIZ_DE_PERMISOS.md).

La UI usa solo `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY`, que son
configuración publicable. La clave `EAG_SUPABASE_SERVICE_ROLE_KEY` se reserva
para el proceso backend y nunca debe tener prefijo `VITE_`, aparecer en OpenAPI
o registrarse. Sin configuración externa, la UI indica el pendiente y las rutas
de invitación responden de forma explícita sin enviar correos.

### Configuración externa pendiente

EAG debe crear y gobernar el proyecto Supabase, aplicar la migración, desactivar
el registro público, configurar correo/SMTP y URLs de redirección permitidas,
asignar el primer administrador mediante un procedimiento controlado y entregar
valores de prueba autorizados fuera de Git. El backend requerirá URL de
Supabase, clave publicable para resolver RLS, clave de servicio solo para las
operaciones administrativas, JWKS, issuer y audience. Los adaptadores reales,
la prueba E2E y la estrategia de revocación no se han ejecutado.
