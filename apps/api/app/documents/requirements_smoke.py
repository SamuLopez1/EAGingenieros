"""Smoke real de una sola llamada con datos sintéticos incorporados."""

import argparse
import os
from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx

from app.documents.extraction import Locator
from app.documents.requirements import Source, build_analysis
from app.documents.requirements_provider import OpenAIAdapter

SYNTHETIC = Source(
    document_id=UUID(int=1),
    sha256="0" * 64,
    version=1,
    title="Fixture",
    kind="pliego",
    locator=Locator(page=1),
    text="Objeto: Consultoría sintética.\nHabilitante: Experiencia de un año.",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-synthetic", action="store_true", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-usd-per-million", required=True)
    parser.add_argument("--output-usd-per-million", required=True)
    parser.add_argument("--max-usd", required=True)
    args = parser.parse_args()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        parser.error("Falta la credencial autorizada OPENAI_API_KEY.")
    try:
        costs = (
            Decimal(args.input_usd_per_million),
            Decimal(args.output_usd_per_million),
            Decimal(args.max_usd),
        )
    except InvalidOperation:
        parser.error("Precios y presupuesto deben ser decimales positivos.")
    if not all(value.is_finite() and value > 0 for value in costs):
        parser.error("Precios y presupuesto deben ser decimales positivos.")
    with httpx.Client(
        base_url="https://api.openai.com",
        headers={"Authorization": f"Bearer {key}"},
        timeout=15,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        provider = OpenAIAdapter(client, args.model, *costs)
        result = build_analysis(provider, "synthetic-smoke", [SYNTHETIC], [])
        if provider.usage:
            input_tokens, output_tokens = provider.usage
            print(f"tokens_entrada={input_tokens} tokens_salida={output_tokens}")
            print(f"coste_usd_calculado={provider.cost(input_tokens, output_tokens):.8f}")
        else:
            print("Consumo sin confirmar.")
        ok = (
            provider.usage is not None
            and provider.cost(*provider.usage) <= provider.max_usd
            and {item.kind for item in result.summary} == {"objeto"}
            and {item.kind for item in result.requirements} == {"habilitante"}
        )
        print(f"fixture_sintetica={'verificada' if ok else 'revision'}")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
