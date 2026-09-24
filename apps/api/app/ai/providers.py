"""Proveedores de IA: registro, clientes y medición de tokens.

Adaptado del patrón del proyecto `agentes-asobares`, que ya resolvió en
producción los tres problemas que aquí importan:

1. **El modelo es configurable, no una constante.** El proveedor se elige por
   entorno y el modelo se puede cambiar sin tocar código, porque el precio y la
   calidad de los modelos cambian más rápido que este repositorio (HU-27).
2. **La medición de tokens nunca rompe el flujo.** No todos los proveedores
   devuelven `usage` con la misma forma; ante la duda se devuelve cero y se
   sigue. Un fallo al medir no puede tumbar un análisis que ya se hizo.
3. **Los timeouts son explícitos.** El SDK usa por defecto `read=600 s` con dos
   reintentos: un turno puede quedar colgado media hora sin que nadie lo note.
   Aquí se acotan por entorno.

Lo que este módulo **no** hace
-----------------------------

No envía nada. Construye clientes y extrae métricas. El envío de documentos a un
proveedor externo exige autorización empresarial específica (HU-27) y `store`
de un proveedor no equivale a retención cero; por eso la decisión de enviar vive
en el adaptador, que declara explícitamente qué sale del perímetro.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Provider(StrEnum):
    """Proveedores soportados. Todos hablan la API compatible con OpenAI."""

    OPENAI = "openai"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"
    # Gateway local multi-proveedor. Se usa en desarrollo: enruta a varios
    # proveedores y evita depender de uno solo que se sature.
    ROUTER9 = "9router"


# Timeouts por entorno. La diferencia no es capricho: un endpoint gratuito puede
# tardar dos minutos en una llamada que uno de pago resuelve en tres segundos, y
# un límite único o corta respuestas legítimas en desarrollo o deja colgado un
# proceso en producción.
_TIMEOUTS: dict[str, tuple[float, int]] = {
    "development": (300.0, 0),
    "test": (30.0, 0),
    "production": (60.0, 2),
}


def timeouts_for(environment: str) -> tuple[float, int]:
    """Devuelve ``(timeout_segundos, reintentos)`` según el entorno.

    Dos variables de entorno permiten ajustarlo sin tocar código, porque el
    comportamiento de un proveedor cambia sin avisar.
    """

    timeout, retries = _TIMEOUTS.get(environment, _TIMEOUTS["production"])
    raw_timeout = os.getenv("EAG_AI_TIMEOUT_SECONDS")
    raw_retries = os.getenv("EAG_AI_MAX_RETRIES")
    if raw_timeout:
        try:
            timeout = float(raw_timeout)
        except ValueError:
            pass
    if raw_retries:
        try:
            retries = int(raw_retries)
        except ValueError:
            pass
    return timeout, retries


@dataclass(frozen=True)
class ProviderConfig:
    """Configuración de un proveedor."""

    provider: Provider
    label: str
    base_url: str | None
    api_key_env: str
    default_model: str
    known_models: tuple[str, ...] = ()
    supports_structured_output: bool = False
    extra_params: dict[str, Any] = field(default_factory=dict)

    def resolve_model(self, model: str | None = None) -> str:
        """Modelo a usar.

        Un modelo fuera de la lista conocida se acepta en lugar de rechazarse:
        los proveedores publican modelos nuevos más rápido de lo que este
        registro se actualiza, y bloquear uno válido obligaría a desplegar
        código para probarlo.
        """

        return model or self.default_model


PROVIDERS: dict[Provider, ProviderConfig] = {
    Provider.OPENAI: ProviderConfig(
        provider=Provider.OPENAI,
        label="OpenAI",
        base_url=None,
        api_key_env="EAG_OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        known_models=("gpt-4o-mini", "gpt-4o", "gpt-4-turbo"),
        supports_structured_output=True,
    ),
    Provider.NVIDIA: ProviderConfig(
        provider=Provider.NVIDIA,
        label="NVIDIA NIM",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="EAG_NVIDIA_API_KEY",
        default_model="openai/gpt-oss-20b",
        known_models=(
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            "nvidia/nemotron-3-nano-30b-a3b",
            "meta/llama-3.1-70b-instruct",
        ),
        supports_structured_output=True,
        extra_params={
            # Los modelos con razonamiento gastan la mayor parte del presupuesto
            # de tokens pensando. Con un límite bajo se truncan a mitad del
            # razonamiento y devuelven texto vacío, que es peor que un error
            # porque parece una respuesta.
            "max_tokens": 3000,
        },
    ),
    Provider.OPENROUTER: ProviderConfig(
        provider=Provider.OPENROUTER,
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="EAG_OPENROUTER_API_KEY",
        default_model="openai/gpt-4o-mini",
        supports_structured_output=True,
    ),
    Provider.ROUTER9: ProviderConfig(
        provider=Provider.ROUTER9,
        label="9router (gateway local)",
        base_url=None,  # se resuelve en tiempo de ejecución
        api_key_env="EAG_ROUTER9_API_KEY",
        default_model="cl/deepseek/deepseek-v4-flash",
        known_models=("cl/deepseek/deepseek-v4-flash",),
        supports_structured_output=True,
        extra_params={"max_tokens": 3000},
    ),
}


def get_provider(provider: str | Provider) -> ProviderConfig:
    """Resuelve un proveedor por nombre.

    Falla en lugar de caer a uno por defecto: analizar con un proveedor distinto
    del configurado produciría resultados que no corresponden a la configuración
    que el administrador cree tener.
    """

    if isinstance(provider, Provider):
        return PROVIDERS[provider]
    try:
        return PROVIDERS[Provider(provider.lower())]
    except ValueError:
        known = ", ".join(p.value for p in PROVIDERS)
        raise UnknownProviderError(
            f"proveedor no reconocido: {provider!r}; disponibles: {known}"
        ) from None


class UnknownProviderError(LookupError):
    """Se pidió un proveedor que el sistema no tiene registrado."""


def describe_providers() -> list[dict[str, Any]]:
    """Descripción de los proveedores, sin secretos, para la interfaz."""

    return [
        {
            "provider": config.provider.value,
            "label": config.label,
            "default_model": config.default_model,
            "known_models": list(config.known_models),
            "structured_output": config.supports_structured_output,
            # Se publica el NOMBRE de la variable, nunca su valor: permite
            # diagnosticar una configuración ausente sin exponer la clave.
            "api_key_env": config.api_key_env,
            "key_present": bool(os.getenv(config.api_key_env)),
        }
        for config in PROVIDERS.values()
    ]


# --- Medición ---------------------------------------------------------------


@dataclass(frozen=True)
class TokenUsage:
    """Tokens consumidos por una llamada.

    Cero cuando el proveedor no informa. No es lo mismo que «no consumió», y por
    eso el llamante puede distinguirlo con `reported`.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    reported: bool = False

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reported=self.reported or other.reported,
        )


