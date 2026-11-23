"""QA local del catálogo: PostgreSQL, proxy Vite e identidad sintética.

Por defecto usa solo fixtures. --public sincroniza exactamente dos procesos de
SECOP II y comprueba sus enlaces sin guardar las filas ni descargar adjuntos.
"""

import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--public", action="store_true", help="Prueba acotada con SECOP real")
    parser.add_argument("--browser-cli", type=Path, help="Ruta a playwright-cli.js")
    parser.add_argument("--dossier", action="store_true", help="Prueba A/B/A con archivos sintéticos")
    parser.add_argument("--extraction", action="store_true", help="Incluye extracción y fallos en la prueba A/B/A")
    parser.add_argument("--comparison", action="store_true", help="Compara dos expedientes sintéticos")
    parser.add_argument("--staffing", action="store_true", help="Verifica encaje y personal sintético")
    parser.add_argument("--margin", action="store_true", help="Verifica escenarios de margen sintéticos")
    parser.add_argument("--shortlist", action="store_true", help="Verifica la lista corta sintética")
    args = parser.parse_args()
    if args.shortlist and not args.margin:
        parser.error("--shortlist requiere --margin")
    if args.margin and not args.staffing:
        parser.error("--margin requiere --staffing")
    if args.staffing and not args.comparison:
        parser.error("--staffing requiere --comparison")
    if args.comparison and not args.extraction:
        parser.error("--comparison requiere --extraction")
    if args.extraction and (not args.dossier or not args.browser_cli):
        parser.error("--extraction requiere --dossier y --browser-cli")
    if args.dossier and args.public:
        parser.error("--dossier usa únicamente datos sintéticos")
    assert 1 <= args.duration <= 3600
    ui_port, api_port = 15176, 18106
    for port in (api_port, ui_port, 18116):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    for key in tuple(os.environ):
        if key.startswith(("EAG_", "VITE_", "LANGCHAIN_", "LANGSMITH_")):
            os.environ.pop(key)

    import httpx
    import jwt
    import uvicorn
    from alembic import command
    from alembic.config import Config
    from app.config import Settings

    Settings.model_config["env_file"] = None
    from app.db.filter_models import SavedOpportunityFilter
    from app.db.models import Opportunity, SyncRun
    from app.db.repository import SqlOpportunityRepository
    from app.main import create_app
    from app.secop.client import normalise_record
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from jwt.algorithms import RSAAlgorithm
    from pydantic import SecretStr
    from sqlalchemy import URL, create_engine, text, update
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    from starlette.responses import JSONResponse

    public_url = "http://127.0.0.1:18116"
    public_key = "synthetic-public-key"
    organization = UUID(int=1)
    token = uuid4().hex
    container = f"eag-mvp06-qa-{token}"
    database = f"mvp06_{token}"
    servers: list[uvicorn.Server] = []
    vite = None
    vite_config = None
    engine = None
    extraction_stop = threading.Event()
    extraction_thread = None

    def docker(*parts: str) -> str:
        try:
            result = subprocess.run(
                ["docker", *parts],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Docker {parts[0]} excedió 30s") from None
        if result.returncode:
            raise RuntimeError(f"Docker {parts[0]} falló")
        return result.stdout.strip()

    def serve(app: FastAPI, port: int) -> None:
        server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=port, access_log=False, log_level="warning"
            )
        )
        servers.append(server)
        threading.Thread(target=server.run, daemon=True).start()

    try:
        password = secrets.token_hex(24)
        docker(
            "run",
            "--detach",
            "--pull=never",
            "--name",
            container,
            "--label",
            f"eag.mvp06.qa={token}",
            "--publish",
            "127.0.0.1::5432",
            "--env",
            f"POSTGRES_DB={database}",
            "--env",
            "POSTGRES_USER=synthetic",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "--tmpfs",
            "/var/lib/postgresql/data",
            "postgres:17.6-bookworm",
        )
        print(f"QA_CONTAINER {container}", flush=True)
        port = int(docker("port", container, "5432/tcp").removeprefix("127.0.0.1:"))
        url = URL.create(
            "postgresql+psycopg",
            username="synthetic",
            password=password,
            host="127.0.0.1",
            port=port,
            database=database,
            query={"connect_timeout": "3", "options": "-c statement_timeout=5000"},
        )
        engine = create_engine(url)
        deadline = time.monotonic() + 45
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                break
            except OperationalError:
                if time.monotonic() > deadline:
                    raise RuntimeError("PostgreSQL no arrancó en 45s") from None
                time.sleep(0.3)
        os.environ["EAG_DATABASE_URL"] = url.render_as_string(hide_password=False)
        command.upgrade(Config(str(ROOT / "apps/api/alembic.ini")), "head")
        if args.comparison:
            seed_comparison_profile(engine, organization, staffing=args.staffing)
        if args.public:
            synchronize_public(engine)
        else:
            with Session(engine) as session:
                now = datetime.now(UTC)
                validity_cases = {
                    0: {"fase": "Adjudicación"},
                    3: {
                        "fase": "Presentación de oferta",
                        "fecha_de_recepcion_de": (now + timedelta(days=2)).isoformat(),
                    },
                    6: {
                        "fase": "Presentación de oferta",
                        "fecha_de_recepcion_de": (now - timedelta(days=2)).isoformat(),
                    },
                    9: {"fase": "Presentación de oferta"},
                }
                records = []
                for index in range(64):
                    record = normalise_record(
                        {
                            "id_del_proceso": f"SYNTH-{index:03}",
                            "referencia_del_proceso": f"QA-{index:03}",
                            "nombre_del_procedimiento": f"Diseño e interventoría de puente · caso sintético {index:03}",
                            "entidad": "Entidad Norte (sintética)"
                            if index < 48
                            else "Entidad Sur (sintética)",
                            "estado_del_procedimiento": "Publicado"
                            if index % 4
                            else "Adjudicado",
                            "modalidad_de_contratacion": "Concurso de méritos"
                            if index % 3
                            else "Contratación directa",
                            "fecha_de_publicacion_del": f"2026-09-{1 + index % 20:02}T10:00:00Z",
                            "fecha_de_ultima_publicaci": "2026-10-01T12:00:00Z",
                            "departamento_entidad": "Antioquia" if index < 48 else "Valle del Cauca",
                            "ciudad_entidad": "Medellín" if index < 48 else "Cali",
                            "urlproceso": {
                                "url": f"https://community.secop.gov.co/synthetic/SYNTH-{index:03}"
                            },
                            **({"precio_base": "800"} if args.margin and index == 3 else {}),
                            **validity_cases.get(index, {}),
                        },
                        fetched_at=datetime(2026, 10, 1, tzinfo=UTC),
                    )
                    assert record is not None
                    records.append(record)
                SqlOpportunityRepository(session).upsert_many(records)
                # Escenario conocido de auditoría: carga correcta pero antigua.
                loaded = now - timedelta(hours=25)
                session.execute(
                    update(Opportunity).values(first_seen_at=loaded, last_synced_at=loaded)
                )
                session.add(
                    SyncRun(
                        dataset="p6dx-8zbt",
                        trigger="synthetic_qa",
                        outcome="completed",
                        started_at=loaded,
                        finished_at=loaded,
                        records_seen=64,
                        records_created=64,
                    )
                )
                session.add(
                    SavedOpportunityFilter(
                        organization_id=organization,
                        name="Puentes publicados · sintético",
                        criteria={"q": "puente", "status": "Publicado"},
                    )
                )
                session.commit()

        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
        jwk.update(kid="mvp06-qa", alg="RS256", use="sig")
        issuer = "http://127.0.0.1:18116/auth/v1"
        provider = FastAPI()
        provider.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:15176"],
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

        def identity(subject: str) -> dict[str, object]:
            return {
                "id": subject,
                "email": "admin@fixture.invalid"
                if subject == str(UUID(int=2))
                else "analista@fixture.invalid",
                "aud": "authenticated",
                "role": "authenticated",
                "created_at": "2026-01-01T00:00:00Z",
                "app_metadata": {"provider": "email"},
                "user_metadata": {},
            }

        @provider.get("/auth/v1/.well-known/jwks.json")
        def jwks() -> dict[str, object]:
            return {"keys": [jwk]}

        @provider.post("/auth/v1/token")
        async def sign_in(request: Request) -> dict[str, object]:
            body = await request.json()
            if body.get("password") != "Synthetic-Only-06":
                raise HTTPException(400, "Credenciales sintéticas incorrectas")
            email = body.get("email")
            if email not in ("admin@fixture.invalid", "analista@fixture.invalid"):
                raise HTTPException(400, "Usuario sintético desconocido")
            subject = str(UUID(int=2 if email == "admin@fixture.invalid" else 3))
            now = datetime.now(UTC)
            access = jwt.encode(
                {
                    "sub": subject,
                    "aud": "authenticated",
                    "iss": issuer,
                    "iat": now,
                    "exp": now + timedelta(hours=1),
                },
                private,
                algorithm="RS256",
                headers={"kid": "mvp06-qa"},
            )
            return {
                "access_token": access,
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": "synthetic-refresh",
                "user": identity(subject),
            }

        def subject(request: Request) -> str:
            access = request.headers.get("authorization", "").removeprefix("Bearer ")
            try:
                return str(
                    jwt.decode(
                        access,
                        private.public_key(),
                        algorithms=["RS256"],
                        audience="authenticated",
                        issuer=issuer,
                    )["sub"]
                )
            except jwt.InvalidTokenError:
                raise HTTPException(401) from None

        @provider.get("/auth/v1/user")
        def user(request: Request) -> dict[str, object]:
            return identity(subject(request))

        @provider.post("/auth/v1/logout", status_code=204)
        def logout() -> Response:
            return Response(status_code=204)

        @provider.get("/rest/v1/organization_memberships")
        def membership(request: Request) -> list[dict[str, str]]:
            sid = subject(request)
            if request.query_params.get("user_id") != f"eq.{sid}":
                return []
            return [
                {
                    "organization_id": str(UUID(int=1)),
                    "role": "administrador" if sid == str(UUID(int=2)) else "analista",
                }
            ]

        serve(provider, 18116)
        auth_config = {
            "supabase_url": public_url,
            "supabase_publishable_key": SecretStr(public_key),
            "auth_jwks_url": f"{issuer}/.well-known/jwks.json",
            "auth_issuer": issuer,
            "auth_audience": "authenticated",
        }
        settings = Settings(
            _env_file=None,
            database_url=SecretStr(url.render_as_string(hide_password=False)),
            document_download_secret=SecretStr(secrets.token_hex(32)) if args.dossier else None,
            extraction_timeout_seconds=15 if args.extraction else 90,
            **auth_config,
        )
        app = create_app(settings)
        if args.dossier:
            from dataclasses import replace

            class FixtureScanner:
                engine = "fixture"
                available = True

                def scan(self, payload: bytes) -> tuple[bool, str | None]:
                    return payload.startswith(b"%PDF-1.4\n% EAG-QA-"), None

            app.state.document_services = replace(
                app.state.document_services, scanner=FixtureScanner()
            )

        if args.extraction:
            from app.db.session import create_session_factory
            from app.documents.extraction_worker import run_one

            factory = create_session_factory(engine)

            def consume_extractions() -> None:
                while not extraction_stop.is_set():
                    if not run_one(factory, settings):
                        extraction_stop.wait(0.2)

            extraction_thread = threading.Thread(target=consume_extractions, daemon=True)
            extraction_thread.start()

        @app.middleware("http")
        async def prevent_secop(request: Request, call_next):
            if request.method == "POST" and request.url.path == "/api/v1/sync-runs":
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "SECOP deshabilitado en este entorno de validación"
                    },
                )
            return await call_next(request)

        serve(app, api_port)
        label = (
            "QA: SECOP público sincronizado · PostgreSQL local · identidad sintética"
            if args.public
            else "QA: catálogo e identidad sintéticos · PostgreSQL local"
        )
        # Config temporal propia: rótulo visible también antes del login, sin cambiar App/auth.
        output = ROOT / "output/playwright"
        output.mkdir(parents=True, exist_ok=True)
        vite_config = output / f"validation-{token}.mjs"
        vite_config.write_text(
            f"import base from {json.dumps((ROOT / 'apps/web/vite.config.ts').as_uri())};\n"
            "export default { ...base, envDir: false, plugins: [...base.plugins, { name: 'validation-label', "
            "transformIndexHtml() { return [{tag:'div', attrs:{role:'note', style:'padding:12px;background:#fff1ba;color:#302400;font:16px system-ui;'}, children:"
            + json.dumps(label)
            + ", injectTo:'body-prepend'}]; } }] };\n",
            encoding="utf-8",
        )
        env = dict(
            os.environ,
            VITE_SUPABASE_URL=public_url,
            VITE_SUPABASE_PUBLISHABLE_KEY=public_key,
            VITE_API_PROXY_TARGET=f"http://127.0.0.1:{api_port}",
        )
        vite = subprocess.Popen(
            [
                "node",
                str(ROOT / "apps/web/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                str(ui_port),
                "--strictPort",
                "--config",
                str(vite_config),
            ],
            cwd=ROOT / "apps/web",
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        # No anunciar el entorno hasta verificar la UI y su proxy hacia esta API.
        ready_deadline = time.monotonic() + 20
        origin = f"http://127.0.0.1:{ui_port}"
        with httpx.Client(timeout=2, trust_env=False) as probe:
            while time.monotonic() < ready_deadline and vite.poll() is None:
                try:
                    health = probe.get(f"{origin}/api/health")
                    page = probe.get(origin)
                    if (
                        health.is_success
                        and health.json().get("status") == "ok"
                        and page.is_success
                        and label in page.text
                    ):
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("La UI, el proxy o la persistencia QA no arrancaron en 20s")
        print(
            f"QA_READY http://127.0.0.1:{ui_port} ({label}); duración {args.duration}s",
            flush=True,
        )
        if args.browser_cli:
            browser = ["node", str(args.browser_cli.resolve()), f"-s=eag-mvp06-{token}"]
            browser_output = output / f"catalog-{token}"
            browser_output.mkdir()
            check_script = str(ROOT / "scripts" / (
                "mvp07_browser_check.js" if args.dossier else "mvp06_browser_check.js"
            ))
            try:
                query = "?qa_comparison=1" if args.comparison else "?qa_extraction=1"
                if args.staffing:
                    query += "&qa_staffing=1"
                if args.margin:
                    query += "&qa_margin=1"
                if args.shortlist:
                    query += "&qa_shortlist=1"
                url = origin + (query if args.extraction else "")
                subprocess.run([*browser, "open", url, "--browser=chrome"],
                               check=True, stdout=subprocess.DEVNULL, timeout=35, cwd=browser_output)
                checked = subprocess.run(
                    [*browser, "run-code", "--filename", check_script],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    check=False, timeout=120 if args.shortlist else 90, cwd=browser_output,
                )
                result = re.search(r'^"?QA_BROWSER_OK ([a-z0-9= ]+)"?$', checked.stdout, re.M)
                if checked.returncode or not result:
                    if not args.public:
                        print(checked.stdout[-4000:], checked.stderr[-2000:], flush=True)
                    raise RuntimeError("El recorrido del navegador no se completó.")
                print(f"QA_BROWSER_OK {result[1]}", flush=True)
            finally:
                subprocess.run([*browser, "close"], check=False, stdout=subprocess.DEVNULL,
                               timeout=15, cwd=browser_output)
            return
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            if vite.poll() is not None:
                raise RuntimeError("Vite terminó antes de completar QA")
            time.sleep(1)
    finally:
        if vite is not None and vite.poll() is None:
            vite.terminate()
            vite.wait(timeout=10)
        if vite_config is not None:
            vite_config.unlink(missing_ok=True)
        for server in servers:
            server.should_exit = True
        extraction_stop.set()
        if extraction_thread is not None:
            extraction_thread.join(timeout=22)
        if engine is not None:
            engine.dispose()
        ownership = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                '{{ index .Config.Labels "eag.mvp06.qa" }}',
                container,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if ownership.returncode == 0:
            assert ownership.stdout.strip() == token
            docker("rm", "--force", "--volumes", container)
            print(f"QA_REMOVED {container}", flush=True)



def seed_comparison_profile(engine, organization, *, staffing: bool = False) -> None:
    from datetime import date
    from hashlib import sha256

    from sqlalchemy.orm import Session

    from app.db.models import utcnow
    from app.db.profile_models import ProfileEvidence, ProfileVersion
    from app.profile import Entry, EvidenceReference

    now = utcnow()
    entries = []
    with Session(engine) as session:
        for label, title, amount in (
            ("A", "Experiencia vial", 12), ("B", "Experiencia hidrica", 6),
        ):
            payload = f"%PDF-1.4\n% EAG-QA-PERFIL-{label}\n%%EOF\n".encode()
            doc_id = uuid4()
            session.add(ProfileEvidence(
                id=doc_id, organization_id=organization, author_id=UUID(int=2),
                created_at=now, filename=f"perfil-{label}.pdf",
                sha256=sha256(payload).hexdigest(), payload=payload,
            ))
            entries.append(Entry(
                category="experiencia", title=title, status="verificado", amount=amount,
                service_line="Consultoría vial" if staffing and label == "A" else None,
                unit="meses", evidence=[EvidenceReference(document_id=doc_id, locator="Página 1")],
            ).model_dump(mode="json"))
        if staffing:
            entries.append(Entry(
                category="disponibilidad", title="Disponibilidad sintética", role="Residente",
                status="verificado", dedication_percent=80, starts_on=date(2026, 12, 1),
                ends_on=date(2026, 12, 30),
                evidence=[EvidenceReference(document_id=doc_id, locator="Página 1")],
            ).model_dump(mode="json"))
        session.add(ProfileVersion(
            organization_id=organization, version=1, author_id=UUID(int=2),
            created_at=now, entries=entries,
        ))
        session.commit()


def synchronize_public(engine) -> None:
    from collections.abc import Mapping
    from typing import Any

    import httpx
    from sqlalchemy.orm import Session

    from app.db.repository import SqlOpportunityRepository
    from app.db.sync_service import SyncRequest, SyncService
    from app.secop.client import (
        PROCESSES_DATASET,
        SOCRATA_ROOT,
        SecopClient,
    )

    endpoint = f"{SOCRATA_ROOT}/resource/{PROCESSES_DATASET}.json"
    projection = (
        "id_del_proceso,referencia_del_proceso,nombre_del_procedimiento,entidad,"
        "estado_del_procedimiento,fase,modalidad_de_contratacion,fecha_de_publicacion_del,"
        "fecha_de_ultima_publicaci,fecha_de_recepcion_de,departamento_entidad,ciudad_entidad,"
        "urlproceso"
    )

    def official(value: str | None) -> bool:
        parts = urlsplit(value or "")
        return (
            parts.scheme == "https"
            and parts.netloc == "community.secop.gov.co"
            and parts.path.lower() == "/public/tendering/opportunitydetail/index"
            and bool(parse_qs(parts.query).get("noticeUID"))
        )

    with httpx.Client(timeout=12, trust_env=False, follow_redirects=False) as http:
        class PublicSample:
            def get(self, target: str, *, params: Mapping[str, Any], timeout: float):
                assert target == endpoint and int(params["$limit"]) <= 5
                return http.get(target, params={**params, "$select": projection}, timeout=timeout)

        sample = PublicSample()
        cutoff = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="milliseconds")
        scout = sample.get(endpoint, params={
            "$limit": 5,
            "$where": (
                "estado_del_procedimiento = 'Publicado' AND "
                f"fecha_de_recepcion_de > '{cutoff}' AND urlproceso IS NOT NULL AND "
                "ciudad_entidad IS NOT NULL AND modalidad_de_contratacion IS NOT NULL"
            ),
        }, timeout=12)
        print(f"SECOP_SCOUT_HTTP {scout.status_code}", flush=True)
        scout.raise_for_status()
        assert isinstance(scout.json(), list)
        candidates = []
        for row in scout.json():
            target = row.get("urlproceso")
            source_url = target.get("url") if isinstance(target, dict) else target
            if official(source_url):
                source_id = row["id_del_proceso"]
                if source_id not in candidates:
                    candidates.append(source_id)
            if len(candidates) == 2:
                break
        if len(candidates) != 2:
            raise RuntimeError("No se hallaron dos enlaces oficiales en la muestra acotada")

        with Session(engine, expire_on_commit=False) as session:
            repo = SqlOpportunityRepository(session)
            for index, source_id in enumerate(candidates, 1):
                outcome = SyncService(
                    client=SecopClient(http=sample, max_retries=0, max_requests=1, timeout=12),
                    repository=repo, session=session,
                ).run(SyncRequest(limit=1, filters={"id_del_proceso": source_id}))
                assert outcome.outcome == "completed" and outcome.records_created == 1
                stored = repo.get_by_source(PROCESSES_DATASET, source_id)
                assert stored is not None and stored.official_url and official(stored.official_url)
                assert stored.entity and stored.city and stored.modality and stored.reception_at
                try:
                    with http.stream("GET", stored.official_url) as result:
                        print(f"OFFICIAL_LINK_{index}_HTTP {result.status_code}", flush=True)
                except httpx.HTTPError as error:
                    print(f"OFFICIAL_LINK_{index}_TRANSPORT {type(error).__name__}", flush=True)
            assert repo.count() == 2
        print("SECOP_SYNC_CREATED 2", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as error:  # noqa: BLE001 - límite de proceso: no exponer secretos
        # No volcar configuración/URLs/credenciales ante errores de arranque.
        print(
            f"QA_FAILED {type(error).__name__}; comprobar infraestructura/configuración",
            flush=True,
        )
        sys.exit(1)
