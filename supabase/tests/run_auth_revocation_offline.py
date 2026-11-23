"""Verifica la RPC en PostgreSQL local con la imagen Docker ya instalada."""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from uuid import uuid4

SUPABASE_DIR = Path(__file__).resolve().parents[1]
IMAGE = "postgres:17.6-bookworm"
LABEL = "eag.auth-revoke-test"
BOOTSTRAP = """
create role anon;
create role authenticated;
create role service_role bypassrls;
create schema auth;
create table auth.users (id uuid primary key, email text not null);
create function auth.uid() returns uuid language sql stable
as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--legacy", action="store_true", help="Reproduce el fallo con las migraciones originales."
    )
    args = parser.parse_args()
    migrations = sorted((SUPABASE_DIR / "migrations").glob("*.sql"))
    if args.legacy:
        migrations = [path for path in migrations if path.name < "20261122000000"]
    test = SUPABASE_DIR / "tests" / "auth_revocation_retry.sql"
    statements = "\n".join(
        [BOOTSTRAP, *(path.read_text(encoding="utf-8") for path in [*migrations, test])]
    )
    owner = uuid4().hex
    container = f"eag-auth-revoke-test-{owner}"
    try:
        subprocess.run(
            ["docker", "run", "--detach", "--pull=never", "--name", container,
             "--label", f"{LABEL}={owner}", "--network", "none",
             "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
             "--tmpfs", "/var/lib/postgresql/data:rw", IMAGE],
            check=True, stdout=subprocess.DEVNULL, timeout=30,
        )
        deadline = time.monotonic() + 30
        while subprocess.run(
            ["docker", "exec", container, "pg_isready", "-q", "-h", "127.0.0.1", "-U", "postgres"],
            timeout=5,
        ).returncode:
            if time.monotonic() >= deadline:
                raise RuntimeError("PostgreSQL local no está listo")
            time.sleep(0.3)
        print("PostgreSQL local sin red; migraciones y fixture de revocación", flush=True)
        result = subprocess.run(
            ["docker", "exec", "-i", container, "psql", "-X", "-q",
             "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1"],
            input=statements.encode("utf-8"), timeout=30,
        )
        return result.returncode
    finally:
        result = subprocess.run(
            ["docker", "inspect", "--format", f'{{{{index .Config.Labels "{LABEL}"}}}}', container],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            if result.stdout.strip() != owner:
                raise RuntimeError("El contenedor no pertenece a esta prueba")
            subprocess.run(
                ["docker", "rm", "--force", "--volumes", container],
                check=True, stdout=subprocess.DEVNULL, timeout=10,
            )
            print("Fixture de PostgreSQL retirada", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
