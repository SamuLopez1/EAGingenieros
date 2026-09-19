"""Cuentas de usuario: creación, credenciales y estado.

Responsabilidad única: gestionar quién puede entrar y con qué credenciales. No
sabe nada de tokens ni de rotación de sesiones.

Dos decisiones que viven aquí:

1. **El error de credenciales no distingue causa.** Correo inexistente,
   contraseña incorrecta y cuenta desactivada producen el mismo fallo.
   Distinguirlos permitiría enumerar qué correos tienen cuenta, que es
   información útil para un atacante y no hace falta para el usuario legítimo.

2. **Se verifica la contraseña aunque el usuario no exista.** Sin esto, un
   correo inexistente respondería antes que uno válido y la diferencia de tiempo
   revelaría qué cuentas existen. Se compara contra un hash señuelo para igualar
   el coste.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.audit import AuditLog
from app.auth.identity import subject_for_user, user_id_from_subject
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.principal import AuthError, Principal, Role
from app.db.models import User, utcnow

# Hash descartable para igualar el tiempo de respuesta cuando el correo no
# existe. Se genera una vez al importar el módulo.
_DUMMY_HASH = hash_password("contrasena-senuelo-que-nunca-coincide")


class InvalidCredentialsError(Exception):
    """Credenciales incorrectas o cuenta no utilizable. No distingue cuál."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AccountService:
    """Gestiona cuentas y credenciales."""

    def __init__(self, session: DbSession, *, audit: AuditLog | None = None) -> None:
        self._db = session
        self._audit = audit or AuditLog(session)

    # --- Consultas ---------------------------------------------------------

    def find_by_email(self, email: str) -> User | None:
        return self._db.execute(
            select(User).where(User.email == normalise_email(email))
        ).scalar_one_or_none()

    def get(self, user_id: int) -> User | None:
        return self._db.get(User, user_id)

    def count(self) -> int:
        """Número de cuentas. Se usa para permitir el primer administrador."""

        return len(self._db.execute(select(User.id)).scalars().all())

    def by_subject(self, subject_id: object) -> User | None:
        """Recupera el usuario a partir del UUID que viaja en el token.

        No se invierte la derivación del UUID —es unidireccional a propósito—,
        así que se comprueban los candidatos.
        """

        from uuid import UUID

        if not isinstance(subject_id, UUID):
            return None
        candidates = list(self._db.execute(select(User.id)).scalars().all())
        found = user_id_from_subject(subject_id, candidates)
        return self._db.get(User, found) if found is not None else None

    # --- Creación ----------------------------------------------------------

    def create(
        self,
        *,
        email: str,
        password: str,
        role: Role,
        display_name: str | None = None,
        actor_id: int | None = None,
    ) -> User:
        """Crea una cuenta. No hay registro público: solo un administrador."""

        user = User(
            email=normalise_email(email),
            display_name=display_name,
            password_hash=hash_password(password),
            role=role.value,
            is_active=True,
        )
        self._db.add(user)
        self._db.flush()
        self._audit.record(
            "user_created",
            actor_id=actor_id,
            target_user_id=user.id,
            metadata={"role": role.value},
        )
        return user

    # --- Autenticación -----------------------------------------------------

    def verify_credentials(self, email: str, password: str) -> User:
        """Comprueba correo y contraseña, o falla sin distinguir la causa."""

        user = self.find_by_email(email)

        if user is None:
            # Se verifica contra el hash señuelo para que el tiempo de respuesta
            # no revele si el correo existe.
            verify_password(_DUMMY_HASH, password)
            self._audit.record(
                "login_failed", outcome="failed", metadata={"reason": "unknown_email"}
            )
            raise InvalidCredentialsError

        if not verify_password(user.password_hash, password):
            self._audit.record(
                "login_failed",
                target_user_id=user.id,
                outcome="failed",
                metadata={"reason": "bad_password"},
            )
            raise InvalidCredentialsError

        if not user.is_active:
            self._audit.record(
                "login_failed",
                target_user_id=user.id,
                outcome="failed",
                metadata={"reason": "inactive"},
            )
            raise InvalidCredentialsError

        # Si el coste de hashing cambió, se recalcula ahora que tenemos la
        # contraseña en claro. Nunca antes de verificar.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_login_at = utcnow()
        return user

    def principal_from_token(self, token: str, tokens: object) -> Principal:
        """Valida un access token y construye la identidad.

        El rol se resuelve desde la base de datos, no del token: un token emitido
        antes de un cambio de rol seguiría concediendo el anterior hasta expirar.
        Un usuario desactivado queda rechazado de inmediato.
        """

        from app.auth.tokens import TokenService

        if not isinstance(tokens, TokenService):
            raise AuthError("servicio de tokens no configurado")

        claims = tokens.decode(token)
        user = self.by_subject(claims.subject_id)
        if user is None:
            raise AuthError("el usuario del token no existe")
        if not user.is_active:
            raise AuthError("el usuario está desactivado")

        # Un cambio de contraseña invalida los tokens emitidos antes de él: es
        # la forma de cerrar sesiones posiblemente robadas sin mantener una
        # lista de revocación de access tokens.
        changed = user.password_changed_at
        if changed is not None:
            from app.auth.sessions import _as_utc

            issued_at = claims.expires_at - timedelta(seconds=tokens.access_ttl_seconds)
            if issued_at < _as_utc(changed):
                raise AuthError("la contraseña cambió después de emitirse el token")

        return Principal(
            subject_id=claims.subject_id,
            organization_id=claims.organization_id,
            role=Role(user.role),
            user_id=user.id,
        )

    # --- Credenciales ------------------------------------------------------

    def change_password(
        self,
        user_id: int,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        """Cambia la contraseña. La verificación de la actual es obligatoria.

        Sin exigir la contraseña actual, un access token robado bastaría para
        apropiarse de la cuenta cambiando la credencial.
        """

        user = self._db.get(User, user_id)
        if user is None:
            raise InvalidCredentialsError

        if not verify_password(user.password_hash, current_password):
            self._audit.record(
                "password_change_failed", target_user_id=user_id, outcome="failed"
            )
            raise InvalidCredentialsError

        if verify_password(user.password_hash, new_password):
            raise ValueError("la contraseña nueva debe ser distinta de la actual")

        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        self._audit.record("password_changed", target_user_id=user_id)

    def deactivate(self, user_id: int, *, actor_id: int | None = None) -> None:
        user = self._db.get(User, user_id)
        if user is None:
            raise InvalidCredentialsError
        user.is_active = False
        self._audit.record("user_deactivated", actor_id=actor_id, target_user_id=user_id)


__all__ = [
    "AccountService",
    "InvalidCredentialsError",
    "normalise_email",
    "subject_for_user",
]
