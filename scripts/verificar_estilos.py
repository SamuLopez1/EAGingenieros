#!/usr/bin/env python3
"""Verifica que las reglas visuales del sistema de diseño se aplican de verdad.

No comprueba gustos: comprueba el contrato de docs/design/DESIGN.md, que tiene
reglas verificables —cifras tabulares, canvas claro, reglas horizontales, el
color nunca como única señal—.

Requisitos para ejecutarlo
--------------------------
  · El stack en marcha:  docker compose up -d
  · Playwright instalado en un entorno aparte, no en el del proyecto:
        python3 -m venv tmp/pw-venv
        tmp/pw-venv/bin/pip install playwright
        PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright \
          tmp/pw-venv/bin/python scripts/verificar_ui.py

  · Una cuenta con acceso. El script usa analista@eag.local; se crea con:
        docker compose exec api python -m scripts.crear_admin \
          --email analista@eag.local --password '...' --role administrador

No forma parte de la suite de pruebas: necesita un navegador, un servidor en
marcha y datos sincronizados. Es una comprobación de extremo a extremo que se
ejecuta a propósito, no en cada cambio.
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("EAG_VERIFY_BASE", "http://127.0.0.1:8082")

# Credenciales por entorno, nunca escritas aquí: una contraseña versionada
# sobrevive en el historial de Git aunque se borre después.
EMAIL = os.environ.get("EAG_VERIFY_EMAIL", "analista@eag.local")
PASSWORD = os.environ.get("EAG_VERIFY_PASSWORD", "")

if not PASSWORD:
    raise SystemExit(
        "Falta EAG_VERIFY_PASSWORD. Pásela por entorno; no se escribe en el archivo."
    )

fallos: list[str] = []


def comprobar(condicion: bool, descripcion: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLO'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.fill("#email", EMAIL)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector("table.dense", timeout=15000)

    print("\n1. Canvas claro para lectura prolongada")
    fondo = page.evaluate("getComputedStyle(document.body).backgroundColor")
    comprobar(fondo in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"), f"el canvas es claro ({fondo})")
    tinta = page.evaluate("getComputedStyle(document.body).color")
    comprobar(tinta == "rgb(13, 37, 61)", f"el texto usa el azul marino de la marca ({tinta})")

    print("\n2. Cifras tabulares donde hay números")
    tabular = page.evaluate("""
        () => {
          const celdas = [...document.querySelectorAll('table.dense tbody td.tnum')];
          if (!celdas.length) return {n: 0};
          const estilos = celdas.map(c => getComputedStyle(c).fontVariantNumeric);
          return {n: celdas.length, todas: estilos.every(v => v.includes('tabular-nums'))};
        }
    """)
    comprobar(tabular["n"] > 0, f"hay celdas numéricas ({tabular['n']})")
    comprobar(bool(tabular.get("todas")), "todas aplican tabular-nums")

    print("\n3. Densidad: solo reglas horizontales")
    reglas = page.evaluate("""
        () => {
          const filas = [...document.querySelectorAll('table.dense tbody tr')].slice(0, 3);
          return filas.map(f => {
            const s = getComputedStyle(f);
            return {abajo: s.borderBottomWidth, lados: s.borderLeftWidth + '/' + s.borderRightWidth};
          });
        }
    """)
    comprobar(bool(reglas), f"se inspeccionaron {len(reglas)} filas")
    comprobar(
        all(r["lados"] == "0px/0px" for r in reglas),
        "ninguna fila tiene reglas verticales",
    )

    print("\n4. La procedencia no depende del color")
    insignias = page.evaluate("""
        () => [...document.querySelectorAll('.source-badge')].slice(0, 3)
                .map(b => b.textContent.trim())
    """)
    comprobar(
        all(t for t in insignias),
        f"cada insignia lleva su texto: {insignias}",
    )

    print("\n5. El aviso de cobertura parcial no usa el color de error")
    aviso = page.evaluate("""
        () => {
          const el = document.querySelector('.coverage-state.is-warn');
          return el ? getComputedStyle(el).color : null;
        }
    """)
    comprobar(aviso is not None, "existe el aviso de cobertura")
    # Ámbar de «parcial», nunca el rojo de «no cumple»: una cobertura
    # incompleta no es un incumplimiento.
    comprobar(aviso == "rgb(138, 90, 31)", f"usa el ámbar de parcial, no el rojo ({aviso})")

    print("\n6. Área de trabajo con ancho suficiente")
    ancho = page.evaluate("""
        () => document.querySelector('table.dense').getBoundingClientRect().width
    """)
    comprobar(ancho > 1000, f"la tabla ocupa el ancho de trabajo ({ancho:.0f}px)")

    print("\n7. Accesibilidad: encabezados de columna con scope")
    alcance = page.evaluate("""
        () => {
          const ths = [...document.querySelectorAll('table.dense thead th')];
          return {total: ths.length, conScope: ths.filter(t => t.getAttribute('scope') === 'col').length};
        }
    """)
    comprobar(
        alcance["total"] == alcance["conSecho"] if "conSecho" in alcance else alcance["total"] == alcance["conScope"],
        f"todas las columnas declaran scope=col ({alcance['conScope']}/{alcance['total']})",
    )

    browser.close()

print("\n" + "=" * 60)
if fallos:
    print(f"FALLOS: {len(fallos)}")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("El contrato visual se cumple.")
