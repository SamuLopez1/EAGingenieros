"""Pruebas del registro de proveedores, la medición y el control de coste.

Todo offline: no se llama a ningún proveedor. Lo que se prueba es la lógica que
rodea a la llamada —qué configuración se resuelve, cómo se miden los tokens
cuando el proveedor no los informa, y si el tope impide gastar de verdad—, que
es donde están los fallos caros: un tope que no se aplica, o una medición que
rompe el flujo cuando el proveedor no devuelve `usage`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.budget import (
    BudgetExceeded,
    budget_state,
    ensure_within_budget,
    get_cached,
    make_cache_key,
    record_usage,
    store_cached,
)
from app.ai.providers import (
    PROVIDERS,
    Provider,
    TokenUsage,
    UnknownProviderError,
    describe_providers,
    estimate_cost,
    extract_usage,
    get_provider,
    timeouts_for,
)
from app.db.models import Base


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    # `import app.db` registra todas las tablas en `Base.metadata`, incluidas las
    # de consumo de IA.
    import app.db  # noqa: F401

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# --- Registro de proveedores ------------------------------------------------


def test_both_paid_and_local_providers_are_registered() -> None:
    assert Provider.OPENAI in PROVIDERS
    assert Provider.ROUTER9 in PROVIDERS


def test_provider_resolves_by_name() -> None:
    assert get_provider("openai") is PROVIDERS[Provider.OPENAI]
    assert get_provider(Provider.NVIDIA) is PROVIDERS[Provider.NVIDIA]


def test_unknown_provider_fails_instead_of_defaulting() -> None:
    """Caer a un proveedor por defecto analizaría con otro del configurado.

    El administrador creería estar usando un modelo y el sistema usaría otro, sin
    que nada lo indicara.
    """

    with pytest.raises(UnknownProviderError):
        get_provider("no-existe")


def test_key_names_are_published_but_never_values() -> None:
    described = describe_providers()

    assert all("api_key_env" in item for item in described)
    assert all("api_key" not in item for item in described)
    # El valor solo se publica como presencia, no como contenido.
    assert all(isinstance(item["key_present"], bool) for item in described)


def test_timeouts_are_explicit_per_environment() -> None:
    """El SDK usa por defecto 600 s con dos reintentos: media hora colgado."""

    dev_timeout, _ = timeouts_for("development")
    prod_timeout, prod_retries = timeouts_for("production")
    assert prod_timeout < dev_timeout
    assert prod_retries >= 0


# --- Medición ---------------------------------------------------------------


def test_extracts_usage_from_an_object() -> None:
    completion = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=45)
    )

    usage = extract_usage(completion)

    assert usage.input_tokens == 120
    assert usage.output_tokens == 45
    assert usage.reported is True
    assert usage.total == 165


def test_extracts_usage_from_a_dict() -> None:
    usage = extract_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    assert usage.input_tokens == 10
    assert usage.reported is True


def test_missing_usage_does_not_raise() -> None:
    """La medición nunca debe romper el flujo.

    Perder la medida de una llamada es un problema menor que perder el análisis
    entero porque el proveedor no devolvió `usage`.
    """

    usage = extract_usage(SimpleNamespace())

    assert usage.total == 0
    assert usage.reported is False


def test_malformed_usage_does_not_raise() -> None:
    usage = extract_usage({"usage": {"prompt_tokens": "muchos"}})

    assert usage.reported is False


def test_usage_adds_up() -> None:
    total = TokenUsage(10, 5, reported=True) + TokenUsage(1, 2)

    assert total.input_tokens == 11
    assert total.output_tokens == 7
    assert total.reported is True


# --- Coste ------------------------------------------------------------------


def test_estimated_cost_uses_the_price_table() -> None:
    cost = estimate_cost("gpt-4o-mini", TokenUsage(1_000_000, 1_000_000, reported=True))

    assert cost == pytest.approx(0.75)


def test_unknown_model_has_no_cost_not_zero_cost() -> None:
    """Un modelo sin tarifa conocida no es gratis, es desconocido.

    Devolver cero haría creer que el gasto está controlado cuando no hay forma
    de saberlo.
    """

    assert estimate_cost("modelo-desconocido", TokenUsage(1000, 1000)) is None


# --- Presupuesto ------------------------------------------------------------


def test_without_limit_there_is_no_budget_check(db: Session) -> None:
    state = ensure_within_budget(db, limit_usd=None)

    assert state.limit_usd is None
    assert state.remaining_usd is None
    assert state.exceeded is False


def test_spending_is_accumulated(db: Session) -> None:
    record_usage(
        db, provider="openai", model="gpt-4o-mini", usage=TokenUsage(1_000_000, 0, True)
    )
    record_usage(
        db, provider="openai", model="gpt-4o-mini", usage=TokenUsage(1_000_000, 0, True)
    )

    state = budget_state(db, limit_usd=Decimal("1.00"))

    assert state.spent_usd == pytest.approx(Decimal("0.30"))
    assert state.calls == 2


def test_budget_blocks_the_call_that_would_cross_the_limit(db: Session) -> None:
    """El tope se comprueba **antes** de gastar, no después.

    Un límite que solo se revisa al terminar informa de un exceso que ya ocurrió.
    """

    record_usage(
        db, provider="openai", model="gpt-4o-mini", usage=TokenUsage(1_000_000, 0, True)
    )

    with pytest.raises(BudgetExceeded):
        ensure_within_budget(
            db, limit_usd=Decimal("0.10"), estimated_cost=Decimal("0.05")
        )


def test_budget_allows_a_call_that_fits(db: Session) -> None:
    state = ensure_within_budget(
        db, limit_usd=Decimal("1.00"), estimated_cost=Decimal("0.05")
    )

    assert state.exceeded is False
    assert state.remaining_usd == Decimal("1.00")


def test_calls_without_price_are_counted_as_unpriced(db: Session) -> None:
    """El gasto calculado es una cota inferior si hay llamadas sin tarifa.

    Declararlo evita afirmar que queda presupuesto cuando en realidad no se sabe.
    """

    record_usage(db, provider="x", model="desconocido", usage=TokenUsage(10, 10, True))

    state = budget_state(db, limit_usd=Decimal("1.00"))

    assert state.unpriced_calls == 1
    assert state.complete is False


def test_last_month_spending_does_not_count(db: Session) -> None:
    """El tope es mensual: el gasto de septiembre no limita octubre."""

    record_usage(
        db, provider="openai", model="gpt-4o-mini", usage=TokenUsage(1_000_000, 0, True)
    )
    # Se envejece la fila más allá del inicio del mes en curso.
    from app.db.ai_models import AiUsage

    old = db.query(AiUsage).one()
    old.created_at = datetime.now(UTC) - timedelta(days=40)
    db.flush()

    state = budget_state(db, limit_usd=Decimal("0.01"))

    assert state.spent_usd == 0
    assert state.exceeded is False


def test_failed_calls_are_recorded_too(db: Session) -> None:
    """Una llamada fallida puede haber consumido entrada: el proveedor la cobra
    aunque la salida se trunque. No registrarla dejaría el gasto por debajo."""

    record_usage(
        db,
        provider="openai",
        model="gpt-4o-mini",
        usage=TokenUsage(500_000, 0, True),
        status="fallida",
        error_kind="timeout",
    )

    state = budget_state(db, limit_usd=None)

    assert state.calls == 1
    assert state.spent_usd > 0


# --- Caché ------------------------------------------------------------------


def test_cache_key_depends_on_model_and_prompt_version() -> None:
    """El mismo texto con otro modelo **no** es la misma llamada."""

    base = make_cache_key(content="pliego", model="gpt-4o-mini", prompt_version="v1")

    assert base != make_cache_key(content="pliego", model="gpt-4o", prompt_version="v1")
    assert base != make_cache_key(content="pliego", model="gpt-4o-mini", prompt_version="v2")
    assert base != make_cache_key(content="otro", model="gpt-4o-mini", prompt_version="v1")
    assert base == make_cache_key(content="pliego", model="gpt-4o-mini", prompt_version="v1")


def test_cache_round_trip(db: Session) -> None:
    key = make_cache_key(content="pliego", model="gpt-4o-mini", prompt_version="v1")
    store_cached(
        db,
        cache_key=key,
        model="gpt-4o-mini",
        prompt_version="v1",
        payload={"requisitos": []},
    )

    found = get_cached(db, cache_key=key, model="gpt-4o-mini", prompt_version="v1")

    assert found is not None
    assert found.payload == {"requisitos": []}
    assert found.hits == 1


def test_cache_misses_when_the_model_changes(db: Session) -> None:
    key = make_cache_key(content="pliego", model="gpt-4o-mini", prompt_version="v1")
    store_cached(
        db, cache_key=key, model="gpt-4o-mini", prompt_version="v1", payload={"a": 1}
    )

    assert get_cached(db, cache_key=key, model="gpt-4o", prompt_version="v1") is None
