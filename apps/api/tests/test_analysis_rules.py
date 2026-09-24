"""Pruebas de las reglas deterministas (HU-29).

El caso que originó el módulo está en `test_insufficient_experience_is_non_compliance`:
antes, un requisito de «mínimo cinco años de experiencia» podía proponerse como
«cumple» solo porque un fragmento sobre experiencia tenía buena puntuación de
recuperación, sin que los números se compararan nunca. Es un falso cumplimiento,
el error más caro que este sistema puede cometer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.analysis.rules import (
    Condition,
    RuleOutcome,
    compare,
    extract_conditions,
    parse_number,
    run_rules,
    strip_accents,
)

# --- Interpretación de números ---------------------------------------------


def test_parses_plain_digits() -> None:
    assert parse_number("5") == Decimal(5)
    assert parse_number("30") == Decimal(30)


def test_parses_colombian_thousands_separator() -> None:
    """«1.000» son mil, no uno con decimales.

    El formato colombiano usa punto para miles y coma para decimales.
    Interpretarlo al revés cambiaría el requisito por un factor de mil.
    """

    assert parse_number("1.000") == Decimal(1000)
    assert parse_number("1.500.000") == Decimal(1500000)
    assert parse_number("1.500.000,50") == Decimal("1500000.50")


def test_parses_number_words() -> None:
    assert parse_number("cinco") == Decimal(5)
    assert parse_number("veinticinco") == Decimal(25)
    assert parse_number("cien") == Decimal(100)
    assert parse_number("mil") == Decimal(1000)


def test_parses_fraction_words() -> None:
    assert parse_number("medio") == Decimal("0.5")


def test_rejects_non_numbers() -> None:
    assert parse_number("experiencia") is None
    assert parse_number("") is None
    assert parse_number("--") is None


def test_strip_accents_makes_text_comparable() -> None:
    assert strip_accents("Años de experiencia") == "Anos de experiencia"
    assert strip_accents("mínimo") == "minimo"


# --- Extracción de condiciones ---------------------------------------------


def test_extracts_experience_requirement_with_parenthetical_digit() -> None:
    """«cinco (5) años» es como lo escriben los pliegos."""

    conditions = extract_conditions(
        "El proponente debe acreditar mínimo cinco (5) años de experiencia"
    )

    assert len(conditions) == 1
    condition = conditions[0]
    assert condition.kind == "duracion"
    assert condition.unit == "anios"
    assert condition.value == Decimal(5)
    assert condition.operator == "min"


def test_extracts_requirement_with_digits() -> None:
    conditions = extract_conditions("Se exige mínimo 3 años en obras civiles")

    assert len(conditions) == 1
    assert conditions[0].value == Decimal(3)
    assert conditions[0].operator == "min"


def test_no_menor_a_is_a_minimum() -> None:
    """El orden de los operadores importa: «no menor a» no es «menor a»."""

    conditions = extract_conditions("experiencia no menor a 4 años")

    assert conditions[0].operator == "min"
    assert conditions[0].value == Decimal(4)


def test_maximum_operator_is_recognised() -> None:
    conditions = extract_conditions("se admiten como máximo 2 contratos vigentes")

    assert conditions[0].operator == "max"
    assert conditions[0].value == Decimal(2)


def test_indexed_value_in_smmlv() -> None:
    conditions = extract_conditions("patrimonio mínimo de 1.000 SMMLV")

    assert conditions[0].kind == "valor_indexado"
    assert conditions[0].unit == "smmlv"
    assert conditions[0].value == Decimal(1000)


def test_operator_defaults_to_minimum() -> None:
    """Sin operador explícito se asume mínimo: es la lectura prudente.

    Tratar un mínimo como máximo aceptaría como cumplido algo que no lo está.
    """

    conditions = extract_conditions("acreditar 5 años de experiencia")

    assert conditions[0].operator == "min"


def test_text_without_conditions_yields_nothing() -> None:
    """Sin condiciones objetivas el módulo no inventa una conclusión."""

    assert extract_conditions("El proponente debe acreditar capacidad técnica") == []


def test_different_magnitudes_are_not_confused() -> None:
    """«3 vehículos» y «3 años» no son comparables."""

    vehicles = extract_conditions("disponibilidad de 3 vehículos")
    years = extract_conditions("experiencia de 3 años")

    assert vehicles[0].qualified_unit == "cantidad:vehiculos"
    assert years[0].qualified_unit == "duracion:anios"
    assert vehicles[0].qualified_unit != years[0].qualified_unit


# --- Comparación ------------------------------------------------------------


def _condition(**overrides: object) -> Condition:
    base = {
        "kind": "duracion",
        "unit": "anios",
        "operator": "min",
        "value": Decimal(5),
        "raw": "cinco (5)",
    }
    base.update(overrides)
    return Condition(**base)  # type: ignore[arg-type]


def test_unknown_value_never_produces_non_compliance() -> None:
    """«No consta» no es «no alcanza».

    Confundirlos rechazaría oportunidades válidas, tan grave como aceptar una
    inválida.
    """

    rule, rationale = compare(_condition(), known={})

    assert rule == "dato_ausente"
    assert "no consta" in rationale


def test_known_value_above_requirement_satisfies() -> None:
    rule, _ = compare(_condition(), known={"duracion:anios": Decimal(7)})

    assert rule == "condicion_objetiva_satisfecha"


def test_known_value_exactly_at_requirement_satisfies() -> None:
    """«Mínimo 5 años» y 5 años cumplen: el límite es inclusivo."""

    rule, _ = compare(_condition(), known={"duracion:anios": Decimal(5)})

    assert rule == "condicion_objetiva_satisfecha"


def test_known_value_below_requirement_is_non_compliance() -> None:
    rule, rationale = compare(_condition(), known={"duracion:anios": Decimal(3)})

    assert rule == "condicion_objetiva_incumplida"
    assert "3" in rationale and "5" in rationale


def test_maximum_operator_inverts_the_comparison() -> None:
    condition = _condition(operator="max", value=Decimal(2))

    assert compare(condition, known={"duracion:anios": Decimal(1)})[0] == (
        "condicion_objetiva_satisfecha"
    )
    assert compare(condition, known={"duracion:anios": Decimal(5)})[0] == (
        "condicion_objetiva_incumplida"
    )


# --- Aplicación completa ----------------------------------------------------


def test_insufficient_experience_is_non_compliance() -> None:
    """El defecto que originó el módulo.

    Antes: un requisito de cinco años con una empresa de tres se proponía como
    «cumple» porque un fragmento sobre experiencia superaba el umbral de
    recuperación. Los números no se comparaban nunca.
    """

    outcome = run_rules(
        "El proponente debe acreditar mínimo cinco (5) años de experiencia",
        known={"duracion:anios": Decimal(3)},
    )

    assert outcome is not None
    assert outcome.state == "no_cumple"
    assert outcome.rule == "condicion_objetiva_incumplida"


def test_sufficient_experience_is_compliance() -> None:
    outcome = run_rules(
        "El proponente debe acreditar mínimo cinco (5) años de experiencia",
        known={"duracion:anios": Decimal(8)},
    )

    assert outcome is not None
    assert outcome.state == "cumple"
    assert outcome.rule == "condicion_objetiva_satisfecha"


def test_missing_company_data_goes_to_manual_review() -> None:
    outcome = run_rules(
        "patrimonio mínimo de 1.000 SMMLV",
        known=None,
    )

    assert outcome is not None
    assert outcome.state == "revision_manual"
    assert outcome.rule == "dato_ausente"


def test_requirement_without_conditions_defers_to_semantic_comparison() -> None:
    """Devuelve None, no una conclusión inventada."""

    assert run_rules("El proponente debe acreditar capacidad técnica", known={}) is None


def test_the_worst_condition_decides() -> None:
    """Un requisito con dos condiciones no se cumple por satisfacer una.

    Quedarse con la primera evaluada haría que el resultado dependiera del orden
    en que aparecen las condiciones en el texto.
    """

    text = "mínimo 5 años de experiencia y como máximo 2 contratos vigentes"
    outcome = run_rules(
        text,
        known={"duracion:anios": Decimal(8), "cantidad:contratos": Decimal(5)},
    )

    assert outcome is not None
    assert outcome.state == "no_cumple"


def test_outcome_records_inputs_rule_and_reason() -> None:
    """HU-29: cada cálculo conserva entradas, regla, resultado y motivo."""

    outcome = run_rules(
        "mínimo cinco (5) años de experiencia",
        known={"duracion:anios": Decimal(3)},
    )
    assert outcome is not None

    assert outcome.inputs["magnitud"] == "duracion:anios"
    assert outcome.inputs["exigido"] == "5"
    assert outcome.inputs["acreditado"] == "3"
    assert outcome.inputs["operador"] == "min"
    assert outcome.rule
    assert outcome.rationale


def test_state_vocabulary_is_closed() -> None:
    """Un estado fuera del vocabulario controlado rompería la auditoría."""

    with pytest.raises(ValueError, match="vocabulario"):
        RuleOutcome(state="aprobado", rule="x", rationale="y", inputs={})


def test_ocr_without_accents_is_still_understood() -> None:
    """El OCR pierde tildes con frecuencia; el requisito debe seguir leyéndose."""

    outcome = run_rules(
        "El proponente debe acreditar minimo cinco (5) anos de experiencia",
        known={"duracion:anios": Decimal(2)},
    )

    assert outcome is not None
    assert outcome.state == "no_cumple"
