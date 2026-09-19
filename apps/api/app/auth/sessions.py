"""Ciclo de vida de las sesiones: emisión, rotación y revocación.

Responsabilidad única: gestionar refresh tokens. No sabe nada de contraseñas ni
de creación de usuarios.

La rotación con detección de reutilización es la parte que importa. Cada uso de
un refresh token emite uno nuevo e invalida el anterior. Si un token ya usado
vuelve a presentarse, significa que alguien lo copió: se revoca **toda la
familia** de esa sesión, no solo el token presentado. Sin eso, un token robado
seguiría renovándose indefinidamente mientras el usuario legítimo no notara nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.auth.audit import AuditLog
from app.auth.identity import subject_for_user
from app.auth.tokens import (
    TokenPair,
    TokenService,
    generate_refresh_token,
    hash_refresh_token,
    refresh_expiry,
)
from app.db.models import Session, User, utcnow


class SessionExpiredError(Exception):
    """El refresh token no es válido, expiró o fue revocado."""


class TokenReuseError(Exception):
    """Se presentó un refresh token ya usado: se revocó la sesión completa."""


@dataclass(frozen=True)
class IssuedSession:
    """Sesión emitida junto con el usuario al que pertenece."""

    user: User
    tokens: TokenPair


def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC una marca de tiempo leída de la base.

    Algunos motores —SQLite entre ellos— no conservan la zona horaria y
    devuelven un datetime sin `tzinfo`. Compararlo con uno consciente lanzaría
    TypeError.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SessionService:
    """Emite, rota y revoca sesiones."""

    def __init__(
        self,
        session: DbSession,
        *,
        tokens: TokenService,
        organization_id: UUID,
        audit: AuditLog | None = None,
    ) -> None:
        self._db = session
        self._tokens = tokens
        self._organization_id = organization_id
        self._audit = audit or AuditLog(session)

    # --- Emisión -----------------------------------------------------------

    def issue(
        self,
        user: User,
        *,
        family_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        """Emite un par de tokens y registra la sesión."""

        from app.auth.principal import Role

        pair = self._tokens.issue(
            subject_id=subject_for_user(user.id),
            organization_id=self._organization_id,
            role=Role(user.role),
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

    # --- Rotación ----------------------------------------------------------

    def rotate(self, refresh_token: str) -> IssuedSession:
        """Rota el refresh token presentado.

        Un token ya usado indica copia: se revoca la familia completa antes de
        rechazar, para que el token robado no siga sirviendo.
        """

        stored = self._find(refresh_token)
        if stored is None or stored.revoked_at is not None:
            raise SessionExpiredError

        if stored.used_at is not None:
            self._revoke_family(stored.family_id)
            self._audit.record(
                "refresh_reuse_detected",
                target_user_id=stored.user_id,
                outcome="failed",
                metadata={"family": stored.family_id},
            )
            self._db.flush()
            raise TokenReuseError

        if _as_utc(stored.expires_at) <= datetime.now(UTC):
            raise SessionExpiredError

        user = self._db.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise SessionExpiredError

        stored.used_at = utcnow()
        pair = self.issue(
            user,
            family_id=stored.family_id,
            user_agent=stored.user_agent,
            ip_address=stored.ip_address,
        )
        self._audit.record("session_refreshed", target_user_id=user.id)
        self._db.flush()
        return IssuedSession(user=user, tokens=pair)

    # --- Revocación --------------------------------------------------------

    def _revoke_family(self, family_id: str) -> None:
        self._db.execute(
            update(Session)
            .where(Session.family_id == family_id, Session.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    def close(self, refresh_token: str) -> bool:
        """Cierra la sesión del refresh token indicado.

        Devuelve si se revocó algo. Un token desconocido no es un error: el
        resultado que le importa al usuario —no poder seguir usándolo— ya se
        cumple.
        """

        stored = self._find(refresh_token)
        if stored is None or stored.revoked_at is not None:
            return False

        self._revoke_family(stored.family_id)
        self._audit.record("logout", target_user_id=stored.user_id)
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
        self._audit.record(
            "sessions_revoked",
            actor_id=actor_id,
            target_user_id=user_id,
            metadata={"count": revoked},
        )
        return revoked

    def _find(self, refresh_token: str) -> Session | None:
        return self._db.execute(
            select(Session).where(
                Session.refresh_hash == hash_refresh_token(refresh_token)
            )
        ).scalar_one_or_none()
