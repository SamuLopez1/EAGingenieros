"""Integración con proveedores de IA.

Adaptado del patrón del proyecto `agentes-asobares`, que ya resolvió en
producción la configuración multi-proveedor y la medición de consumo.

Contenido:

- ``providers``: registro de proveedores, clientes con timeouts explícitos y
  extracción de tokens tolerante a las diferencias entre proveedores.
- ``budget``: tope mensual comprobado **antes** de gastar, y caché de llamadas
  por hash de contenido, modelo y versión de prompt.

Regla del paquete: **ninguna llamada sin medición y ninguna llamada sin tope.**
"""

from app.ai.budget import (
    BudgetExceeded,
    BudgetState,
    budget_state,
    ensure_within_budget,
    get_cached,
    make_cache_key,
    record_usage,
    store_cached,
)
from app.ai.providers import (
    PROVIDERS,
    Provider,
    ProviderConfig,
    TokenUsage,
    UnknownProviderError,
    describe_providers,
    estimate_cost,
    extract_usage,
    get_provider,
    timeouts_for,
)

__all__ = [
    "PROVIDERS",
    "BudgetExceeded",
    "BudgetState",
    "Provider",
    "ProviderConfig",
    "TokenUsage",
    "UnknownProviderError",
    "budget_state",
    "describe_providers",
    "ensure_within_budget",
    "estimate_cost",
    "extract_usage",
    "get_cached",
    "get_provider",
    "make_cache_key",
    "record_usage",
    "store_cached",
    "timeouts_for",
]
