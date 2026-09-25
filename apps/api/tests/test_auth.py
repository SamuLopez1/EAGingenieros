from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from jwt import PyJWKClientConnectionError

from app.auth import AuthServices, JwtValidator, Membership, Role, SupabaseMembershipResolver
from app.config import Settings
from app.invitations import InvitationResendUnsupported, InvitationService
from app.main import create_app

ISSUER = "https://example.supabase.co/auth/v1"
AUDIENCE = "authenticated"
ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000002")


class FixedSigningKey:
    def __init__(self, public_key: rsa.RSAPublicKey) -> None:
        self.public_key = public_key

    def __call__(self, encoded_token: str) -> rsa.RSAPublicKey:
        del encoded_token
        return self.public_key


class FakeMemberships:
    def __init__(self, memberships: dict[UUID, Membership]) -> None:
        self.memberships = memberships

    def resolve(self, subject_id: UUID, access_token: str) -> Membership | None:
        del access_token
        return self.memberships.get(subject_id)


class FakeInvitations:
    def __init__(self) -> None:
        self.created: list[tuple[str, UUID, UUID]] = []
        self.resent: list[tuple[UUID, UUID, UUID]] = []
        self.revoked: list[tuple[UUID, UUID, UUID]] = []

    def create(self, *, email: str, organization_id: UUID, actor_id: UUID) -> UUID:
        self.created.append((email, organization_id, actor_id))
        return UUID("00000000-0000-0000-0000-000000000099")

    def resend(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
        self.resent.append((invitation_id, organization_id, actor_id))

    def revoke(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
        self.revoked.append((invitation_id, organization_id, actor_id))


def make_settings() -> Settings:
    return Settings(
        environment="test",
        auth_jwks_url="https://example.supabase.co/auth/v1/.well-known/jwks.json",
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
    )


def make_client(
    private_key: rsa.RSAPrivateKey,
    memberships: dict[UUID, Membership],
    invitations: FakeInvitations | None = None,
) -> TestClient:
    settings = make_settings()
    signing_key_loader = FixedSigningKey(private_key.public_key())
    auth_services = AuthServices(
        validator=JwtValidator(settings, signing_key_loader=signing_key_loader),
        memberships=FakeMemberships(memberships),
    )
    return TestClient(
        create_app(
            settings,
            auth_services=auth_services,
            invitation_service=InvitationService(gateway=invitations or FakeInvitations()),
        )
    )


def make_token(
    private_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey,
    subject_id: UUID,
    *,
    expires_at: datetime | None = None,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(
        {
            "sub": str(subject_id),
            "iss": issuer,
            "aud": audience,
            "exp": expires_at or datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm=algorithm,
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_protected_route_returns_401_without_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = make_client(private_key, {})

    response = client.get("/auth/session")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_signature_expiration_issuer_and_audience_fail_with_401() -> None:
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject_id = uuid4()
    client = make_client(signing_key, {subject_id: Membership(ORGANIZATION_ID, Role.ANALYST)})
    invalid_tokens = [
        make_token(other_key, subject_id),
        make_token(signing_key, subject_id, expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        make_token(signing_key, subject_id, issuer="https://other.example/auth/v1"),
        make_token(signing_key, subject_id, audience="other-audience"),
    ]

    for token in invalid_tokens:
        response = client.get("/auth/session", headers=bearer(token))
        assert response.status_code == 401


def test_authenticated_subject_without_membership_returns_403() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = make_client(private_key, {})

    response = client.get("/auth/session", headers=bearer(make_token(private_key, uuid4())))

    assert response.status_code == 403


def test_removing_membership_denies_an_already_issued_token_offline() -> None:
    """El JWT sigue firmado, pero cada solicitud vuelve a resolver permisos."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject_id = uuid4()
    memberships = {subject_id: Membership(ORGANIZATION_ID, Role.ANALYST)}
    client = make_client(private_key, memberships)
    headers = bearer(make_token(private_key, subject_id))

    assert client.get("/auth/session", headers=headers).status_code == 200
    del memberships[subject_id]
    assert client.get("/auth/session", headers=headers).status_code == 403


def test_paused_provider_response_fails_closed_with_503_offline(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject_id = uuid4()
    settings = Settings(
        environment="test",
        auth_jwks_url="https://example.supabase.co/auth/v1/.well-known/jwks.json",
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="test-only-publishable-key",
    )

    def paused_response(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        return httpx.Response(540, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.auth.httpx.get", paused_response)
    services = AuthServices(
        validator=JwtValidator(
            settings, signing_key_loader=FixedSigningKey(private_key.public_key())
        ),
        memberships=SupabaseMembershipResolver(settings),
    )
    client = TestClient(create_app(settings, auth_services=services))

    response = client.get("/auth/session", headers=bearer(make_token(private_key, subject_id)))

    assert response.status_code == 503
    assert "test-only-publishable-key" not in response.text


def test_unavailable_jwks_returns_503_instead_of_invalid_token_401() -> None:
    class UnavailableSigningKey:
        def __call__(self, encoded_token: str) -> object:
            del encoded_token
            raise PyJWKClientConnectionError("JWKS temporarily unavailable")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    services = AuthServices(
        validator=JwtValidator(make_settings(), signing_key_loader=UnavailableSigningKey()),
        memberships=FakeMemberships({}),
    )
    client = TestClient(create_app(make_settings(), auth_services=services))

    response = client.get("/auth/session", headers=bearer(make_token(private_key, uuid4())))

    assert response.status_code == 503
    assert "JWKS temporarily unavailable" not in response.text


def test_admin_can_create_resend_and_revoke_with_fake_gateway_offline() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    administrator_id = uuid4()
    invitations = FakeInvitations()
    client = make_client(
        private_key,
        {administrator_id: Membership(ORGANIZATION_ID, Role.ADMINISTRATOR)},
        invitations,
    )
    token_headers = bearer(make_token(private_key, administrator_id))
    invitation_id = UUID("00000000-0000-0000-0000-000000000099")

    created = client.post(
        "/auth/invitations", headers=token_headers, json={"email": "user@example.com"}
    )
    resent = client.post(f"/auth/invitations/{invitation_id}/resend", headers=token_headers)
    revoked = client.delete(f"/auth/invitations/{invitation_id}", headers=token_headers)

    assert created.status_code == 202
    assert created.json() == {"invitation_id": str(invitation_id), "status": "sent"}
    assert resent.json()["status"] == "resent"
    assert revoked.json()["status"] == "revoked"
    assert invitations.created == [("user@example.com", ORGANIZATION_ID, administrator_id)]
    assert invitations.resent == [(invitation_id, ORGANIZATION_ID, administrator_id)]
    assert invitations.revoked == [(invitation_id, ORGANIZATION_ID, administrator_id)]


def test_unsupported_resend_is_not_reported_as_success() -> None:
    class UnsupportedResend(FakeInvitations):
        def resend(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
            del invitation_id, organization_id, actor_id
            raise InvitationResendUnsupported

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    administrator_id = uuid4()
    client = make_client(
        private_key,
        {administrator_id: Membership(ORGANIZATION_ID, Role.ADMINISTRATOR)},
        UnsupportedResend(),
    )

    response = client.post(
        f"/auth/invitations/{uuid4()}/resend",
        headers=bearer(make_token(private_key, administrator_id)),
    )

    assert response.status_code == 501


def test_es256_token_from_a_recent_supabase_project_is_accepted() -> None:
    signing_key = ec.generate_private_key(ec.SECP256R1())
    subject_id = uuid4()
    settings = make_settings()
    auth_services = AuthServices(
        validator=JwtValidator(
            settings, signing_key_loader=FixedSigningKey(signing_key.public_key())
        ),
        memberships=FakeMemberships({subject_id: Membership(ORGANIZATION_ID, Role.ANALYST)}),
    )
    client = TestClient(create_app(settings, auth_services=auth_services))

    response = client.get(
        "/auth/session",
        headers=bearer(make_token(signing_key, subject_id, algorithm="ES256")),
    )

    assert response.status_code == 200


def test_analyst_cannot_create_invitation_or_escalate_a_role_from_payload() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    analyst_id = uuid4()
    administrator_id = uuid4()
    invitations = FakeInvitations()
    client = make_client(
        private_key,
        {
            analyst_id: Membership(ORGANIZATION_ID, Role.ANALYST),
            administrator_id: Membership(ORGANIZATION_ID, Role.ADMINISTRATOR),
        },
        invitations,
    )

    analyst_response = client.post(
        "/auth/invitations",
        headers=bearer(make_token(private_key, analyst_id)),
        json={"email": "user@example.com"},
    )
    manipulated_payload = client.post(
        "/auth/invitations",
        headers=bearer(make_token(private_key, administrator_id)),
        json={
            "email": "user@example.com",
            "role": "administrador",
            "organization_id": str(OTHER_ORGANIZATION_ID),
        },
    )

    assert analyst_response.status_code == 403
    assert manipulated_payload.status_code == 422
    assert invitations.created == []


def test_member_cannot_access_a_resource_in_another_organization() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    analyst_id = uuid4()
    client = make_client(private_key, {analyst_id: Membership(ORGANIZATION_ID, Role.ANALYST)})

    response = client.get(
        f"/auth/organizations/{OTHER_ORGANIZATION_ID}/session",
        headers=bearer(make_token(private_key, analyst_id)),
    )

    assert response.status_code == 403


def test_supabase_membership_mock_uses_verified_user_token_and_renders_one_membership(
    monkeypatch,
) -> None:
    subject_id = uuid4()
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            200,
            json=[{"organization_id": str(ORGANIZATION_ID), "role": "analista"}],
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("app.auth.httpx.get", fake_get)
    resolver = SupabaseMembershipResolver(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-only-publishable-key",
        )
    )

    membership = resolver.resolve(subject_id, "verified-test-token")

    assert membership == Membership(ORGANIZATION_ID, Role.ANALYST)
    assert captured["params"] == {
        "user_id": f"eq.{subject_id}",
        "select": "organization_id,role",
    }
    assert captured["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer verified-test-token",
        "apikey": "test-only-publishable-key",
    }


def test_service_key_is_not_exposed_by_health_or_openapi() -> None:
    settings = Settings(supabase_service_role_key="test-only-service-key")
    client = TestClient(create_app(settings))

    assert "test-only-service-key" not in repr(settings)
    assert "test-only-service-key" not in client.get("/health").text
    assert "supabase_service_role_key" not in client.get("/openapi.json").text
