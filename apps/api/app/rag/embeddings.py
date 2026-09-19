"""Adaptadores de representación vectorial (embeddings).

El sistema necesita convertir texto en vectores, pero no debe quedar atado a un
proveedor. Este módulo define el contrato y dos implementaciones:

- **`HashingEmbedder`**: representación local por *feature hashing* sobre
  palabras y bigramas. No requiere red, no cuesta nada y es determinista. **No
  entiende de significado**: dos frases que dicen lo mismo con palabras
  distintas no se parecen. Sirve para que el sistema funcione y se pueda probar
  de extremo a extremo, no para producción.

- **`HttpEmbedder`**: cliente de un servicio compatible con la API de
  embeddings de OpenAI. Es el que se usará con un modelo real, configurando URL,
  clave y nombre del modelo.

Por qué el modelo se identifica con una cadena y se guarda por fragmento: un
cambio de modelo cambia el espacio vectorial. Mezclar vectores de dos modelos en
una búsqueda devuelve resultados arbitrarios **sin dar error**, que es el peor
tipo de fallo. Guardar el identificador permite filtrar y detectar qué falta
reindexar.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Protocol

import httpx

from app.db.knowledge_models import EMBEDDING_DIMENSIONS

_WORD = re.compile(r"[a-záéíóúñü0-9]+")

# Palabras vacías del español. Se excluyen porque aparecen en todos los
# fragmentos y dominarían la representación sin aportar señal discriminante.
_STOPWORDS = frozenset(
    {
        "de", "la", "el", "en", "y", "a", "los", "del", "se", "las", "por", "un",
        "para", "con", "no", "una", "su", "al", "lo", "como", "más", "pero",
        "sus", "le", "ya", "o", "este", "sí", "porque", "esta", "entre", "cuando",
        "muy", "sin", "sobre", "también", "me", "hasta", "hay", "donde", "quien",
        "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni", "contra",
        "otros", "ese", "eso", "ante", "ellos", "e", "esto", "mí", "antes",
        "algunos", "qué", "unos", "yo", "otro", "otras", "otra", "él", "tanto",
        "esa", "estos", "mucho", "quienes", "nada", "muchos", "cual", "poco",
        "ella", "estar", "estas", "algunas", "algo", "nosotros", "mi", "mis",
        "tú", "te", "ti", "tu", "tus", "ellas", "nosotras", "vosotros", "vosotras",
        "os", "mío", "mía", "míos", "mías", "tuyo", "tuya", "tuyos", "tuyas",
        "suyo", "suya", "suyos", "suyas", "nuestro", "nuestra", "vuestro",
        "vuestra", "es", "son", "ser", "fue", "era", "ha", "han", "haber",
    }
)


class Embedder(Protocol):
    """Contrato de representación vectorial."""

    @property
    def model_id(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _tokens(text: str) -> list[str]:
    """Extrae palabras significativas y bigramas.

    Los bigramas aportan algo de contexto: «interventoría vial» como unidad
    distingue mejor que «interventoría» y «vial» por separado.
    """

    words = [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
    return words + bigrams


class HashingEmbedder:
    """Representación local determinista, sin red ni coste.

    Usa *feature hashing*: cada término se proyecta a una posición del vector
    mediante un hash estable, y el valor es su frecuencia ponderada. Dos textos
    con las mismas palabras se parecen; dos que dicen lo mismo con sinónimos, no.

    Por eso **no sirve para producción**: en este dominio un pliego puede exigir
    «experiencia en interventoría» y el certificado decir «supervisión de obra»,
    que es lo mismo. Encontrar esa equivalencia requiere un modelo con
    conocimiento semántico. Este adaptador existe para que el sistema sea
    ejecutable y comprobable de extremo a extremo sin depender de un proveedor.
    """

    def __init__(self, *, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        return f"hashing-local-v1-{self._dimensions}"

    def _bucket(self, token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        # El bit alto decide el signo: sin él, todos los términos se sumarían y
        # vectores de textos distintos tenderían a parecerse.
        sign = 1.0 if value & 1 else -1.0
        return (value >> 1) % self._dimensions, sign

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            counts = Counter(_tokens(text))
            vector = [0.0] * self._dimensions
            for token, count in counts.items():
                index, sign = self._bucket(token)
                # Ponderación sublineal: una palabra repetida diez veces no debe
                # pesar diez veces más que una que aparece una sola vez.
                vector[index] += sign * (1.0 + math.log(count))
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0:
                vector = [v / norm for v in vector]
            vectors.append(vector)
        return vectors


class EmbeddingServiceError(RuntimeError):
    """El proveedor de representaciones no respondió o respondió mal."""


class HttpEmbedder:
    """Cliente de un servicio de embeddings compatible con OpenAI.

    La clave viaja solo en la cabecera `Authorization` y nunca se registra. Los
    errores se acotan a su tipo y código, sin incluir el cuerpo de la respuesta:
    puede contener la URL con la clave.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int = EMBEDDING_DIMENSIONS,
        timeout: float = 30.0,
        batch_size: int = 32,
    ) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key y model son obligatorios")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout
        self._batch_size = batch_size

    @property
    def model_id(self) -> str:
        # La dimensión forma parte de la identidad: dos modelos con el mismo
        # nombre pero distinta dimensión producen espacios vectoriales distintos.
        return f"{self._model}@{self._dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": batch},
                timeout=self._timeout,
            )
        except httpx.HTTPError as error:
            raise EmbeddingServiceError(
                f"fallo de red al calcular representaciones: {type(error).__name__}"
            ) from error

        if response.status_code >= 400:
            raise EmbeddingServiceError(
                f"el proveedor de representaciones respondió {response.status_code}"
            )

        try:
            payload = response.json()
            items = sorted(payload["data"], key=lambda item: item["index"])
            result = [list(map(float, item["embedding"])) for item in items]
        except (ValueError, KeyError, TypeError) as error:
            raise EmbeddingServiceError("respuesta del proveedor con forma inesperada") from error

        if len(result) != len(batch):
            raise EmbeddingServiceError(
                f"el proveedor devolvió {len(result)} vectores para {len(batch)} textos"
            )
        for vector in result:
            if len(vector) != self._dimensions:
                raise EmbeddingServiceError(
                    f"el proveedor devolvió vectores de {len(vector)} dimensiones, "
                    f"se esperaban {self._dimensions}"
                )
        return result


def build_embedder(settings) -> Embedder:  # type: ignore[no-untyped-def]
    """Construye el representador según la configuración disponible.

    Sin proveedor configurado se usa el local, y el modo se declara en `/health`
    para que nadie confunda una demostración con un entorno semántico real.
    """

    if settings.embeddings_are_configured:
        return HttpEmbedder(
            base_url=settings.require_embeddings_base_url(),
            api_key=settings.require_embeddings_api_key(),
            model=settings.embeddings_model or "desconocido",
            dimensions=settings.embeddings_dimensions,
        )
    return HashingEmbedder(dimensions=settings.embeddings_dimensions)
