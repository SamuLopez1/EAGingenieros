"""Capa HTTP del MVP.

Cada dominio expone sus rutas en un archivo propio. Los contratos viven en
`schemas/`, separados de los endpoints: un archivo que mezcla veinte esquemas con
la lógica de las peticiones obliga a saltar entre dos responsabilidades para leer
una sola ruta.
"""

from app.api.analysis_routes import router as analysis_router
from app.api.auth_routes import router as auth_router
from app.api.knowledge_routes import router as knowledge_router
from app.api.profile_data_routes import router as profile_data_router
from app.api.profile_routes import router as profile_router
from app.api.routes import router as opportunities_router

__all__ = [
    "analysis_router",
    "auth_router",
    "knowledge_router",
    "opportunities_router",
    "profile_data_router",
    "profile_router",
]
