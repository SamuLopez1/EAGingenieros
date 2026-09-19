"""Contratos HTTP publicados por FastAPI y, posteriormente, OpenAPI."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str
    # "database" o "memory". Se declara para que nadie confunda una demostración
    # en memoria con un entorno con persistencia real.
    persistence: Literal["database", "memory"] = "memory"
    # "proveedor_externo" o "local_sin_semantica". El representador local no
    # entiende de significado: se declara para no confundir una demostración con
    # un entorno con recuperación semántica real.
    embeddings: Literal["proveedor_externo", "local_sin_semantica"] = "local_sin_semantica"
