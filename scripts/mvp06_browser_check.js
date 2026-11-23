// Playwright CLI: run-code --filename scripts/mvp06_browser_check.js
async (page) => {
  page.setDefaultTimeout(12000);
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const catalog = page.getByRole("heading", { name: "Oportunidades", exact: true });
  const results = page.getByRole("region", { name: "Resultados", exact: true });
  const detail = page.getByRole("region", { name: "Detalle de oportunidad" });
  const publicRun = await page.getByRole("note").filter({ hasText: "SECOP público sincronizado" }).count();
  const isList = (response) =>
    new URL(response.url()).pathname === "/api/v1/opportunities" && response.status() === 200;
  const initial = page.waitForResponse(isList);
  await page.getByLabel("Correo", { exact: true }).fill("analista@fixture.invalid");
  await page.getByLabel("Contraseña", { exact: true }).fill("Synthetic-Only-06");
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await catalog.waitFor();
  const initialPage = await (await initial).json();
  await results.getByRole("link").first().waitFor();
  assert(new URL(page.url()).pathname === "/", "El catálogo debe ser la ruta de entrada");

  const apply = async () => {
    const response = page.waitForResponse(isList);
    await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
    return (await response).json();
  };
  const open = async (record, useKeyboard = true) => {
    const link = results.getByRole("link", { name: record.title, exact: true });
    await link.waitFor();
    const response = page.waitForResponse(
      (request) => new URL(request.url()).pathname === `/api/v1/opportunities/${record.id}` &&
        request.status() === 200,
    );
    if (useKeyboard) {
      await link.focus();
      await page.keyboard.press("Enter");
    } else {
      await link.click();
    }
    const actual = await (await response).json();
    await detail.getByRole("heading", { name: record.title, exact: true }).waitFor();
    assert(actual.source_id === record.source_id, "El detalle no conserva el ID sincronizado");
    assert(await detail.getByText("p6dx-8zbt", { exact: true }).isVisible(), "Fuente ausente");
    const official = await detail.getByRole("link", { name: /Ver proceso en SECOP/ }).getAttribute("href");
    assert(official === new URL(actual.official_url).href, "El enlace difiere de la API");
    assert(await detail.getByText("Última carga (hora Colombia)", { exact: true }).isVisible(),
           "No se muestra última sincronización");
    return { actual, official };
  };
  const noOverflow = async () => assert(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "Desbordamiento horizontal de la página",
  );

  if (publicRun) {
    assert(initialPage.total === 2 && initialPage.items.length === 2, "Se esperaban dos filas reales");
    const links = new Set();
    const identifiers = new Set();
    const portal = [];
    for (const [index, record] of initialPage.items.entries()) {
      const date = record.reception_at.slice(0, 10);
      await page.getByLabel("Entidad", { exact: true }).fill(record.entity);
      await page.getByLabel("Ubicación de la entidad", { exact: true }).fill(record.city);
      await page.getByRole("combobox", { name: "Modalidad", exact: true }).selectOption(record.modality);
      await page.getByLabel("Cierre desde (UTC)", { exact: true }).fill(date);
      await page.getByLabel("Cierre hasta (UTC)", { exact: true }).fill(date);
      const filtered = await apply();
      assert(filtered.items.some((row) => row.id === record.id), "El filtro excluyó el proceso");
      const listing = page.url();
      const { actual, official } = await open(record, index === 0);
      assert(new URL(official).hostname === "community.secop.gov.co", "Host oficial inesperado");
      links.add(official);
      identifiers.add(actual.source_id);
      const chain = [];
      const context = page.context();
      const recordResponse = (event) => {
        if (!event.request().isNavigationRequest()) return;
        let request = event.request();
        while (request.redirectedFrom()) request = request.redirectedFrom();
        if (request.url() === official) chain.push(event.status());
      };
      context.on("response", recordResponse);
      const popupReady = page.waitForEvent("popup", { timeout: 10000 }).catch(() => null);
      await detail.getByRole("link", { name: /Ver proceso en SECOP/ }).click();
      const popup = await popupReady;
      await popup?.waitForLoadState("domcontentloaded", { timeout: 10000 }).catch(() => {});
      const final = new URL(popup?.url() ?? "about:blank");
      const origin = final.hostname === "community.secop.gov.co";
      const matched = origin && final.pathname.toLowerCase().includes("/opportunitydetail/") &&
        final.searchParams.get("noticeUID") === new URL(official).searchParams.get("noticeUID");
      const destination = matched ? "ficha" : !final.hostname ? "sinrespuesta"
        : !origin ? "otrohost" : /login|signin|access/i.test(final.pathname) ? "acceso" : "otrosecop";
      portal.push({ first: chain[0] ?? "sinrespuesta", last: chain.at(-1) ?? "sinrespuesta",
                    destination });
      context.off("response", recordResponse);
      await popup?.close();
      if (index === 0) await detail.getByRole("link", { name: /Volver al listado/ }).click();
      else await page.goBack();
      await results.getByRole("link", { name: record.title, exact: true }).waitFor();
      assert(page.url() === listing, "Se modificaron los parámetros al volver");
      assert(await page.getByLabel("Entidad", { exact: true }).inputValue() === record.entity,
             "Se perdió la entidad");
      assert(await page.getByLabel("Ubicación de la entidad").inputValue() === record.city,
             "Se perdió la ubicación");
      assert(await page.getByRole("combobox", { name: "Modalidad", exact: true }).inputValue() === record.modality,
             "Se perdió la modalidad");
      assert(await page.getByLabel("Cierre desde (UTC)").inputValue() === date &&
             await page.getByLabel("Cierre hasta (UTC)").inputValue() === date,
             "Se perdió el rango de cierre");
      if (index === 0) {
        const reset = page.waitForResponse(isList);
        await page.getByRole("button", { name: "Limpiar filtros" }).click();
        await reset;
        await results.getByRole("link").first().waitFor();
      }
    }
    assert(links.size === 2 && identifiers.size === 2, "Se repitió el proceso o el enlace");
    return "QA_BROWSER_OK procesos=2 enlaces=2 regreso=2 filtros=4 " +
      portal.map(({ first, last, destination }, index) =>
        `portal${index + 1}=${first} final${index + 1}=${last} destino${index + 1}=${destination}`).join(" ");
  }

  const cases = [
    { ref: "003", validity: "abierto", label: "Abierto", official: "Publicado" },
    { ref: "000", validity: "cerrado", label: "Cerrado", official: "Adjudicado" },
    { ref: "006", validity: "vencido", label: "Vencido", official: "Publicado" },
    { ref: "009", validity: "desconocida", label: "Vigencia desconocida", official: "Publicado" },
  ];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1080 });
    for (const test of cases) {
      await page.getByLabel("Buscar", { exact: true }).fill(`QA-${test.ref}`);
      await page.getByRole("combobox", { name: "Vigencia", exact: true }).selectOption(test.validity);
      const filtered = await apply();
      assert(filtered.total === 1, "El estado no filtró su fixture");
      await noOverflow();
      const { actual } = await open(filtered.items[0]);
      assert(actual.status === test.official && actual.validity === test.validity,
             "La API confundió estado oficial y vigencia");
      assert(await detail.getByText(test.label, { exact: true }).isVisible(), "Vigencia ausente");
      assert(await detail.getByText(test.official, { exact: true }).isVisible(), "Estado SECOP ausente");
      if (test.validity === "desconocida") {
        assert(actual.reception_at === null, "Se inventó un cierre");
        assert(await detail.getByText(/no aporta información suficiente/).isVisible(),
               "Falta aviso de vigencia desconocida");
      }
      await noOverflow();
      if (test.validity === "abierto") {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: `mvp06-${width}-detalle.png`, fullPage: true });
      }
      await detail.getByRole("link", { name: /Volver al listado/ }).click();
      await results.getByRole("link").first().waitFor();
      assert(await page.getByRole("combobox", { name: "Vigencia", exact: true }).inputValue() === test.validity,
             "Se perdió el filtro de vigencia");
      if (test.validity === "abierto") {
        const closing = results.locator('td[data-label="Cierre (UTC)"]');
        assert(await closing.count() === 1, "Falta la etiqueta de cierre en el listado");
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: `mvp06-${width}-catalogo.png`, fullPage: true });
      }
    }
  }
  return "QA_BROWSER_OK estados=4 tamanos=2 capturas=4";
}
