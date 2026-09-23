#!/usr/bin/env python3
"""Determina la clave correcta para agrupar el mismo proceso entre fuentes.

Hallazgo previo: `referencia_del_proceso` NO es unica en SECOP II —'001-2026'
aparece 1139 veces—, asi que no sirve como clave por si sola. Se comprueba si
la pareja (NIT de entidad, referencia) si es unica y cuanto solapamiento real
queda con esa clave mas estricta.

Prueba de red explicita y acotada.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections import Counter

ROOT = "https://www.datos.gov.co/resource"


def get(dataset: str, params: dict[str, str]) -> list[dict]:
    url = f"{ROOT}/{dataset}.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def norm(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\s\-_/.]", "", value).upper()


def solo_digitos(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\D", "", value)


print("=" * 70)
print("1. Unicidad de (NIT, referencia) en SECOP II")
print("=" * 70)

# Se traen filas de SECOP II con NIT y referencia para medir duplicidad.
muestra_ii = get(
    "p6dx-8zbt",
    {
        "$select": "nit_entidad,referencia_del_proceso,id_del_proceso",
        "$where": "nit_entidad IS NOT NULL AND referencia_del_proceso IS NOT NULL",
        "$order": "id_del_proceso DESC",
        "$limit": "3000",
    },
)
print(f"filas traidas: {len(muestra_ii)}")

pares = Counter(
    (solo_digitos(r.get("nit_entidad")), norm(r.get("referencia_del_proceso")))
    for r in muestra_ii
)
refs_solas = Counter(norm(r.get("referencia_del_proceso")) for r in muestra_ii)

print(f"pares (nit, ref) distintos      : {len(pares)}")
print(f"referencias distintas           : {len(refs_solas)}")
print(f"reduccion de ambiguedad         : {len(refs_solas) - len(pares)} colisiones evitadas")

repetidos = [(k, v) for k, v in pares.most_common(5) if v > 1]
print(f"pares (nit, ref) que aun se repiten: {len([k for k, v in pares.items() if v > 1])}")
for par, veces in repetidos:
    print(f"   {par} -> {veces} filas")

print()
print("=" * 70)
print("2. Solapamiento real con la clave (NIT, referencia)")
print("=" * 70)

filas_i = get(
    "f789-7hwg",
    {
        "$select": "nit_de_la_entidad,numero_de_proceso",
        "$where": (
            "anno_cargue_secop=2026 AND numero_de_proceso IS NOT NULL "
            "AND nit_de_la_entidad IS NOT NULL"
        ),
        "$order": "uid DESC",
        "$limit": "400",
    },
)
pares_i = {
    (solo_digitos(r.get("nit_de_la_entidad")), norm(r.get("numero_de_proceso")))
    for r in filas_i
    if r.get("nit_de_la_entidad") and r.get("numero_de_proceso")
}
print(f"SECOP I: {len(filas_i)} filas -> {len(pares_i)} pares (nit, ref) unicos")

# El conjunto de NIT de la muestra es pequeno: se consulta SECOP II por esos
# NIT y se compara en memoria, en lugar de construir un IN de 300 parejas.
nits = sorted({nit for nit, _ in pares_i if nit})
print(f"NIT distintos en la muestra: {len(nits)}")

en_ii: set[tuple[str, str]] = set()
for inicio in range(0, len(nits), 40):
    lote = nits[inicio : inicio + 40]
    quoted = ",".join("'" + n.replace("'", "''") + "'" for n in lote)
    filas = get(
        "p6dx-8zbt",
        {
            "$select": "nit_entidad,referencia_del_proceso",
            "$where": f"nit_entidad IN ({quoted})",
            "$limit": "5000",
        },
    )
    for fila in filas:
        en_ii.add(
            (solo_digitos(fila.get("nit_entidad")), norm(fila.get("referencia_del_proceso")))
        )
    print(f"  lote {inicio // 40 + 1}: {len(lote)} NIT -> {len(en_ii)} pares acumulados")

presentes = pares_i & en_ii
print()
print("=" * 70)
print("RESULTADO con clave (NIT, referencia)")
print("=" * 70)
print(f"  pares de SECOP I              : {len(pares_i)}")
print(f"  presentes en SECOP II         : {len(presentes)}")
print(f"  cobertura                     : {100 * len(presentes) / len(pares_i):.1f} %")
print(f"  SOLO en SECOP I               : {len(pares_i) - len(presentes)}")