def extract_usage(completion: Any) -> TokenUsage:
    """Extrae los tokens de una respuesta, sin romper si no los trae.

    Se comprueba en cadena porque los proveedores no coinciden en la forma:
    algunos omiten `usage` y otros lo anidan distinto. Ante cualquier duda se
    devuelve cero con `reported=False`, porque **la medición nunca debe romper
    el flujo**: perder la medida de una llamada es un problema menor que perder
    el análisis entero.
    """

    usage = getattr(completion, "usage", None)
    if usage is None and isinstance(completion, dict):
        usage = completion.get("usage")
    if usage is None:
        return TokenUsage()

    def _read(name: str) -> int | None:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    entrada = _read("prompt_tokens")
    salida = _read("completion_tokens")
    if entrada is None and salida is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=entrada or 0,
        output_tokens=salida or 0,
        reported=True,
    )


# --- Estimación de coste ----------------------------------------------------

# Precio en dólares por millón de tokens. Es una tabla explícita y no una
# consulta al proveedor porque el coste debe poder calcularse **antes** de
# gastar, para poder negarse a hacerlo.
#
# Advertencia: son precios de referencia y cambian. El coste calculado es una
# estimación para control presupuestario, no una cifra contable, y así se
# declara en la interfaz en lugar de presentarlo como una factura.
PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "openai/gpt-oss-20b": (0.10, 0.50),
    "openai/gpt-oss-120b": (0.15, 0.75),
}


def estimate_cost(model: str, usage: TokenUsage) -> float | None:
    """Coste estimado en dólares, o None si el modelo no tiene precio conocido.

    Devolver None y no cero: un modelo sin tarifa conocida no es gratis, es
    desconocido. Presentar cero haría creer que el gasto está controlado cuando
    no hay forma de saberlo.
    """

    prices = PRICES_PER_MILLION.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (
        usage.input_tokens * input_price / 1_000_000
        + usage.output_tokens * output_price / 1_000_000
    )


class TokenMeter(Protocol):
    """Contrato mínimo para registrar consumo desde el adaptador."""

    def record(
        self,
        *,
        model: str,
        usage: TokenUsage,
        node: str,
        run_id: int | None = None,
    ) -> None: ...
