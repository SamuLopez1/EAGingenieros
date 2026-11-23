"""Directorios privados y descartables usados por el worker de extracción."""

import os
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

PREFIX = "eag-extraction-"
MARKER = ".eag-extraction-v1"
MIN_AGE = 3600  # Mayor que el límite del worker (300 s) y su reserva.


def private_root(root: Path) -> Path:
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ValueError("Directorio de trabajo inválido.")
    return root.resolve(strict=True)


@contextmanager
def workspace(root: Path | None) -> Iterator[str]:
    directory = private_root(root) if root is not None else None
    with TemporaryDirectory(prefix=PREFIX, dir=directory) as scratch:
        if directory is not None:
            (Path(scratch) / MARKER).touch(exist_ok=False)
        yield scratch


def sweep(root: Path, now: datetime, *, remove: bool) -> int:
    directory = private_root(root)
    cutoff = now.timestamp() - MIN_AGE
    count = 0
    for child in directory.iterdir():
        if not re.fullmatch(r"eag-extraction-[a-z0-9_]{8}", child.name):
            continue
        try:
            if child.is_symlink() or child.is_junction() or not child.is_dir():
                continue
            resolved = child.resolve(strict=True)
            marker = resolved / MARKER
            if (
                resolved.parent != directory
                or os.path.ismount(resolved)
                or marker.is_symlink()
                or not marker.is_file()
                or max(marker.stat().st_mtime, resolved.stat().st_mtime) > cutoff
            ):
                continue
            if remove:
                shutil.rmtree(resolved)
            count += 1
        except FileNotFoundError:
            # El worker puede haber limpiado su propio directorio.
            continue
    return count
