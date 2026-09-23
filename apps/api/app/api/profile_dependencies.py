"""Dependencias compartidas de las rutas del perfil.

Viven aparte para que los dos archivos de rutas que las usan no tengan que
importarse entre sí: uno expone la lectura y el versionado, otro la carga de
datos, y ambos necesitan las mismas comprobaciones previas.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status

from app.auth.principal import CurrentPrincipal
from app.profile.service import ProfileService


def get_profile_service(request: Request) -> ProfileService:
    """Servicio del perfil, o 503 si no está configurado."""

    factory = cast(
        "Callable[[], ProfileService] | None",
        getattr(request.app.state, "profile_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El perfil empresarial no está configurado.",
        )
    return factory()


ProfileDep = Annotated[ProfileService, Depends(get_profile_service)]


def require_administrator(principal: CurrentPrincipal) -> None:
    """Comprueba que quien llama puede modificar el perfil.

    El perfil es material privado de la empresa: leerlo lo puede hacer cualquier
    usuario autenticado —necesita saber si está listo antes de confiar en un
    análisis—, pero modificarlo solo un administrador.
    """

    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )


def require_current_version(profile: ProfileService):  # type: ignore[no-untyped-def]
    """Devuelve la versión vigente o falla con un mensaje accionable.

    Se devuelve un mensaje que explica qué hacer —crear una versión— en lugar de
    un error genérico: sin versión no se puede añadir nada, y quien lo intente
    necesita saber por dónde empezar.
    """

    current = profile.current()
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no hay ninguna versión del perfil; cree una antes de añadir datos",
        )
    return current
