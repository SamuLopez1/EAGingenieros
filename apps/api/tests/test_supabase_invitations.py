from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from app.config import Settings
from app.invitations import (
    InvitationAuthorizationError,
    InvitationProviderUnavailable,
    InvitationResendUnsupported,
    SupabaseInvitationGateway,
)

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000010")
PROVIDER_USER_ID = UUID("00000000-0000-0000-0000-000000000020")
INVITATION_ID = UUID("00000000-0000-0000-0000-000000000030")


def make_gateway() -> SupabaseInvitationGateway:
    return SupabaseInvitationGateway(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="test-only-service-key",
            supabase_invite_redirect_url="http://127.0.0.1:5173",
        )
    )


def response(
    method: str, url: str, status_code: int, payload: object | None = None
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request(method, url),
    )


def test_create_invitation_calls_auth_then_atomic_rpc_without_exposing_service_key(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        calls.append((method, url, kwargs))
        if url.endswith("/auth/v1/invite"):
            return response(method, url, 200, {"id": str(PROVIDER_USER_ID)})
        assert url.endswith("/rest/v1/rpc/record_eag_invitation")
        return response(method, url, 204)

    monkeypatch.setattr("app.invitations.httpx.request", fake_request)

    created_id = make_gateway().create(
        email="analyst@example.test", organization_id=ORGANIZATION_ID, actor_id=ACTOR_ID
    )

    assert isinstance(created_id, UUID)
    assert [call[0] for call in calls] == ["POST", "POST"]
    assert calls[0][2]["params"] == {"redirect_to": "http://127.0.0.1:5173/"}
    assert calls[0][2]["json"] == {"email": "analyst@example.test", "data": {}}
    assert calls[1][2]["json"] == {
        "p_invitation_id": str(created_id),
        "p_provider_user_id": str(PROVIDER_USER_ID),
        "p_organization_id": str(ORGANIZATION_ID),
        "p_email": "analyst@example.test",
        "p_actor_id": str(ACTOR_ID),
    }
    assert "test-only-service-key" not in repr(calls[0][1])


def test_create_invitation_deletes_provider_user_when_atomic_record_fails(monkeypatch) -> None:
    calls: list[str] = []

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        calls.append(f"{method} {url}")
        if url.endswith("/auth/v1/invite"):
            return response(method, url, 200, {"id": str(PROVIDER_USER_ID)})
        if url.endswith("record_eag_invitation"):
            return response(method, url, 500)
        return response(method, url, 204)

    monkeypatch.setattr("app.invitations.httpx.request", fake_request)

    with pytest.raises(InvitationProviderUnavailable):
        make_gateway().create(
            email="analyst@example.test", organization_id=ORGANIZATION_ID, actor_id=ACTOR_ID
        )

    assert calls[-1].endswith(f"/auth/v1/admin/users/{PROVIDER_USER_ID}")


def test_revoke_requires_same_organization_then_removes_access_before_auth_user(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        calls.append(f"{method} {url}")
        if url.endswith("/rest/v1/invitations"):
            return response(method, url, 200, [{"provider_user_id": str(PROVIDER_USER_ID)}])
        return response(method, url, 204)

    monkeypatch.setattr("app.invitations.httpx.request", fake_request)

    make_gateway().revoke(
        invitation_id=INVITATION_ID, organization_id=ORGANIZATION_ID, actor_id=ACTOR_ID
    )

    assert calls == [
        "GET https://example.supabase.co/rest/v1/invitations",
        "POST https://example.supabase.co/rest/v1/rpc/revoke_eag_invitation",
        f"DELETE https://example.supabase.co/auth/v1/admin/users/{PROVIDER_USER_ID}",
    ]


def test_revoke_and_resend_do_not_cross_organization_boundaries(monkeypatch) -> None:
    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        assert method == "GET"
        assert url.endswith("/rest/v1/invitations")
        return response(method, url, 200, [])

    monkeypatch.setattr("app.invitations.httpx.request", fake_request)
    gateway = make_gateway()

    with pytest.raises(InvitationAuthorizationError):
        gateway.revoke(
            invitation_id=INVITATION_ID,
            organization_id=UUID("00000000-0000-0000-0000-000000000002"),
            actor_id=ACTOR_ID,
        )
    with pytest.raises(InvitationAuthorizationError):
        gateway.resend(
            invitation_id=INVITATION_ID,
            organization_id=UUID("00000000-0000-0000-0000-000000000002"),
            actor_id=ACTOR_ID,
        )


def test_resend_is_explicitly_unsupported_when_the_invitation_belongs_to_eag(monkeypatch) -> None:
    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        assert method == "GET"
        return response(method, url, 200, [{"provider_user_id": str(PROVIDER_USER_ID)}])

    monkeypatch.setattr("app.invitations.httpx.request", fake_request)

    with pytest.raises(InvitationResendUnsupported):
        make_gateway().resend(
            invitation_id=INVITATION_ID, organization_id=ORGANIZATION_ID, actor_id=ACTOR_ID
        )
