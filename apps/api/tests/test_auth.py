"""Pruebas de autenticación: contraseñas, tokens, sesiones y permisos.

Todo offline: sin red y sin proveedor externo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    hash_password,
    verify_password,
)
from app.auth.principal import AuthError, Role
from app.auth.service import (
    AuthService,
    InvalidCredentialsError,
    SessionExpiredError,
    TokenReuseError,
    normalise_email,
)
from app.auth.tokens import (
    TokenService,
    generate_refresh_token,
    hash_refresh_token,
)
from app.db.models import Base

SECRET = "un-secreto-de-prueba-suficientemente-largo-1234"
PASSWORD = "contrasena-larga-de-prueba"


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def tokens() -> TokenService:
    return TokenService(secret=SECRET)


@pytest.fixture
def auth(db: Session, tokens: TokenService) -> AuthService:
    return AuthService(db, tokens=tokens)


def make_user(auth: AuthService, email: str = "ana@eag.local", role: Role = Role.ANALYST):
    user = auth.create_user(email=email, password=PASSWORD, role=role)
    auth._db.commit()
    return user


# --- Contraseñas -----------------------------------------------------------


def test_password_roundtrip() -> None:
    stored = hash_password(PASSWORD)

    assert verify_password(stored, PASSWORD)
    assert not verify_password(stored, "otra-contrasena-distinta")


def test_password_is_never_stored_in_clear() -> None:
    stored = hash_password(PASSWORD)

    assert PASSWORD not in stored
    assert stored.startswith("$argon2id$")


def test_short_password_is_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        hash_password("corta")


def test_two_hashes_of_the_same_password_differ() -> None:
    """Cada hash lleva su propia sal: dos iguales revelarían contraseñas repetidas."""

    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_invalid_hash_does_not_authenticate() -> None:
    """Un hash corrupto devuelve False, no una excepción que revele el estado."""

    assert not verify_password("no-es-un-hash-valido", PASSWORD)
    assert not verify_password("", PASSWORD)
    assert not verify_password(hash_password(PASSWORD), "")


def test_password_length_requirement_is_documented() -> None:
    assert MIN_PASSWORD_LENGTH == 12


# --- Tokens ----------------------------------------------------------------


def test_issued_access_token_carries_the_identity(tokens: TokenService) -> None:
    subject, org = uuid4(), uuid4()

    pair = tokens.issue(subject_id=subject, organization_id=org, role=Role.ADMINISTRATOR)
    claims = tokens.decode(pair.access_token)

    assert claims.subject_id == subject
    assert claims.organization_id == org
    assert claims.role is Role.ADMINISTRATOR


def test_token_rejects_a_different_secret(tokens: TokenService) -> None:
    pair = tokens.issue(subject_id=uuid4(), organization_id=uuid4(), role=Role.ANALYST)
    other = TokenService(secret="otro-secreto-igualmente-largo-para-la-prueba-99")

    with pytest.raises(AuthError):
        other.decode(pair.access_token)


def test_token_rejects_a_different_audience(tokens: TokenService) -> None:
    """Un token válido para otro servicio no debe servir aquí."""

    pair = tokens.issue(subject_id=uuid4(), organization_id=uuid4(), role=Role.ANALYST)
    other = TokenService(secret=SECRET, audience="otra-api")

    with pytest.raises(AuthError):
        other.decode(pair.access_token)


def test_expired_token_is_rejected(tokens: TokenService) -> None:
    short = TokenService(secret=SECRET, access_ttl=timedelta(seconds=-1))
    pair = short.issue(subject_id=uuid4(), organization_id=uuid4(), role=Role.ANALYST)

    with pytest.raises(AuthError):
        short.decode(pair.access_token)


def test_refresh_token_cannot_be_used_as_access_token(tokens: TokenService) -> None:
    """Aunque comparta firma, un refresh no debe abrir la API."""

    pair = tokens.issue(subject_id=uuid4(), organization_id=uuid4(), role=Role.ANALYST)

    with pytest.raises(AuthError):
        tokens.decode(pair.refresh_token)


def test_unsigned_token_is_rejected(tokens: TokenService) -> None:
    """El ataque clásico: cambiar el algoritmo a `none`."""

    forged = jwt.encode(
        {"sub": str(uuid4()), "org": str(uuid4()), "role": "administrador", "typ": "access"},
        "",
        algorithm="none",
    )

    with pytest.raises(AuthError):
        tokens.decode(forged)


def test_short_secret_is_rejected() -> None:
    """Con HS256 el secreto es la única barrera: uno corto es adivinable."""

    with pytest.raises(ValueError):
        TokenService(secret="corto")


def test_refresh_tokens_are_unique() -> None:
    assert generate_refresh_token() != generate_refresh_token()


def test_refresh_hash_is_stable_and_not_the_token() -> None:
    token = generate_refresh_token()

    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert token not in hash_refresh_token(token)


# --- Inicio de sesión ------------------------------------------------------


def test_login_returns_tokens(auth: AuthService) -> None:
    make_user(auth)

    user, pair = auth.login(email="ana@eag.local", password=PASSWORD)

    assert user.email == "ana@eag.local"
    assert pair.access_token
    assert pair.refresh_token


def test_login_is_case_insensitive_on_email(auth: AuthService) -> None:
    make_user(auth, email="Ana@EAG.local")

    user, _ = auth.login(email="  ANA@eag.LOCAL  ", password=PASSWORD)

    assert user.email == "ana@eag.local"


def test_login_does_not_reveal_whether_the_email_exists(auth: AuthService) -> None:
    """Mismo error para correo inexistente y contraseña incorrecta.

    Distinguirlos permitiría enumerar qué correos tienen cuenta.
    """

    make_user(auth)

    with pytest.raises(InvalidCredentialsError):
        auth.login(email="ana@eag.local", password="contrasena-incorrecta")
    with pytest.raises(InvalidCredentialsError):
        auth.login(email="nadie@eag.local", password=PASSWORD)


def test_deactivated_user_cannot_log_in(auth: AuthService) -> None:
    user = make_user(auth)
    user.is_active = False
    auth._db.commit()

    with pytest.raises(InvalidCredentialsError):
        auth.login(email="ana@eag.local", password=PASSWORD)


def test_login_records_the_attempt_without_secrets(auth: AuthService) -> None:
    from sqlalchemy import select

    from app.db.models import AuditEvent

    make_user(auth)
    auth._db.commit()
    auth.login(email="ana@eag.local", password=PASSWORD)
    auth._db.commit()

    events = auth._db.execute(select(AuditEvent)).scalars().all()
    assert any(e.action == "login_succeeded" for e in events)
    for event in events:
        blob = str(event.metadata_json)
        assert PASSWORD not in blob
        assert "token" not in blob.lower()


def test_failed_login_is_audited(auth: AuthService) -> None:
    from sqlalchemy import select

    from app.db.models import AuditEvent

    make_user(auth)
    auth._db.commit()
    with pytest.raises(InvalidCredentialsError):
        auth.login(email="ana@eag.local", password="incorrecta")
    auth._db.commit()

    events = auth._db.execute(select(AuditEvent)).scalars().all()
    assert any(e.action == "login_failed" and e.outcome == "failed" for e in events)


# --- Rotación de refresh tokens -------------------------------------------


def test_refresh_rotates_the_token(auth: AuthService) -> None:
    make_user(auth)
    _, first = auth.login(email="ana@eag.local", password=PASSWORD)

    _, second = auth.refresh(first.refresh_token)

    assert second.refresh_token != first.refresh_token


def test_old_refresh_token_stops_working_after_rotation(auth: AuthService) -> None:
    make_user(auth)
    _, first = auth.login(email="ana@eag.local", password=PASSWORD)
    auth.refresh(first.refresh_token)

    # El token anterior ya se usó: presentarlo otra vez es reutilización.
    with pytest.raises(TokenReuseError):
        auth.refresh(first.refresh_token)


def test_reuse_revokes_the_whole_session_family(auth: AuthService) -> None:
    """Si alguien copió el token, no basta con rechazar el presentado."""

    make_user(auth)
    _, first = auth.login(email="ana@eag.local", password=PASSWORD)
    _, second = auth.refresh(first.refresh_token)
    _, third = auth.refresh(second.refresh_token)

    with pytest.raises(TokenReuseError):
        auth.refresh(first.refresh_token)

    # El token legítimo más reciente también quedó invalidado.
    with pytest.raises(SessionExpiredError):
        auth.refresh(third.refresh_token)


def test_unknown_refresh_token_is_rejected(auth: AuthService) -> None:
    with pytest.raises(SessionExpiredError):
        auth.refresh(generate_refresh_token())


def test_expired_refresh_token_is_rejected(auth: AuthService) -> None:
    from sqlalchemy import select

    from app.db.models import Session as DbSession

    make_user(auth)
    _, pair = auth.login(email="ana@eag.local", password=PASSWORD)
    auth._db.commit()

    stored = auth._db.execute(
        select(DbSession).where(
            DbSession.refresh_hash == hash_refresh_token(pair.refresh_token)
        )
    ).scalar_one()
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    auth._db.commit()

    with pytest.raises(SessionExpiredError):
        auth.refresh(pair.refresh_token)


def test_session_stores_only_the_hash(auth: AuthService) -> None:
    from sqlalchemy import select

    from app.db.models import Session as DbSession

    make_user(auth)
    _, pair = auth.login(email="ana@eag.local", password=PASSWORD)
    auth._db.commit()

    stored = auth._db.execute(select(DbSession)).scalars().all()
    assert stored
    for row in stored:
        assert row.refresh_hash != pair.refresh_token
        assert len(row.refresh_hash) == 64  # sha256 hex


# --- Cierre de sesión ------------------------------------------------------


def test_logout_revokes_the_session(auth: AuthService) -> None:
    make_user(auth)
    _, pair = auth.login(email="ana@eag.local", password=PASSWORD)

    assert auth.logout(pair.refresh_token) is True
    with pytest.raises(SessionExpiredError):
        auth.refresh(pair.refresh_token)


def test_logout_with_unknown_token_is_not_an_error(auth: AuthService) -> None:
    """El resultado que importa —no poder usarlo— ya se cumple."""

    assert auth.logout(generate_refresh_token()) is False


def test_deactivating_a_user_revokes_all_sessions(auth: AuthService) -> None:
    """Sin esto, las sesiones abiertas seguirían renovándose."""

    user = make_user(auth)
    _, pair = auth.login(email="ana@eag.local", password=PASSWORD)
    auth._db.commit()

    auth.deactivate_user(user.id)
    auth._db.commit()

    with pytest.raises(SessionExpiredError):
        auth.refresh(pair.refresh_token)


def test_revoking_sessions_reports_the_count(auth: AuthService) -> None:
    user = make_user(auth)
    auth.login(email="ana@eag.local", password=PASSWORD)
    auth.login(email="ana@eag.local", password=PASSWORD)
    auth._db.commit()

    assert auth.revoke_user_sessions(user.id) == 2


# --- Normalización ---------------------------------------------------------


def test_email_normalisation() -> None:
    assert normalise_email("  Ana@EAG.Local  ") == "ana@eag.local"


def test_first_user_can_be_created_without_actor(auth: AuthService) -> None:
    """El primer administrador no tiene quien lo invite."""

    assert auth.count_users() == 0
    make_user(auth, role=Role.ADMINISTRATOR)
    assert auth.count_users() == 1
