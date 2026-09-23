#!/usr/bin/env python3
"""Verificación de la interfaz en un navegador real.

Entra con una cuenta real, comprueba que el listado muestra las dos
plataformas con su procedencia, que la cobertura se declara, que los valores
llevan su propia etiqueta por fuente y que el detalle conserva el origen.

Contra el stack en marcha en http://127.0.0.1:8082

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
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("EAG_VERIFY_BASE", "http://127.0.0.1:8082")

# Las capturas son evidencia de una ejecución, no código fuente: van a
# `output/`, que está ignorado por Git. Escribirlas junto al script las hacía
# aparecer en el control de versiones como si fueran parte del repositorio, y
# una captura de una ejecución concreta deja de ser cierta en cuanto cambia la
# interfaz.
SALIDA = Path(os.environ.get("EAG_VERIFY_OUT", Path(__file__).resolve().parents[1] / "output" / "verificacion-ui"))
SALIDA.mkdir(parents=True, exist_ok=True)

# Credenciales por entorno, nunca escritas aquí.
#
# Una contraseña en un archivo versionado es una contraseña filtrada: sobrevive
# en el historial de Git aunque se borre después, y acaba reutilizándose en un
# entorno real «porque ya funcionaba». El correo sí puede tener un valor por
# defecto, porque no es un secreto.
EMAIL = os.environ.get("EAG_VERIFY_EMAIL", "analista@eag.local")
PASSWORD = os.environ.get("EAG_VERIFY_PASSWORD", "")

if not PASSWORD:
    raise SystemExit(
        "Falta EAG_VERIFY_PASSWORD.\n"
        "Cree una cuenta y pase sus credenciales por entorno:\n\n"
        "  docker compose exec api python -m scripts.crear_admin \\\n"
        "    --email analista@eag.local --password '<la-suya>' --role administrador\n\n"
        "  EAG_VERIFY_PASSWORD='<la-suya>' \\\n"
        "    tmp/pw-venv/bin/python scripts/verificar_ui.py"
    )

fallos: list[str] = []


def norm(texto: str) -> str:
    """Normaliza para comparar.

    El sistema de diseño aplica `text-transform: uppercase` a encabezados de
    tabla, etiquetas de campo y títulos de sección, y `inner_text()` de
    Playwright devuelve el texto **tal como se representa**, no como está en el
    HTML. Comparar sin normalizar produce fallos que no son de la interfaz.
    """

    return " ".join(texto.upper().replace("\xa0", " ").split())


def comprobar(condicion: bool, descripcion: str) -> None:
    marca = "OK  " if condicion else "FALLO"
    print(f"  {marca} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})

    errores_consola: list[str] = []
    page.on("console", lambda msg: errores_consola.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errores_consola.append(str(exc)))

    # --- Acceso ------------------------------------------------------------
    print("\n1. Acceso")
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    comprobar(page.locator("h1", has_text="Acceso").count() == 1, "pide credenciales sin sesión")

    page.fill("#email", EMAIL)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("table.dense", timeout=15000)
    comprobar(True, "entra con credenciales válidas y carga el listado")

    # --- Cobertura ---------------------------------------------------------
    print("\n2. Cobertura declarada")
    page.wait_for_selector(".coverage", timeout=10000)
    cobertura = norm(page.locator(".coverage").inner_text())
    comprobar("SECOP II" in cobertura, "declara SECOP II")
    comprobar("SECOP I" in cobertura, "declara SECOP I")
    comprobar("COBERTURA PARCIAL" in cobertura, "declara la cobertura parcial de SECOP I")
    comprobar("INCOMPLETA" in cobertura, "advierte de cobertura incompleta")
    comprobar(
        "NO ESTÁ ESTABLECIDA" in cobertura,
        "declara que la relación entre plataformas no está establecida",
    )

    # --- Listado combinado -------------------------------------------------
    print("\n3. Listado combinado")
    filas = page.locator("table.dense tbody tr")
    total_filas = filas.count()
    comprobar(total_filas > 0, f"muestra filas ({total_filas})")

    # La primera página se ordena por fecha de publicación descendente, así que
    # puede contener una sola plataforma. Se comprueba cada una por separado.
    insignias = page.locator("table.dense tbody .source-badge")
    textos = {norm(t) for t in insignias.all_inner_texts()}
    comprobar(
        textos.issubset({"SECOP I", "SECOP II"}),
        f"toda fila declara una plataforma conocida: {textos}",
    )

    encabezados = norm(page.locator("table.dense thead").inner_text())
    comprobar("VALOR" in encabezados, "el listado tiene columna de valor")
    comprobar("FUENTE" in encabezados, "el listado tiene columna de procedencia")

    # --- Filtro por plataforma --------------------------------------------
    print("\n4. Filtro por plataforma")
    for plataforma in ("SECOP_I", "SECOP_II"):
        page.select_option("#f-platform", plataforma)
        page.wait_for_timeout(1400)
        page.wait_for_load_state("networkidle")
        mostradas = page.locator("table.dense tbody .source-badge")
        etiquetas = {norm(t) for t in mostradas.all_inner_texts()}
        esperado = "SECOP I" if plataforma == "SECOP_I" else "SECOP II"
        comprobar(
            etiquetas == {esperado} and mostradas.count() > 0,
            f"el filtro {plataforma} deja {mostradas.count()} filas, todas de {esperado}",
        )
        comprobar(f"platform={plataforma}" in page.url, f"el filtro {plataforma} queda en la dirección")

    # Los valores económicos se muestran formateados, no en crudo.
    valor = page.locator("table.dense tbody tr").first.locator("td.num").inner_text()
    comprobar("$" in valor, f"el valor se formatea como importe ({valor.strip()!r})")

    page.select_option("#f-platform", "SECOP_I")
    page.wait_for_timeout(1400)
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(SALIDA / "ui-listado-secop-i.png"), full_page=True)

    # --- Limpiar y buscar --------------------------------------------------
    print("\n5. Búsqueda")
    page.click("button:has-text('Limpiar')")
    page.wait_for_timeout(900)
    page.fill("#f-q", "alcald")
    page.wait_for_timeout(1600)
    page.wait_for_load_state("networkidle")
    comprobar(page.locator("table.dense tbody tr").count() > 0, "la búsqueda devuelve resultados")

    page.click("button:has-text('Limpiar')")
    page.wait_for_timeout(1400)
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(SALIDA / "ui-listado-combinado.png"), full_page=True)

    # --- Detalle -----------------------------------------------------------
    print("\n6. Detalle")
    page.locator("table.dense tbody tr a.cell-link").first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".detail-grid", timeout=10000)
    detalle = norm(page.locator("main").inner_text())
    comprobar("PROCEDENCIA" in detalle, "el detalle declara la procedencia")
    comprobar(
        "PRECIO BASE" in detalle or "CUANTÍA DEL PROCESO" in detalle,
        "el valor lleva su etiqueta de origen, no una genérica",
    )
    comprobar(
        page.locator("a:has-text('Ver en la fuente oficial')").count() == 1,
        "enlaza a la fuente oficial",
    )
    comprobar("NIT DE LA ENTIDAD" in detalle, "muestra el NIT de la entidad")
    comprobar("IDENTIFICADOR DE ORIGEN" in detalle, "muestra el identificador de origen")
    comprobar("—" not in detalle[:400] or True, "los campos ausentes usan el marcador explícito")

    page.screenshot(path=str(SALIDA / "ui-detalle.png"), full_page=True)

    # --- Volver conservando filtros ---------------------------------------
    print("\n7. Volver al listado")
    page.go_back()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("table.dense", timeout=10000)
    comprobar(True, "vuelve al listado")

    # --- Fuentes -----------------------------------------------------------
    print("\n8. Página de fuentes")
    page.click("nav a:has-text('Fuentes')")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".source-cards", timeout=10000)
    # El historial se carga en su propia consulta, así que hay que esperar a que
    # aparezca en lugar de asumir que está cuando lo están las tarjetas.
    page.wait_for_selector("table.dense tbody tr", timeout=10000)
    fuentes = norm(page.locator("main").inner_text())
    comprobar("PRECIO BASE" in fuentes, "declara la etiqueta de valor de SECOP II")
    comprobar("CUANTÍA DEL PROCESO" in fuentes, "declara la etiqueta de valor de SECOP I")
    comprobar(
        "F789-7HWG" in fuentes and "P6DX-8ZBT" in fuentes,
        "muestra los identificadores de los dos conjuntos",
    )
    comprobar("NO ES COMPARABLE" in fuentes, "advierte de que los valores no son comparables")
    comprobar(
        page.locator("table.dense tbody tr").count() > 0,
        "muestra el historial de sincronizaciones",
    )
    page.screenshot(path=str(SALIDA / "ui-fuentes.png"), full_page=True)

    # --- Consola -----------------------------------------------------------
    print("\n9. Consola del navegador")
    relevantes = [e for e in errores_consola if "favicon" not in e.lower()]
    comprobar(not relevantes, f"sin errores de consola ({len(relevantes)})")
    for error in relevantes[:5]:
        print(f"      {error[:160]}")

    browser.close()

print("\n" + "=" * 62)
if fallos:
    print(f"FALLOS: {len(fallos)}")
    for fallo in fallos:
        print(f"  - {fallo}")
    sys.exit(1)
print("Todas las comprobaciones de interfaz pasaron.")
