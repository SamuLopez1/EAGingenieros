"""Verificación HTTPS, de solo lectura, con cuentas autorizadas de staging."""

import argparse
import json
import os
import sys
from uuid import UUID

import httpx

from app.auth import Role

PROFILE = "/api/v1/company-profile"
CATALOG = "/api/v1/opportunities?limit=1"
SESSION = "/auth/session"


def check_access(
    client: httpx.Client,
    analyst: str,
    admin: str,
    report: str | None = None,
) -> dict[str, int]:
    results: dict[str, int] = {}

    def check(label: str, path: str, status: int, token: str = "") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with client.stream("GET", path, headers=headers) as response:
            results[label] = response.status_code
            if response.status_code != status:
                raise SmokeFailure(
                    f"{label}: se esperaba {status}, se recibió {response.status_code}"
                )
            if status == 200 and path not in (SESSION, CATALOG):
                if "no-store" not in response.headers.get("Cache-Control", ""):
                    raise SmokeFailure(f"{label}: falta control de caché privado.")
            if status == 200 and path == SESSION:
                response.read()
            return response

    check("anonimo_sesion", SESSION, 401)
    check("anonimo_catalogo", CATALOG, 401)
    check("anonimo_perfil", PROFILE, 401)
    orgs: set[UUID] = set()
    users: set[UUID] = set()
    for label, token, role in (
        ("analista", analyst, Role.ANALYST),
        ("administrador", admin, Role.ADMINISTRATOR),
    ):
        session = check(f"{label}_sesion", SESSION, 200, token).json()
        if session["role"] != role.value:
            raise SmokeFailure(f"{label}: rol inesperado.")
        org = UUID(session["organization_id"])
        orgs.add(org)
        users.add(UUID(session["subject_id"]))
        foreign_id = UUID(int=org.int ^ 1)
        check(
            f"{label}_organizacion_ajena", f"/auth/organizations/{foreign_id}/session", 403, token
        )
        check(f"{label}_catalogo", CATALOG, 200, token)
        check(f"{label}_perfil", PROFILE, 200, token)
    if len(orgs) != 1 or len(users) != 2:
        raise SmokeFailure("Se requieren dos cuentas distintas de la misma organización.")
    if report is not None:
        check("anonimo_informe", report, 401)
        check("analista_informe", report, 200, analyst)
        check("analista_bandeja", f"{report}/mail", 403, analyst)
        check("administrador_bandeja", f"{report}/mail", 200, admin)
    return results


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("se requiere un entero positivo")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opportunity", type=positive_int)
    parser.add_argument("--revision", type=positive_int)
    args = parser.parse_args()
    if (args.opportunity is None) != (args.revision is None):
        parser.error("Indica juntos --opportunity y --revision.")
    names = ("EAG_STAGING_API_URL", "EAG_STAGING_ANALYST_TOKEN", "EAG_STAGING_ADMIN_TOKEN")
    values = {name: os.environ.get(name, "").strip() for name in names}
    endpoint, analyst, admin = values.values()
    if not (endpoint and analyst and admin):
        print(
            "staging: faltan " + ", ".join(name for name in names if not values[name]),
            file=sys.stderr,
        )
        return 2
    try:
        origin = httpx.URL(endpoint)
        if (
            origin.scheme != "https"
            or not origin.host
            or origin.userinfo
            or origin.query
            or origin.fragment
            or origin.path not in ("", "/")
        ):
            print("staging: indica el origen HTTPS autorizado de la API.", file=sys.stderr)
            return 2
        report = (
            f"/api/v1/opportunities/{args.opportunity}/reports/{args.revision}"
            if args.opportunity is not None
            else None
        )
        with httpx.Client(
            base_url=origin,
            timeout=8.0,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            print(json.dumps(check_access(client, analyst, admin, report), sort_keys=True))
        return 0
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        # No imprimir cuerpos, URLs ni identificadores devueltos por el servidor.
        message = str(error) if isinstance(error, SmokeFailure) else "respuesta o conexión inválida"
        print(f"staging: {message}", file=sys.stderr)
        return 1


class SmokeFailure(ValueError):
    """Solo mensajes construidos localmente con los estados de las comprobaciones."""


if __name__ == "__main__":
    raise SystemExit(main())
