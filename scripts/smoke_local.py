#!/usr/bin/env python3
"""Comprueba la ruta local Vite (/api) -> FastAPI sin servicios externos."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"
HOST = "127.0.0.1"
API_PORT = 8000
WEB_PORT = 5173


def api_python() -> str:
    scripts = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    candidate = API_DIR / ".venv" / scripts
    if not candidate.exists():
        raise RuntimeError("API virtual environment is missing; follow README.md first")
    return str(candidate)


def node_command() -> str:
    return "node.exe" if os.name == "nt" else "node"


def require_running(process: subprocess.Popen[bytes], url: str) -> None:
    exit_code = process.poll()
    if exit_code is not None:
        raise RuntimeError(f"local process for {url} exited with code {exit_code}")


def wait_for(url: str, process: subprocess.Popen[bytes]) -> bytes:
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        require_running(process, url)
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 - fixed localhost URLs
                if response.status == 200:
                    return response.read()
        except Exception as error:  # pragma: no cover - timing depends on local processes
            last_error = error
        time.sleep(0.25)
    raise RuntimeError(f"local service did not become ready: {url}; last error: {last_error}")


def main() -> int:
    for port in (API_PORT, WEB_PORT):
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex((HOST, port)) == 0:
                raise RuntimeError(f"smoke requires {HOST}:{port} to be free; stop the local service")

    api_url = f"http://{HOST}:{API_PORT}"
    web_url = f"http://{HOST}:{WEB_PORT}"
    environment = os.environ.copy()
    environment["VITE_API_PROXY_TARGET"] = api_url
    api: subprocess.Popen[bytes] | None = None
    web: subprocess.Popen[bytes] | None = None
    try:
        api = subprocess.Popen(
            [api_python(), "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(API_PORT)],
            cwd=API_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        vite = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite.exists():
            raise RuntimeError("Vite is missing; run npm ci --prefix apps/web first")
        web = subprocess.Popen(
            [node_command(), str(vite), "--host", HOST, "--port", str(WEB_PORT), "--strictPort"],
            cwd=WEB_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        health = wait_for(f"{api_url}/health", api)
        openapi = wait_for(f"{api_url}/openapi.json", api)
        proxied_health = wait_for(f"{web_url}/api/health", web)
        page = wait_for(web_url, web)
        if health != proxied_health or b'"/health"' not in openapi or b'<div id="root"></div>' not in page:
            raise RuntimeError("API response or Vite page did not match the expected smoke contract")
        require_running(api, api_url)
        require_running(web, web_url)
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
