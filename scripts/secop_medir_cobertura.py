#!/usr/bin/env python3
"""Mide el solapamiento SECOP I -> SECOP II con una muestra mayor.

El documento docs/SECOP_COBERTURA.md afirma 12 de 12. La primera medicion dio
4 de 12, asi que se amplia la muestra para decidir cual de las dos sostiene una
muestra grande. Tambien se comprueba si `referencia_del_proceso` es unica en
SECOP II, que es un requisito para poder usarla como clave de agrupacion.

Prueba de red explicita y acotada: 4 peticiones.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

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


# --- Muestra amplia de SECOP I ---------------------------------------------
rows = get(
    "f789-7hwg",
    {
        "$select": "numero_de_proceso",
        "$where": "anno_cargue_secop=2026 AND numero_de_proceso IS NOT NULL",
        "$order": "uid DESC",
        "$limit": "400",
    },
)
refs = sorted({r["numero_de_proceso"] for r in rows if r.get("numero_de_proceso")})
print(f"SECOP I: {len(rows)} filas -> {len(refs)} referencias unicas (2026, uid DESC)")


def cruzar(valores: list[str], etiqueta: str) -> set[str]:
    """Pregunta a SECOP II por un conjunto de referencias, en un solo $where."""

    quoted = ",".join("'" + v.replace("'", "''") + "'" for v in valores)
    answer = get(
        "p6dx-8zbt",
        {
            "$select": "referencia_del_proceso,id_del_proceso",
            "$where": f"referencia_del_proceso IN ({quoted})",
            "$limit": "5000",
        },
    )
    encontradas = {
        r["referencia_del_proceso"] for r in answer if r.get("referencia_del_proceso")
    }
    print(f"\n{etiqueta}: {len(valores)} consultadas -> {len(encontradas)} presentes")
    print(f"  filas devueltas por SECOP II: {len(answer)}")

    # Si hay mas filas que referencias distintas, la referencia no es unica:
    # eso invalida usarla como clave de identidad y obliga a agrupar.
    if encontradas and len(answer) > len(encontradas):
        from collections import Counter

        conteo = Counter(r["referencia_del_proceso"] for r in answer)
        repetidas = [(k, v) for k, v in conteo.most_common(5) if v > 1]
        print(f"  AVISO: referencia_del_proceso NO es unica. Ejemplos: {repetidas}")
    return encontradas


# Por lotes para que neither la URL ni la respuesta crezcan demasiado.
presentes: set[str] = set()
LOTE = 50
for inicio in range(0, len(refs), LOTE):
    lote = refs[inicio : inicio + LOTE]
    presentes |= cruzar(lote, f"lote {inicio // LOTE + 1}")

print("\n" + "=" * 68)
print("RESULTADO SECOP I -> SECOP II (coincidencia exacta)")
print(f"  referencias de SECOP I        : {len(refs)}")
print(f"  presentes en SECOP II         : {len(presentes)}")
print(f"  cobertura                     : {100 * len(presentes) / len(refs):.1f} %")
print(f"  solo en SECOP I               : {len(refs) - len(presentes)}")

# --- Direccion inversa: referencias de SECOP II presentes en SECOP I -------
ii = get(
    "p6dx-8zbt",
    {
        "$select": "referencia_del_proceso",
        "$where": "fecha_de_publicacion_del IS NOT NULL",
        "$order": "id_del_proceso DESC",
        "$limit": "400",
    },
)
ii_refs = sorted({r["referencia_del_proceso"] for r in ii if r.get("referencia_del_proceso")})
print(f"\nSECOP II: {len(ii)} filas -> {len(ii_refs)} referencias unicas")

en_i: set[str] = set()
for inicio in range(0, len(ii_refs), LOTE):
    lote = ii_refs[inicio : inicio + LOTE]
    quoted = ",".join("'" + v.replace("'", "''") + "'" for v in lote)
    answer = get(
        "f789-7hwg",
        {
            "$select": "numero_de_proceso",
            "$where": f"numero_de_proceso IN ({quoted})",
            "$limit": "5000",
        },
    )
    en_i |= {r["numero_de_proceso"] for r in answer if r.get("numero_de_proceso")}

print("\nRESULTADO SECOP II -> SECOP I (coincidencia exacta)")
print(f"  referencias de SECOP II       : {len(ii_refs)}")
print(f"  presentes en SECOP I          : {len(en_i)}")
print(f"  cobertura                     : {100 * len(en_i) / len(ii_refs):.1f} %")
