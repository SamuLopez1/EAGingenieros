#!/usr/bin/env python3
"""Comprueba si el numero de proceso de SECOP I cruza con la referencia de SECOP II.

Es la verificacion de la que depende la deduplicacion entre fuentes: si el
cruce no funciona, agrupar por referencia produciria grupos falsos o ninguno.

Prueba de red explicita y acotada: 2 peticiones, 12 filas. Sin LIKE ni upper():
una busqueda no indexada sobre estos conjuntos tarda minutos y no aporta nada
que la coincidencia exacta no responda ya.
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
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        return json.loads(response.read())


def norm(value: object) -> str:
    """Normalizacion conservadora: mayusculas y sin separadores."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\s\-_/.]", "", value).upper()


secop1 = get(
    "f789-7hwg",
    {
        "$select": "uid,numero_de_proceso,nombre_entidad,fecha_de_cargue_en_el_secop",
        "$where": "anno_cargue_secop=2026 AND numero_de_proceso IS NOT NULL",
        "$order": "uid DESC",
        "$limit": "12",
    },
)
print(f"SECOP I: {len(secop1)} filas de 2026")
for row in secop1:
    print(f"   numero={row.get('numero_de_proceso')!r:28} entidad={(row.get('nombre_entidad') or '')[:38]}")

refs = sorted({r["numero_de_proceso"] for r in secop1 if r.get("numero_de_proceso")})
print(f"\nreferencias distintas: {len(refs)}")

quoted = ",".join("'" + r.replace("'", "''") + "'" for r in refs)
secop2 = get(
    "p6dx-8zbt",
    {
        "$select": "id_del_proceso,referencia_del_proceso,entidad",
        "$where": f"referencia_del_proceso IN ({quoted})",
        "$limit": "200",
    },
)
found = {r["referencia_del_proceso"] for r in secop2 if r.get("referencia_del_proceso")}

print(f"SECOP II: {len(secop2)} coincidencias exactas")
print(f"RESULTADO: {len(found)} de {len(refs)} referencias de SECOP I estan en SECOP II\n")

for ref in refs:
    mark = "OK  " if ref in found else "NO  "
    print(f"  {mark}{ref}")

# Segunda comprobacion: coincidencia normalizada mediante OR de variantes.
# Se hace con igualdad exacta sobre la forma normalizada, no con LIKE, para
# que Socrata pueda usar indice.
sin_match = [r for r in refs if r not in found]
if sin_match:
    variantes = set()
    for ref in sin_match:
        variantes.add(ref.upper())
        variantes.add(ref.lower())
        variantes.add(norm(ref))
    quoted2 = ",".join("'" + v.replace("'", "''") + "'" for v in sorted(variantes))
    secop2b = get(
        "p6dx-8zbt",
        {
            "$select": "referencia_del_proceso",
            "$where": f"referencia_del_proceso IN ({quoted2})",
            "$limit": "200",
        },
    )
    rescatadas = {r["referencia_del_proceso"] for r in secop2b if r.get("referencia_del_proceso")}
    print(f"\nRecuperadas por normalizacion de caja/separadores: {len(rescatadas)}")
    for value in sorted(rescatadas):
        print(f"   {value!r}")

    # Coincidencia por la forma normalizada en ambos lados.
    def normalizados(dataset: str, campo: str, limite: str) -> set[str]:
        rows = get(dataset, {"$select": campo, "$limit": limite})
        return {norm(r.get(campo)) for r in rows}

    print("\nComprobacion final: se comparan formas normalizadas de una muestra")
    print("amplia de cada fuente, para medir solapamiento real sin depender del orden.")
    ii_norm = normalizados("p6dx-8zbt", "referencia_del_proceso", "500")
    print(f"  SECOP II: {len(ii_norm)} referencias normalizadas distintas en 500 filas")
    hits = sum(1 for ref in refs if norm(ref) in ii_norm)
    print(f"  De las {len(refs)} de SECOP I, {hits} aparecen normalizadas en esa muestra")
