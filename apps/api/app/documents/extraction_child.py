"""Proceso aislado, con entrada y salida privadas por tubería."""

import argparse
import re
import sys
from typing import cast

from app.documents.extraction import Format, extract, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("format", choices=["pdf", "docx", "xlsx"])
    parser.add_argument("language")
    parser.add_argument("max_ocr", type=int)
    parser.add_argument("max_bytes", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z]{3}(?:[+][a-z]{3}){0,3}", args.language):
        parser.error("idioma OCR inválido")
    if not 0 <= args.max_ocr <= 50 or not 1 <= args.max_bytes <= 100 * 1024**2:
        parser.error("límites inválidos")
    if sys.platform != "win32":
        import resource

        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        cap = 1024**3 if hard == resource.RLIM_INFINITY else min(hard, 1024**3)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    data = sys.stdin.buffer.read(args.max_bytes + 1)
    if len(data) > args.max_bytes:
        result = failed("limite_archivo")
    else:
        result = extract(
            data, cast(Format, args.format), language=args.language, max_ocr_pages=args.max_ocr,
        )
    sys.stdout.buffer.write(result.model_dump_json().encode("utf-8"))


if __name__ == "__main__":
    main()
