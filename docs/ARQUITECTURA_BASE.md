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
