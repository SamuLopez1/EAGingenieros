"""Reglas deterministas para condiciones objetivas de un requisito (HU-29).

Por qué esto existe, y no basta con recuperación semántica
----------------------------------------------------------

La comparación semántica decide por relevancia: si un fragmento de la empresa
habla de experiencia y su puntuación supera el umbral, propone «cumple». Eso
funciona para condiciones interpretables —«capacidad técnica acreditada»— pero
**falla en las objetivas**. Ante el requisito «mínimo cinco (5) años de
experiencia», un fragmento sobre experiencia con buena puntuación producía un
«cumple» aunque la empresa tuviera tres años: nunca se comparaban los números.

Ese es un falso cumplimiento, y es el error más caro que este sistema puede
cometer: el analista lo llevaría al informe y la empresa se presentaría a una
licitación que no cumple. HU-42 lo trata como bloqueante del lanzamiento.

Las condiciones objetivas —años, cantidades, plazos, valores, vigencias— se
comparan aquí con aritmética, y el resultado queda registrado con sus entradas,
su regla y su motivo, de modo que sea reproducible y auditable.

La regla que gobierna el módulo
-------------------------------

    Dato desconocido → revisión manual. Nunca incumplimiento.

«No consta el patrimonio» no es «el patrimonio no alcanza». La primera es una
falta de información que una persona puede resolver aportando el dato; la segunda
es un incumplimiento demostrado. Confundirlas rechazaría oportunidades válidas,
que es tan grave como aceptar una inválida.

Y al contrario: un dato conocido que no alcanza **sí** es incumplimiento, y se
declara. Es la única forma de que «no_cumple» signifique algo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# --- Vocabulario ------------------------------------------------------------

# Palabras de cantidad que aparecen escritas en los pliegos. Se incluyen las
# formas con tilde y sin ella porque el OCR las pierde con frecuencia.
_NUMBER_WORDS: dict[str, int] = {
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
    "doscientos": 200, "trescientos": 300, "cuatrocientos": 400,
    "quinientos": 500, "seiscientos": 600, "setecientos": 700,
    "ochocientos": 800, "novecientos": 900, "mil": 1000,
}

# Operadores. El orden importa: se prueban de más específico a más general, de
# modo que «no menor a» no se lea como «menor a».
_OPERATORS: tuple[tuple[str, str], ...] = (
    (r"no\s+(?:menor|inferior)\s+(?:a|que)", "min"),
    (r"igual\s+o\s+(?:superior|mayor)\s+(?:a|que)", "min"),
    (r"(?:m[íi]nim[oa]|al\s+menos|por\s+lo\s+menos|como\s+m[íi]nimo)", "min"),
    (r"no\s+(?:mayor|superior)\s+(?:a|que)", "max"),
    (r"igual\s+o\s+(?:inferior|menor)\s+(?:a|que)", "max"),
    (r"(?:m[áa]xim[oa]|como\s+m[áa]ximo|hasta)", "max"),
    (r"superior\s+(?:a|que)", "min"),
    (r"mayor\s+(?:a|que)", "min"),
    (r"inferior\s+(?:a|que)", "max"),
    (r"menor\s+(?:a|que)", "max"),
)

# Unidades reconocidas y el tipo de condición al que pertenecen.
# `anios` y `meses` son magnitudes de tiempo; `smmlv` es una unidad monetaria
# indexada, no un valor absoluto, y por eso se compara contra el número de
# salarios y no contra pesos.
_UNITS: tuple[tuple[str, str, str], ...] = (
    (r"a[ñn]os?", "duracion", "anios"),
    (r"meses?", "duracion", "meses"),
    (r"d[íi]as?", "duracion", "dias"),
    (r"(?:salarios?\s+m[íi]nimos?|smmlv|smlmv)", "valor_indexado", "smmlv"),
    (r"veh[íi]culos?", "cantidad", "vehiculos"),
    (r"equipos?", "cantidad", "equipos"),
    (r"unidades?", "cantidad", "unidades"),
    (r"personas?|profesionales?", "cantidad", "personas"),
    (r"contratos?", "cantidad", "contratos"),
)

# Fracción de tiempo expresada en palabras del pliego.
_ORDINAL_FRACTIONS = {
    "medio": Decimal("0.5"),
    "media": Decimal("0.5"),
}

# Máximo de caracteres hacia atrás que se miran para encontrar el operador. Si
# está más lejos, probablemente pertenece a otra frase.
_OPERATOR_WINDOW = 60


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse_number(token: str) -> Decimal | None:
    """Interpreta un número escrito con dígitos o con palabras.

    Los pliegos escriben «cinco (5) años» o «1.000 SMMLV». El formato
    colombiano usa punto para los miles y coma para los decimales, y ese orden
    hay que respetarlo: interpretar «1.000» como 1.0 cambiaría el requisito por
    un factor de mil.
    """

    cleaned = token.strip().lower()

    if cleaned in _ORDINAL_FRACTIONS:
        return _ORDINAL_FRACTIONS[cleaned]
    if cleaned in _NUMBER_WORDS:
        return Decimal(_NUMBER_WORDS[cleaned])

    digits = re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", cleaned)
    if digits:
        # Formato de miles colombiano: se quitan los puntos y la coma es decimal.
        normalised = cleaned.replace(".", "").replace(",", ".")
        try:
            return Decimal(normalised)
        except InvalidOperation:
            return None

    digits = re.fullmatch(r"\d+(?:[.,]\d+)?", cleaned)
    if digits:
        try:
            return Decimal(cleaned.replace(",", "."))
        except InvalidOperation:
            return None
    return None


@dataclass(frozen=True)
class Condition:
    """Una condición objetiva extraída del texto de un requisito."""

    kind: str  # duracion | cantidad | valor_indexado
    unit: str  # anios | meses | smmlv | vehiculos | ...
    operator: str  # min | max
    value: Decimal
    raw: str = field(repr=False, default="")

    @property
    def qualified_unit(self) -> str:
        """Unidad con su tipo, para no comparar magnitudes distintas.

        «3 vehículos» y «3 años» no son comparables aunque ambos sean cantidades:
        la clave incluye el tipo para que una comparación cruzada sea imposible
        por construcción y no dependa de que alguien la recuerde.
        """

        return f"{self.kind}:{self.unit}"


def _find_operator(context: str) -> str:
    """Devuelve el operador de la ventana de texto previa al valor."""

    for pattern, operator in _OPERATORS:
        if re.search(pattern, context):
            return operator
    # Sin operador explícito, un requisito de pliego establece un mínimo: es la
    # lectura prudente, porque tratar un mínimo como máximo aceptaría un
    # cumplimiento que no lo es.
    return "min"


def extract_conditions(text: str) -> list[Condition]:
    """Extrae las condiciones objetivas de un requisito.

    Es deliberadamente conservador: si no reconoce con seguridad un número y su
    unidad, no inventa una condición. Un requisito sin condiciones extraídas cae
    a la comparación semántica, que es el comportamiento anterior; inventar una
    condición sería peor que no extraerla.

    Las apariciones se recogen **todas primero** y se recorren en orden de
    posición. Es necesario para acotar la búsqueda del operador: si cada patrón
    se procesara por separado, el «mínimo» de una condición anterior quedaría
    dentro de la ventana de la siguiente y «como máximo 2 contratos» se leería
    como un mínimo. Ese fallo invierte el sentido de un requisito.
    """

    normalised = strip_accents(text).lower()

    occurrences: list[tuple[int, int, str, str]] = []
    for pattern, kind, unit in _UNITS:
        for match in re.finditer(pattern, normalised):
            occurrences.append((match.start(), match.end(), kind, unit))
    occurrences.sort()

    conditions: list[Condition] = []
    seen: set[tuple[str, str]] = set()
    previous_end = 0

    for start, end, kind, unit in occurrences:
        prefix = normalised[:start]
        value, raw, value_start = _last_value_before(prefix)
        if value is None:
            continue

        # La ventana del operador va desde donde terminó la condición anterior
        # hasta el valor actual. Acotarla por la izquierda es lo que impide que
        # el operador de una condición se aplique a la siguiente.
        window_start = max(previous_end, value_start - _OPERATOR_WINDOW)
        operator = _find_operator(normalised[window_start:value_start])

        previous_end = end
        key = (f"{kind}:{unit}", operator)
        if key in seen:
            continue
        seen.add(key)
        conditions.append(
            Condition(kind=kind, unit=unit, operator=operator, value=value, raw=raw)
        )

    return conditions


def _last_value_before(prefix: str) -> tuple[Decimal | None, str, int]:
    """Busca el número inmediatamente anterior a una unidad.

    Devuelve el valor, el texto reconocido y la posición donde empieza, que hace
    falta para acotar la ventana del operador.

    Se miran primero los dígitos entre paréntesis —el caso «cinco (5) años»,
    donde el número útil es el del paréntesis—, después los dígitos sueltos y por
    último la palabra de cantidad.
    """

    tail_start = max(0, len(prefix) - 40)
    tail = prefix[tail_start:]

    parenthetical = re.search(r"\(\s*(\d[\d.,]*)\s*\)\s*$", tail)
    if parenthetical:
        value = parse_number(parenthetical.group(1))
        if value is not None:
            return value, parenthetical.group(0).strip(), tail_start + parenthetical.start()

    digits = re.search(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*$", tail)
    if digits:
        value = parse_number(digits.group(1))
        if value is not None:
            return value, digits.group(0).strip(), tail_start + digits.start()

    words = re.search(r"([a-z]+)\s*$", tail)
    if words:
        value = parse_number(words.group(1))
        if value is not None:
            return value, words.group(0).strip(), tail_start + words.start()

    return None, "", 0


def compare(
    condition: Condition,
    *,
    known: dict[str, Decimal] | None,
) -> tuple[str, str]:
    """Compara una condición con el valor conocido de la empresa.

    Devuelve ``(regla, motivo)`` y el estado se deriva en `run_rules`. Se separa
    para que el cálculo sea comprobable por sí solo.

    Los tres desenlaces posibles, y por qué:

    - **Sin dato** → no se puede afirmar nada. No es incumplimiento.
    - **Cumple la condición** → cumplimiento objetivo, demostrado por aritmética.
    - **No la cumple** → incumplimiento demostrado. Es el único caso en que el
      sistema dice «no_cumple» sin intervención humana, y lo hace porque la
      comparación es reproducible y verificable.
    """

    value = (known or {}).get(condition.qualified_unit)
    if value is None:
        return (
            "dato_ausente",
            f"no consta el dato de la empresa para «{condition.qualified_unit}»: "
            "no se puede comparar y la falta de información no es incumplimiento",
        )

    if condition.operator == "min":
        satisfied = value >= condition.value
        relation = f"{value} >= {condition.value}"
    else:
        satisfied = value <= condition.value
        relation = f"{value} <= {condition.value}"

    if satisfied:
        return (
            "condicion_objetiva_satisfecha",
            f"la empresa acredita {value} {condition.unit} y el requisito exige "
            f"{'al menos' if condition.operator == 'min' else 'como máximo'} "
            f"{condition.value} {condition.unit} ({relation})",
        )

    return (
        "condicion_objetiva_incumplida",
        f"la empresa acredita {value} {condition.unit} y el requisito exige "
        f"{'al menos' if condition.operator == 'min' else 'como máximo'} "
        f"{condition.value} {condition.unit} ({relation}): incumplimiento "
        "demostrado por comparación de los dos valores",
    )


@dataclass(frozen=True)
class RuleOutcome:
    """Resultado de aplicar las reglas a un requisito.

    Conserva entradas, regla, resultado y motivo, que es lo que HU-29 exige para
    que un cálculo sea auditable.
    """

    state: str
    rule: str
    rationale: str
    inputs: dict[str, object]

    def __post_init__(self) -> None:
        if self.state not in ("cumple", "cumple_parcialmente", "no_cumple", "revision_manual"):
            raise ValueError(f"estado fuera del vocabulario controlado: {self.state!r}")


def run_rules(
    text: str,
    *,
    known: dict[str, Decimal] | None,
) -> RuleOutcome | None:
    """Aplica reglas deterministas al texto de un requisito.

    Devuelve ``None`` cuando el requisito no contiene condiciones objetivas: en
    ese caso la decisión corresponde a la comparación semántica y este módulo no
    debe fingir una conclusión que no puede sostener.
    """

    conditions = extract_conditions(text)
    if not conditions:
        return None

    # Se evalúan todas y gana la más desfavorable para el proponente. Un
    # requisito que exige «5 años de experiencia y máximo 2 contratos vigentes»
    # no se cumple por satisfacer solo una parte: quedarse con la primera
    # condición evaluada haría que el resultado dependiera del orden del texto.
    priority = {"no_cumple": 3, "revision_manual": 2, "cumple_parcialmente": 1, "cumple": 0}
    worst: RuleOutcome | None = None

    for condition in conditions:
        rule, rationale = compare(condition, known=known)
        if rule == "condicion_objetiva_satisfecha":
            state = "cumple"
        elif rule == "condicion_objetiva_incumplida":
            state = "no_cumple"
        else:
            state = "revision_manual"

        inputs: dict[str, object] = {
            "magnitud": condition.qualified_unit,
            "operador": condition.operator,
            "exigido": str(condition.value),
            "acreditado": (
                str(known[condition.qualified_unit])
                if known and condition.qualified_unit in known
                else None
            ),
            "texto_reconocido": condition.raw,
        }
        outcome = RuleOutcome(state=state, rule=rule, rationale=rationale, inputs=inputs)
        if worst is None or priority[state] > priority[worst.state]:
            worst = outcome

    return worst
