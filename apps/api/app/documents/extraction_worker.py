"""Worker durable, con un proceso acotado por intento."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from time import sleep

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.session import create_engine_from_url, create_session_factory
from app.documents.extraction import Result, failed
from app.documents.extraction_jobs import Claim, claim_next, finish_claim
from app.operations.scratch import workspace

Processor = Callable[[Claim, Settings], Result]
MAX_RESULT_BYTES = 3_000_000


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if sys.platform != "win32":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    process.communicate()


def process_claim(claim: Claim, settings: Settings) -> Result:
    try:
        with workspace(settings.extraction_scratch_root) as scratch:
            return extract_in_workspace(claim, settings, scratch)
    except (OSError, ValueError):
        return failed("worker_fallido")


def extract_in_workspace(claim: Claim, settings: Settings, scratch: str) -> Result:
    # El parser no recibe tokens ni configuración de base de datos.
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATHEXT",
            "TESSDATA_PREFIX", "LANG", "LC_ALL",
        }
    }
    env.update(TMPDIR=scratch, TEMP=scratch, TMP=scratch, OMP_THREAD_LIMIT="1")
    try:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "app.documents.extraction_child", claim.format,
                settings.extraction_ocr_language, str(settings.extraction_ocr_max_pages),
                str(settings.document_max_bytes),
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=os.name == "posix",
        )
    except OSError:
        return failed("worker_fallido")
    try:
        stdout, _ = process.communicate(
            claim.payload, timeout=settings.extraction_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        stop_process(process)
        return failed("tiempo_agotado")
    except BaseException:
        stop_process(process)
        raise
    if process.returncode != 0 or len(stdout) > MAX_RESULT_BYTES:
        return failed("worker_fallido")
    try:
        return Result.model_validate_json(stdout)
    except ValidationError:
        return failed("worker_fallido")


def run_one(
    factory: sessionmaker[Session], settings: Settings, processor: Processor = process_claim,
) -> bool:
    with factory() as session:
        found, claim = claim_next(
            session, timeout=settings.extraction_timeout_seconds,
            max_bytes=settings.document_max_bytes,
        )
    if claim is None:
        return found
    result = processor(claim, settings)
    with factory() as session:
        finish_claim(session, claim, result)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Procesar solo una tarea pendiente")
    args = parser.parse_args()
    settings = Settings()
    if not settings.database_is_configured:
        parser.error("EAG_DATABASE_URL es requerida")
    engine = create_engine_from_url(settings.require_database_url())
    factory = create_session_factory(engine)
    try:
        while True:
            try:
                found = run_one(factory, settings)
            except SQLAlchemyError:
                if args.once:
                    print("worker: persistencia no disponible", file=sys.stderr)
                    return 1
                print("worker: persistencia no disponible", file=sys.stderr)
                sleep(5)
                continue
            if args.once:
                print("worker: tarea atendida" if found else "worker: sin tareas pendientes")
                return 0
            if not found:
                sleep(2)
    except KeyboardInterrupt:
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
