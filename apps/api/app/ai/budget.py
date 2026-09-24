"""Control de presupuesto y caché de llamadas de IA (HU-27).

La regla que gobierna el módulo: **el tope se comprueba antes de gastar, no
después.** Un límite que solo se revisa al terminar informa de un exceso que ya
ocurrió; lo que HU-27 pide es no llegar a él.

Cuando el presupuesto se agota, la llamada se **omite** y queda registrada como
tal. No se lanza una excepción hacia arriba ni se devuelve una respuesta vacía
disfrazada de resultado: el análisis continúa por las vías que no cuestan dinero
—las reglas deterministas y la recuperación local— y el consumo omitido queda
visible. Así el sistema sigue siendo útil sin presupuesto, y nadie confunde un
límite presupuestario con una avería.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers import TokenUsage, estimate_cost
from app.db.ai_models import AiCache, AiUsage, content_hash


class BudgetExceeded(RuntimeError):
    """El gasto del mes alcanzó el tope configurado.

    Se distingue de un error técnico porque no lo es: es una decisión de
    configuración funcionando.
    """


@dataclass(frozen=True)
class BudgetState:
    """Situación del presupuesto en el mes en curso."""

    limit_usd: Decimal | None
    spent_usd: Decimal
    calls: int
    # Llamadas cuyo coste no se pudo calcular por no tener tarifa conocida. Se
    # informan aparte porque el gasto real es mayor que `spent_usd`.
    unpriced_calls: int

    @property
    def remaining_usd(self) -> Decimal | None:
        if self.limit_usd is None:
            return None
        return max(Decimal(0), self.limit_usd - self.spent_usd)

    @property
    def exceeded(self) -> bool:
        return self.limit_usd is not None and self.spent_usd >= self.limit_usd

    @property
    def complete(self) -> bool:
        """Indica si el gasto calculado refleja todo lo gastado.

        Con llamadas sin tarifa conocida el total es una cota inferior: no se
        puede afirmar que quede presupuesto.
        """

        return self.unpriced_calls == 0


def _month_start(now: datetime | None = None) -> datetime:
    """Primer instante del mes en curso, en UTC.

    El corte es mensual y en UTC porque el presupuesto es una decisión de coste,
    no de calendario local: usar la zona del servidor haría que el mes cambiara
    a distinta hora según dónde esté desplegado.
    """

    moment = now or datetime.now(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def budget_state(
    session: Session, *, limit_usd: Decimal | None, now: datetime | None = None
) -> BudgetState:
    """Calcula el consumo del mes en curso."""

    start = _month_start(now)
    statement = select(
        func.coalesce(func.sum(AiUsage.cost_usd), 0),
        func.count(AiUsage.id),
        func.count(AiUsage.id).filter(AiUsage.cost_usd.is_(None)),
    ).where(AiUsage.created_at >= start)

    spent, calls, unpriced = session.execute(statement).one()
    return BudgetState(
        limit_usd=limit_usd,
        spent_usd=Decimal(str(spent or 0)),
        calls=int(calls or 0),
        unpriced_calls=int(unpriced or 0),
    )


def ensure_within_budget(
    session: Session,
    *,
    limit_usd: Decimal | None,
    estimated_cost: Decimal | None = None,
    now: datetime | None = None,
) -> BudgetState:
    """Comprueba que queda presupuesto *antes* de llamar al proveedor.

    Se tiene en cuenta el coste estimado de la llamada que se va a hacer, no solo
    lo ya gastado: si no, la llamada que cruza el tope siempre se ejecutaría.
    """

    state = budget_state(session, limit_usd=limit_usd, now=now)
    if state.limit_usd is None:
        return state

    projected = state.spent_usd + (estimated_cost or Decimal(0))
    if projected >= state.limit_usd:
        raise BudgetExceeded(
            f"el gasto del mes ({state.spent_usd:.4f} USD) alcanzaría el tope "
            f"de {state.limit_usd:.2f} USD"
        )
    return state


def record_usage(
    session: Session,
    *,
    provider: str,
    model: str,
    usage: TokenUsage,
    status: str = "completada",
    node: str | None = None,
    analysis_run_id: int | None = None,
    actor_id: int | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    cache_key: str | None = None,
    duration_ms: int | None = None,
    error_kind: str | None = None,
) -> AiUsage:
    """Registra una llamada. Se llama siempre, incluso cuando falla.

    Una llamada fallida también puede haber consumido tokens —el proveedor cobra
    la entrada aunque la salida se trunque—, así que no registrarla dejaría el
    gasto real por debajo del calculado.
    """

    cost = estimate_cost(model, usage)
    row = AiUsage(
        provider=provider,
        model=model,
        status=status,
        node=node,
        analysis_run_id=analysis_run_id,
        actor_id=actor_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        usage_reported=usage.reported,
        cost_usd=None if cost is None else Decimal(str(round(cost, 6))),
        cache_key=cache_key,
        duration_ms=duration_ms,
        error_kind=error_kind,
    )
    session.add(row)
    session.flush()
    return row


def make_cache_key(
    *, content: str, model: str, prompt_version: str, schema_version: str | None = None
) -> str:
    """Clave de caché de una llamada."""

    return content_hash(content, model, prompt_version, schema_version or "")


def get_cached(
    session: Session,
    *,
    cache_key: str,
    model: str,
    prompt_version: str,
) -> AiCache | None:
    """Devuelve el resultado guardado, si lo hay.

    El modelo y la versión van en la consulta además del hash: cambiar de modelo
    invalida la caché por construcción, sin depender de que alguien se acuerde de
    purgarla.
    """

    found = session.execute(
        select(AiCache).where(
            AiCache.cache_key == cache_key,
            AiCache.model == model,
            AiCache.prompt_version == prompt_version,
        )
    ).scalar_one_or_none()
    if found is not None:
        found.hits += 1
        session.flush()
    return found


def store_cached(
    session: Session,
    *,
    cache_key: str,
    model: str,
    prompt_version: str,
    payload: dict[str, object],
    raw_text: str | None = None,
    schema_version: str | None = None,
) -> AiCache:
    """Guarda un resultado **ya validado**.

    Solo se llama después de que la respuesta pasó la validación de esquema: una
    respuesta inválida en caché se reutilizaría indefinidamente como si fuera
    buena.
    """

    row = AiCache(
        cache_key=cache_key,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        payload=payload,
        raw_text=raw_text,
    )
    session.add(row)
    session.flush()
    return row
