"""Identidad externa de los usuarios.

El identificador interno es entero porque así lo usa la base de datos, pero hacia
fuera se expone un UUID. La conversión vive aquí, en un solo sitio, porque tener
dos derivaciones distintas del mismo concepto ya causó un fallo real: el login
emitía un UUID y la validación buscaba otro, de modo que toda petición
autenticada respondía «el usuario del token no existe».
"""

from __future__ import annotations

import hmac
from uuid import UUID, uuid5

# Namespace fijo para derivar el UUID externo. Debe permanecer constante: si
# cambiara, los UUID de los usuarios existentes cambiarían y los tokens ya
# emitidos dejarían de corresponder a su sujeto.
_EAG_NAMESPACE = UUID("6f7a1c2e-3b4d-5e6f-8a9b-0c1d2e3f4a5b")


def subject_for_user(user_id: int) -> UUID:
    """Deriva el UUID externo de un identificador interno.

    Se usa UUID v5 y no `UUID(int=user_id)`: el segundo interpreta el entero
    como los 128 bits completos del UUID, y un valor grande no cabría en el
    entero de 64 bits que admite un motor como SQLite.
    """

    return uuid5(_EAG_NAMESPACE, str(user_id))


def user_id_from_subject(subject_id: UUID, candidates: list[int]) -> int | None:
    """Recupera el identificador interno a partir del UUID externo.

    La derivación es unidireccional a propósito, para que el identificador
    externo no revele el interno, así que hay que comprobar los candidatos. La
    comparación usa `hmac.compare_digest` para no filtrar por temporización qué
    posición de la lista coincide.
    """

    for candidate in candidates:
        if hmac.compare_digest(str(subject_for_user(candidate)), str(subject_id)):
            return candidate
    return None
