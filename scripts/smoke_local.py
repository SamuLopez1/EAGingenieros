#!/usr/bin/env python3
"""Comprueba la ruta local Vite (/api) -> FastAPI sin servicios externos."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"


def api_python() -> str:
    scripts = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    candidate = API_DIR / ".venv" / scripts
    if not candidate.exists():
        raise RuntimeError("API virtual environment is missing; follow README.md first")
    return str(candidate)


def node_command() -> str:
    return "node.exe" if os.name == "nt" else "node"


def wait_for(url: str, expected_status: int = 200) -> bytes:
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 - fixed localhost URLs
                if response.status == expected_status:
                    return response.read()
        except Exception as error:  # pragma: no cover - timing depends on local processes
            last_error = error
        time.sleep(0.25)
    raise RuntimeError(f"local service did not become ready: {url}; last error: {last_error}")


def main() -> int:
    environment = os.environ.copy()
    environment["VITE_API_PROXY_TARGET"] = "http://127.0.0.1:8000"
    api: subprocess.Popen[bytes] | None = None
    web: subprocess.Popen[bytes] | None = None
    try:
        api = subprocess.Popen(
            [api_python(), "-m", "uvicorn", "app.main:app", "--app-dir", str(API_DIR), "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        vite = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite.exists():
            raise RuntimeError("Vite is missing; run npm ci --prefix apps/web first")
        web = subprocess.Popen(
            [node_command(), str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
            cwd=WEB_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        health = wait_for("http://127.0.0.1:8000/health")
        openapi = wait_for("http://127.0.0.1:8000/openapi.json")
        proxied_health = wait_for("http://127.0.0.1:5173/api/health")
        page = wait_for("http://127.0.0.1:5173/")
        if health != proxied_health or b'"/health"' not in openapi or b'<div id="root"></div>' not in page:
            raise RuntimeError("API response or Vite page did not match the expected smoke contract")
        print("smoke passed: Vite /api proxy reached FastAPI /health")
        return 0
    finally:
        for process in (web, api):
            if process is not None:
                process.terminate()
        for process in (web, api):
            if process is None:
                continue
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
