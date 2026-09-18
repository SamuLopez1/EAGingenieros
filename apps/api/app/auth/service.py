"""Servicio de autenticación: registro, sesión y rotación de tokens.

Este módulo concentra las decisiones de seguridad del acceso. Las tres que más
importan:

1. **El error de login no distingue causa.** Correo inexistente, contraseña
   incorrecta y cuenta desactivada devuelven el mismo error. Distinguirlos
   permitiría enumerar qué correos tienen cuenta, que es información útil para
   un atacante y no hace falta para el usuario legítimo.

2. **Se verifica la contraseña aunque el usuario no exista.** Sin esto, un
   correo inexistente respondería antes que uno válido y la diferencia de
   tiempo revelaría qué cuentas existen. Se compara contra un hash señuelo para
   igualar el coste.

3. **Reutilizar un refresh token revoca la sesión completa.** Si un token ya
   rotado vuelve a presentarse, alguien copió el token: se revoca toda la
   familia, no solo el presentado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.principal import Role
from app.auth.tokens import (
    TokenPair,
    TokenService,
    generate_refresh_token,
    hash_refresh_token,
    refresh_expiry,
)
from app.db.models import AuditEvent, Session, User, utcnow

# Hash de una contraseña descartable, usado para igualar el tiempo de respuesta
# cuando el correo no existe. Se genera una vez al importar el módulo.
_DUMMY_HASH = hash_password("contrasena-senuelo-que-nunca-coincide")


class InvalidCredentialsError(Exception):
    """Credenciales incorrectas o cuenta no utilizable. No distingue cuál."""


class SessionExpiredError(Exception):
    """El refresh token no es válido, expiró o fue revocado."""


class TokenReuseError(Exception):
    """Se presentó un refresh token ya usado: se revocó la sesión completa."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    email: str
    display_name: str | None
    role: Role
    organization_id: UUID


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(
        self,
        session: DbSession,
        *,
        tokens: TokenService,
        organization_id: UUID | None = None,
    ) -> None:
        self._db = session
        self._tokens = tokens
        # UUID fijo de la unica organizacion del MVP. Se mantiene el tipo UUID
        # porque el dominio del token lo usa y asi no hay conversion implicita.
        self._organization_id = organization_id or UUID(int=1)

    # --- Consultas ---------------------------------------------------------

    def _find_user(self, email: str) -> User | None:
        return self._db.execute(
            select(User).where(User.email == normalise_email(email))
        ).scalar_one_or_none()

    def _audit(
        self,
        action: str,
        *,
        actor_id: int | None = None,
        target_user_id: int | None = None,
        outcome: str = "ok",
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Registra un evento sin contenido sensible.

        Se filtran las claves prohibidas por si el llamador las incluye: la
        restricción no puede depender de que quien llame se acuerde.
        """

        forbidden = {"password", "token", "authorization", "refresh", "secret"}
        safe: dict[str, object] = {}
        for key, value in (metadata or {}).items():
            if any(word in key.lower() for word in forbidden):
                continue
            safe[key] = value
        self._db.add(
            AuditEvent(
                action=action,
                actor_id=actor_id,
                target_user_id=target_user_id,
                outcome=outcome,
                metadata_json=safe,
            )
        )

    # --- Registro ----------------------------------------------------------

    def create_user(
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
        self._audit(
            "user_created",
            actor_id=actor_id,
            target_user_id=user.id,
            metadata={"role": role.value},
        )
        return user

    def count_users(self) -> int:
        """Número de cuentas. Se usa para permitir el primer administrador."""

        return len(self._db.execute(select(User.id)).scalars().all())

    # --- Inicio de sesión --------------------------------------------------

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, TokenPair]:
        user = self._find_user(email)

        if user is None:
            # Se verifica contra un hash señuelo para que el tiempo de respuesta
            # no revele si el correo existe.
            verify_password(_DUMMY_HASH, password)
            self._audit("login_failed", outcome="failed", metadata={"reason": "unknown_email"})
            raise InvalidCredentialsError

        if not verify_password(user.password_hash, password):
            self._audit(
                "login_failed",
                target_user_id=user.id,
                outcome="failed",
                metadata={"reason": "bad_password"},
            )
            raise InvalidCredentialsError

        if not user.is_active:
            self._audit(
                "login_failed",
                target_user_id=user.id,
                outcome="failed",
                metadata={"reason": "inactive"},
            )
            raise InvalidCredentialsError

        # Si el coste de hashing cambió, se recalcula ahora que tenemos la
        # contraseña en claro. No se hace nunca antes de verificar.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_login_at = utcnow()
        pair = self._issue_session(
            user, user_agent=user_agent, ip_address=ip_address
        )
        self._audit("login_succeeded", target_user_id=user.id)
        return user, pair

    def _issue_session(
        self,
        user: User,
        *,
        family_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        role = Role(user.role)
        pair = self._tokens.issue(
            subject_id=_uuid_from_user(user.id),
            organization_id=self._organization_id,
            role=role,
        )
        self._db.add(
            Session(
                user_id=user.id,
                family_id=family_id or generate_refresh_token()[:32],
                refresh_hash=hash_refresh_token(pair.refresh_token),
                expires_at=refresh_expiry(),
                user_agent=(user_agent or "")[:300] or None,
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self._db.flush()
        return pair

    # --- Renovación --------------------------------------------------------

    def refresh(self, refresh_token: str) -> tuple[User, TokenPair]:
        """Rota el refresh token.

        Si el token presentado ya se usó, se revoca la familia completa: eso
        indica que alguien copió un token y hay dos partes usándolo.
        """

        token_hash = hash_refresh_token(refresh_token)
        stored = self._db.execute(
            select(Session).where(Session.refresh_hash == token_hash)
        ).scalar_one_or_none()

        if stored is None:
            raise SessionExpiredError

        if stored.revoked_at is not None:
            raise SessionExpiredError

        if stored.used_at is not None:
            # Reutilización: se revoca todo lo derivado de este inicio de sesión.
            self._revoke_family(stored.family_id)
            self._audit(
                "refresh_reuse_detected",
                target_user_id=stored.user_id,
                outcome="failed",
                metadata={"family": stored.family_id},
            )
            raise TokenReuseError

        if _as_utc(stored.expires_at) <= datetime.now(UTC):
            raise SessionExpiredError

        user = self._db.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise SessionExpiredError

        stored.used_at = utcnow()
        pair = self._issue_session(
            user,
            family_id=stored.family_id,
            user_agent=stored.user_agent,
            ip_address=stored.ip_address,
        )
        self._audit("session_refreshed", target_user_id=user.id)
        return user, pair

    def _revoke_family(self, family_id: str) -> None:
        self._db.execute(
            update(Session)
            .where(Session.family_id == family_id, Session.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    # --- Cierre de sesión --------------------------------------------------

    def logout(self, refresh_token: str) -> bool:
        """Revoca la sesión del refresh token indicado.

        Devuelve si se revocó algo. Un token desconocido no es un error: el
        resultado que le importa al usuario —no poder seguir usándolo— ya se
        cumple.
        """

        token_hash = hash_refresh_token(refresh_token)
        stored = self._db.execute(
            select(Session).where(Session.refresh_hash == token_hash)
        ).scalar_one_or_none()
        if stored is None or stored.revoked_at is not None:
            return False

        self._revoke_family(stored.family_id)
        self._audit("logout", target_user_id=stored.user_id)
        return True

    def revoke_user_sessions(self, user_id: int, *, actor_id: int | None = None) -> int:
        """Cierra todas las sesiones de un usuario.

        Se usa al desactivar una cuenta o al cambiar su contraseña: sin esto,
        las sesiones abiertas seguirían renovándose.
        """

        result = self._db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        revoked = int(result.rowcount or 0)  # type: ignore[attr-defined]
        self._audit(
            "sessions_revoked",
            actor_id=actor_id,
            target_user_id=user_id,
            metadata={"count": revoked},
        )
        return revoked

    def deactivate_user(self, user_id: int, *, actor_id: int | None = None) -> None:
        user = self._db.get(User, user_id)
        if user is None:
            raise InvalidCredentialsError
        user.is_active = False
        self.revoke_user_sessions(user_id, actor_id=actor_id)
        self._audit("user_deactivated", actor_id=actor_id, target_user_id=user_id)


def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC una marca de tiempo leida de la base.

    Algunos motores —SQLite entre ellos— no conservan la zona horaria y
    devuelven un datetime sin `tzinfo`. Compararlo con uno consciente lanzaria
    TypeError. Se asume UTC, que es como se escribe siempre, en lugar de
    comparar a ciegas.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _uuid_from_user(user_id: int) -> UUID:  # noqa: F821
    """Deriva un UUID estable del identificador entero.

    El dominio del token usa UUID porque Supabase lo hacía; mantenerlo permite
    cambiar de proveedor sin tocar los contratos. La derivación es determinista
    para que el mismo usuario produzca siempre el mismo UUID.
    """

    from uuid import UUID

    return UUID(int=user_id)


def session_ttl() -> timedelta:
    """Duración del refresh token, expuesta para documentación y pruebas."""

    from app.auth.tokens import REFRESH_TOKEN_TTL

    return REFRESH_TOKEN_TTL
