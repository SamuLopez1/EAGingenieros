#!/usr/bin/env python3
"""Cuenta líneas por lenguaje en este repositorio.

Se escribe a mano en lugar de añadir `pygount` o `cloc` como dependencia: la
medición se hace una vez para documentar el stack, y una herramienta más en el
entorno de desarrollo es un coste permanente para una necesidad puntual.

Distingue líneas totales, en blanco y de comentario. Informar solo del total
infla el número: un archivo muy comentado parecería más código del que es.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Directorios que no son código del proyecto: dependencias instaladas, cachés de
# herramientas, artefactos de construcción y material de trabajo local.
EXCLUIDOS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "output",
    "tmp",
    "build",
    ".vite",
}

# Comentario de línea y, opcionalmente, delimitadores de bloque.
SINTAXIS: dict[str, tuple[str | None, tuple[str, str] | None]] = {
    ".py": ("#", ('"""', '"""')),
    ".ts": ("//", ("/*", "*/")),
    ".tsx": ("//", ("/*", "*/")),
    ".js": ("//", ("/*", "*/")),
    ".mjs": ("//", ("/*", "*/")),
    ".css": (None, ("/*", "*/")),
    ".sql": ("--", ("/*", "*/")),
    ".sh": ("#", None),
    ".yml": ("#", None),
    ".yaml": ("#", None),
    ".toml": ("#", None),
    ".ini": ("#", None),
    ".conf": ("#", None),
    ".dockerfile": ("#", None),
    ".md": (None, None),
    ".mako": ("##", None),
}

LENGUAJE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (TSX)",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".css": "CSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".conf": "Nginx",
    ".dockerfile": "Dockerfile",
    ".md": "Markdown",
    ".mako": "Mako (plantilla)",
    ".html": "HTML",
    ".json": "JSON",
}

# Archivos generados por herramientas, no escritos aquí. Contarlos inflaría el
# resultado: `package-lock.json` son miles de líneas que nadie mantiene a mano.
GENERADOS = {
    "package-lock.json",
    "requirements.lock",
    "pnpm-lock.yaml",
    "yarn.lock",
}

# Archivos sin extensión que sí son código o configuración del proyecto.
POR_NOMBRE = {
    "Dockerfile": ("Dockerfile", "#", None),
    ".dockerignore": ("Dockerfile", "#", None),
    ".gitignore": ("Configuración", "#", None),
}


def contar(ruta: Path, comentario: str | None, bloque: tuple[str, str] | None) -> tuple[int, int, int]:
    """Devuelve (total, en blanco, comentario)."""

    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return (0, 0, 0)

    lineas = texto.splitlines()
    total = len(lineas)
    blanco = 0
    comentadas = 0
    dentro_de_bloque = False

    for linea in lineas:
        despojada = linea.strip()
        if not despojada:
            blanco += 1
            continue

        if bloque is not None:
            inicio, fin = bloque
            if dentro_de_bloque:
                comentadas += 1
                if fin in despojada:
                    dentro_de_bloque = False
                continue
            if despojada.startswith(inicio):
                comentadas += 1
                # Un docstring de una sola línea abre y cierra en la misma.
                if not (despojada.count(inicio) >= 2 or fin in despojada[3:]):
                    dentro_de_bloque = True
                continue

        if comentario is not None and despojada.startswith(comentario):
            comentadas += 1

    return (total, blanco, comentadas)


acumulado: dict[str, dict[str, int]] = defaultdict(
    lambda: {"archivos": 0, "total": 0, "blanco": 0, "comentario": 0}
)

for ruta in sorted(RAIZ.rglob("*")):
    if not ruta.is_file():
        continue
    if any(parte in EXCLUIDOS for parte in ruta.relative_to(RAIZ).parts):
        continue
    if ruta.name in GENERADOS:
        continue

    if ruta.name in POR_NOMBRE:
        lenguaje, comentario, bloque = POR_NOMBRE[ruta.name]
    elif ruta.suffix.lower() in LENGUAJE:
        lenguaje = LENGUAJE[ruta.suffix.lower()]
        comentario, bloque = SINTAXIS.get(ruta.suffix.lower(), (None, None))
    else:
        continue

    total, blanco, comentadas = contar(ruta, comentario, bloque)
    datos = acumulado[lenguaje]
    datos["archivos"] += 1
    datos["total"] += total
    datos["blanco"] += blanco
    datos["comentario"] += comentadas

filas = []
for lenguaje, datos in acumulado.items():
    codigo = datos["total"] - datos["blanco"] - datos["comentario"]
    filas.append((codigo, lenguaje, datos["archivos"], datos["total"], datos["comentario"]))

filas.sort(reverse=True)

print(f"{'Lenguaje':<20}{'Archivos':>9}{'Líneas':>9}{'Código':>9}{'Comentario':>12}")
print("-" * 60)
total_codigo = 0
total_archivos = 0
for codigo, lenguaje, archivos, total, comentario in filas:
    print(f"{lenguaje:<20}{archivos:>9}{total:>9}{codigo:>9}{comentario:>12}")
    total_codigo += codigo
    total_archivos += archivos
print("-" * 60)
print(f"{'TOTAL':<20}{total_archivos:>9}{'':>9}{total_codigo:>9}")

if "--json" in sys.argv:
    import json

    print()
    print(
        json.dumps(
            [
                {"lenguaje": l, "archivos": a, "codigo": c, "comentario": com}
                for c, l, a, _t, com in filas
            ],
            ensure_ascii=False,
        )
    )
