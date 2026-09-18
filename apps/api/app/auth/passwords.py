"""Hashing de contraseñas.

Se usa Argon2id, el ganador de la Password Hashing Competition y la
recomendación actual de OWASP para almacenamiento de contraseñas.

Dos decisiones que importan más que el algoritmo:

1. **La verificación es de tiempo constante.** `verify` de argon2-cffi lo
   garantiza; comparar hashes con `==` filtraría información por temporización.
2. **Un hash inválido o de formato desconocido no autentica.** Se captura la
   excepción y se devuelve `False`, en lugar de propagarla o de dejar que un
   hash corrupto provoque un 500 que revele el estado de la cuenta.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.exceptions import VerificationError as Argon2VerificationError

# Parámetros explícitos en lugar de los del entorno: si cambian las variables
# de la máquina, el coste de hashing no debe cambiar de forma silenciosa entre
# despliegues, porque los hashes existentes dejarían de ser verificables con el
# mismo coste y una auditoría no podría reproducirlo.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# Longitud mínima. No se impone una política de complejidad de caracteres:
# añade fricción sin mejorar la seguridad real y empuja a patrones predecibles.
MIN_PASSWORD_LENGTH = 12


class WeakPasswordError(ValueError):
    """La contraseña no cumple la longitud mínima."""


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de la contraseña."""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"la contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
        )
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Verifica una contraseña contra su hash.

    Devuelve `False` ante cualquier fallo en lugar de propagar la excepción: el
    llamador no necesita distinguir "contraseña incorrecta" de "hash corrupto",
    y esa distinción no debe llegar al usuario.
    """

    if not stored_hash or not password:
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, Argon2VerificationError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Indica si el hash se generó con parámetros distintos a los actuales.

    Permite migrar el coste de hashing sin pedir la contraseña de nuevo: al
    iniciar sesión con éxito, si el hash quedó obsoleto se recalcula.
    """

    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True
