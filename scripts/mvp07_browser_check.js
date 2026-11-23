// Chrome, FastAPI, Vite y PostgreSQL; identidad y antivirus de fixture.
async (page) => {
  page.setDefaultTimeout(12000);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const details = page.getByRole("region", { name: "Detalle de oportunidad" });
  const folder = page.getByRole("region", { name: "Expediente", exact: true });
  const documentList = folder.getByRole("list", { name: "Documentos del expediente" });
  const withComparison = new URL(page.url()).searchParams.has("qa_comparison");
  const withReport = new URL(page.url()).searchParams.has("qa_report");
  const withStaffing = new URL(page.url()).searchParams.has("qa_staffing");
  const withMargin = new URL(page.url()).searchParams.has("qa_margin");
  const withShortlist = new URL(page.url()).searchParams.has("qa_shortlist");
  const withExtraction = new URL(page.url()).searchParams.has("qa_extraction");
  const nativeText = "Texto sintetico verificable de la oportunidad A, version uno.";
  function textPdf(label, content = nativeText) {
    const lines = content.split("\n").map((line) => `(${line}) Tj T*`).join(" ");
    const stream = `BT /F1 12 Tf 20 220 Td 15 TL ${lines} ET`;
    const objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 250] /Contents 4 0 R " +
        "/Resources << /Font << /F1 5 0 R >> >> >>",
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ];
    let pdf = `%PDF-1.4\n% EAG-QA-${label}\n`;
    const offsets = [];
    for (const [index, object] of objects.entries()) {
      offsets.push(pdf.length);
      pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
    }
    const xref = pdf.length;
    pdf += "xref\n0 6\n0000000000 65535 f \n";
    for (const offset of offsets) pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
    return Buffer.from(pdf + `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  }

  const clauses = {
    A: "Habilitante: Experiencia vial: minimo 1 ano.",
    B: "Habilitante: Experiencia hidrica: minimo 12 meses.",
  };
  const staffingLines = {
    A: [
      "Objeto: Linea de servicio: Consultoria vial.",
      "Habilitante: Cargo: Residente; dedicacion: 60%; periodo: 2026-12-01 a 2026-12-20.",
      "Obligacion: Cargo: Residente; dedicacion: 50%; periodo: 2026-12-11 a 2026-12-30.",
    ],
    B: ["Obligacion: Cargo: Topografo; dedicacion: 30%; periodo: 2026-12-01 a 2026-12-15."],
  };
  const pdf = (label) => withComparison && clauses[label]
    ? textPdf(label, [clauses[label], ...(withStaffing ? staffingLines[label] : [])].join("\n"))
    : withExtraction && label === "A"
      ? textPdf(label)
      : Buffer.from(`%PDF-1.4\n% EAG-QA-${label}\n%%EOF\n`);
  await page.getByLabel("Correo", { exact: true }).fill(
    withComparison ? "admin@fixture.invalid" : "analista@fixture.invalid",
  );
  await page.getByLabel("Contraseña", { exact: true }).fill("Synthetic-Only-06");
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await page.getByRole("heading", { name: "Oportunidades", exact: true }).waitFor();

  async function open(reference, saveInCatalog = false) {
    await page.getByLabel("Buscar", { exact: true }).fill(`QA-${reference}`);
    await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
    const catalog = page.getByRole("region", { name: "Resultados del catálogo" });
    const matching = { name: new RegExp(`caso sintético ${reference}$`) };
    const card = catalog.getByRole("link", matching);
    if (saveInCatalog) {
      const row = catalog.getByRole("row").filter({ has: page.getByRole("link", matching) });
      await row.getByRole("button", { name: "Guardar en lista corta" }).click();
      await row.getByRole("button", { name: "Quitar de la lista corta", exact: true }).waitFor();
    }
    await card.click();
    await folder.getByRole("button", { name: "Cargar archivo", exact: true }).waitFor();
    return Number(new URL(page.url()).searchParams.get("opportunity"));
  }
  async function add(label, kind) {
    await folder.getByRole("combobox", { name: "Tipo", exact: true }).selectOption(kind);
    await folder.getByLabel("Nombre del documento", { exact: true }).fill(`Documento QA ${label}`);
    await folder.getByLabel("Archivo (PDF, DOCX o XLSX)", { exact: true }).setInputFiles({
      name: `expediente-${label}.pdf`, mimeType: "application/pdf", buffer: pdf(label),
    });
    const done = page.waitForResponse((res) =>
      res.request().method() === "POST" && new URL(res.url()).pathname.endsWith("/documents"),
    );
    await folder.getByRole("button", { name: "Cargar archivo", exact: true }).click();
    const response = await done;
    assert(response.status() === 201, "La carga manual no fue aceptada");
    await documentList.getByText(new RegExp(`Documento QA ${label}$`)).waitFor();
    return response.json();
  }
  async function back() {
    await details.getByRole("link", { name: /Volver al listado/ }).click();
    await page.getByLabel("Buscar", { exact: true }).waitFor();
  }

  async function extraction(status, enqueue) {
    const panel = documentList.locator(".document-extraction");
    await panel.getByText("Extracción de texto · versión 1", { exact: true }).click();
    if (enqueue) await panel.getByRole("button", { name: "Extraer texto", exact: true }).click();
    await panel.getByRole("status").filter({ hasText: status }).waitFor();
    return panel;
  }

  if (withComparison) {
    const matrix = folder.getByRole("region", { name: "Comparación con EAG" });
    async function matrixFor(reference, label, expected) {
      const opportunityId = await open(reference, withShortlist && label === "B");
      const document = await add(label, "pliego");
      await documentList.getByRole("button", { name: "Marcar en revisión" }).click();
      await documentList.getByText("Disponible · En revisión").waitFor();
      const panel = await extraction("Extracción disponible", true);
      await panel.getByText(clauses[label], { exact: !withStaffing }).waitFor();
      await matrix.getByRole("button", { name: "Comparar con EAG" }).click();
      await matrix.getByText(expected, { exact: true }).waitFor();
      const row = matrix.getByRole("list", { name: "Matriz de requisitos" }).locator(":scope > li")
        .filter({ has: page.getByText(clauses[label], { exact: true }) });
      await row.getByText(clauses[label], { exact: true }).waitFor();
      for (const [name, filter] of [
        ["Abrir evidencia del expediente", `/${document.id}/content`],
        ["Abrir evidencia EAG · Página 1", "/company-profile/evidence/"],
      ]) {
        const download = page.waitForEvent("download");
        const fetched = page.waitForResponse((res) => res.url().includes(filter) && res.status() === 200);
        await row.getByRole("button", { name, exact: true }).click();
        await fetched;
        await (await download).delete();
      }
      return opportunityId;
    }
    async function approve() {
      await matrix.getByLabel("Justificación de aprobación").fill("Revisión de fixture sintética");
      await matrix.getByRole("button", { name: "Aprobar comparación" }).click();
      await matrix.getByRole("status").filter({ hasText: "Comparación aprobada" }).waitFor();
    }
    async function marginPanel() {
      const panel = folder.locator("details").filter({
        has: page.getByText("Escenarios de utilidad y margen", { exact: true }),
      });
      await panel.getByText("Escenarios de utilidad y margen", { exact: true }).click();
      await panel.getByText(/Presupuesto publicado, solo como referencia/).waitFor();
      return panel;
    }
    async function checkMargins() {
      const panel = await marginPanel();
      await panel.getByText(/Presupuesto publicado, solo como referencia: 800.00/).waitFor();
      await panel.getByText("Brechas de personal para presupuestar").click();
      await panel.getByText(/Residente · 30 % · 2026-12-11/).waitFor();
      const form = panel.locator("form").filter({ has: page.getByRole("button", { name: "Guardar escenario" }) });
      async function assumption(label, amount) {
        const group = form.getByRole("group", { name: label, exact: true });
        if (amount !== null) await group.getByLabel("Importe").fill(amount);
        await group.getByLabel("Fuente o supuesto").fill("Fixture sintética autorizada");
      }
      async function costs(hiring) {
        await assumption("Costos directos", "30");
        await assumption("Costos indirectos", "5");
        await assumption("Personal interno", "20");
        await assumption("Contratación adicional", hiring);
        await assumption("Contingencia", "5");
      }
      function card(name) {
        return panel.getByRole("list", { name: "Escenarios de margen" }).locator(":scope > li")
          .filter({ has: page.getByRole("heading", { name, exact: true }) });
      }
      await panel.getByRole("button", { name: "Nuevo escenario" }).click();
      await form.getByLabel("Nombre", { exact: true }).fill("Base QA");
      const income = form.getByRole("group", { name: "Ingreso estimado", exact: true }).getByLabel("Importe");
      assert(await income.inputValue() === "", "El presupuesto se aplicó sin autorización");
      await assumption("Ingreso estimado", "100");
      await costs(null);
      await form.getByRole("button", { name: "Guardar escenario" }).click();
      await card("Base QA").getByText("Importes pendientes: Contratación adicional.").waitFor();
      await card("Base QA").getByRole("button", { name: "Editar escenario" }).click();
      await assumption("Contratación adicional", "10");
      await form.getByRole("button", { name: "Guardar escenario" }).click();
      await card("Base QA").getByText("30,00 %", { exact: true }).waitFor();

      await panel.getByRole("button", { name: "Nuevo escenario" }).click();
      await form.getByLabel("Nombre", { exact: true }).fill("Adverso QA");
      await form.getByLabel("Base del ingreso").selectOption("publicado");
      await form.getByLabel("Justificación y moneda del presupuesto").fill("Referencia sintética en COP.");
      await costs("900");
      await form.getByRole("button", { name: "Guardar escenario" }).click();
      await card("Adverso QA").getByText("-20,00 %", { exact: true }).waitFor();
      await card("Adverso QA").getByLabel("Nota de revisión").fill("Revisión sintética de Finanzas.");
      await card("Adverso QA").getByRole("button", { name: "Registrar revisión" }).click();
      await card("Adverso QA").getByText(/Versión 2 · Revisado/).waitFor();
      await card("Adverso QA").getByRole("button", { name: "Ver historial" }).click();
      await card("Adverso QA").getByText("Revisión sintética de Finanzas.", { exact: true }).waitFor();
    }
    const a = await matrixFor("003", "A", "Habilitante · Cumple");
    if (withStaffing) {
      const staff = matrix.getByRole("region", { name: "Encaje y personal" });
      await staff.getByText("Consultoria vial · Con respaldo", { exact: true }).waitFor();
      const overlap = staff.getByRole("listitem").filter({
        has: page.getByText("2026-12-11 a 2026-12-20 · Capacidad insuficiente", { exact: true }),
      });
      await overlap.getByText("Exigencias citadas del periodo", { exact: true }).click();
      await overlap.getByText(staffingLines.A[1], { exact: true }).waitFor();
      await overlap.getByText(staffingLines.A[2], { exact: true }).waitFor();
      await staff.getByText(/Evaluar contratación o reasignación de Residente al 30/).waitFor();
      await staff.getByText("Brechas habilitantes", { exact: true }).waitFor();
    }
    await matrix.getByRole("list", { name: "Matriz de requisitos" }).locator(":scope > li")
      .filter({ has: page.getByText(clauses.A, { exact: true }) })
      .getByRole("button", { name: "Corregir requisito" }).click();
    await matrix.getByLabel("Resultado").selectOption("cumple_parcialmente");
    await matrix.getByLabel("Evidencia verificada").selectOption({ label: "Experiencia vial" });
    await matrix.getByLabel("Justificación", { exact: true }).fill("Corrección con respaldo sintético");
    await matrix.getByRole("button", { name: "Guardar corrección" }).click();
    await matrix.getByText("Habilitante · Cumple parcialmente", { exact: true }).waitFor();
    await approve();
    if (withReport) {
      const report = matrix.locator("#informe-aprobado");
      await report.getByRole("heading", { name: /Informe aprobado/ }).waitFor();
      const pdfPreview = page.waitForResponse((res) => res.url().includes("/reports/") &&
        res.request().method() === "GET" && res.headers()["content-type"] === "application/pdf");
      await report.getByRole("button", { name: "Vista previa del PDF" }).click();
      const preview = await pdfPreview;
      assert(preview.headers()["cache-control"] === "private, no-store", "PDF sin política privada");
      await report.locator("iframe").waitFor();
      await report.getByRole("button", { name: "Cerrar vista previa" }).click();
      const saved = page.waitForEvent("download");
      await report.getByRole("button", { name: "Descargar PDF privado" }).click();
      const file = await saved;
      assert(file.suggestedFilename().endsWith(".pdf"), "El archivo descargado no es el informe");
      await file.delete();

      await report.getByLabel("Destinatario autorizado").selectOption("revisor@fixture.invalid");
      await report.getByRole("button", { name: "Enviar enlace privado" }).click();
      await report.getByRole("button", { name: "Comprobar o reintentar envío" }).click();
      await report.getByText("Auditoría de correo", { exact: true }).click();
      await report.getByText("2 intentos", { exact: true }).waitFor();
      await report.getByText(/revisor@fixture.invalid · Aceptado por el proveedor/).waitFor();
      assert(await report.getByRole("button", { name: "Comprobar o reintentar envío" }).isDisabled(),
        "El envío aceptado continuó habilitado");
    }
    if (withMargin) await checkMargins();
    if (withShortlist) {
      await details.getByRole("button", { name: "Guardar en lista corta", exact: true }).click();
      await details.getByRole("button", { name: "Quitar de la lista corta", exact: true }).waitFor();
    }
    await back();
    const b = await matrixFor("006", "B", "Habilitante · No cumple");
    assert(a !== b, "El recorrido reabrió la ficha de A");
    if (withMargin) {
      const panel = await marginPanel();
      assert(await panel.getByRole("list", { name: "Escenarios de margen" }).count() === 0,
        "Se filtraron los escenarios de otra ficha");
    }
    if (withStaffing) {
      const staff = matrix.getByRole("region", { name: "Encaje y personal" });
      await staff.getByText("2026-12-01 a 2026-12-15 · Disponibilidad por confirmar", { exact: true }).waitFor();
      await staff.getByText("Confirmar disponibilidad con Talento Humano para este periodo.", { exact: true }).waitFor();
    }
    await approve();
    await add("Adenda-B", "adenda");
    await matrix.getByRole("status").filter({ hasText: "La aprobación anterior no está vigente" }).waitFor();
    if (withReport) {
      assert(await matrix.locator("#informe-aprobado").count() === 0, "Informe visible tras invalidar");
    }
    await back();
    assert(await open("003") === a, "El retorno abrió una ficha incorrecta");
    await matrix.getByRole("status").filter({ hasText: "Comparación aprobada" }).waitFor();
    await matrix.getByText("Habilitante · Cumple parcialmente", { exact: true }).waitFor();
    await matrix.getByText("Historial de revisión", { exact: true }).click();
    await matrix.getByText("Corrección con respaldo sintético", { exact: true }).waitFor();
    if (withShortlist) {
      const shortlist = page.getByRole("region", { name: "Lista corta", exact: true });
      const table = shortlist.getByRole("table", { name: "Comparación de oportunidades guardadas" });
      async function checkTwo() {
        await table.getByRole("columnheader", { name: /caso sintético 003/ }).waitFor();
        await table.getByRole("columnheader", { name: /caso sintético 006/ }).waitFor();
        assert(await table.getByRole("columnheader").count() === 3, "Se esperaban dos columnas de datos");
      }
      await shortlist.getByRole("button", { name: "Comparar lista corta" }).click();
      await checkTwo();
      await table.getByText("Margen 30,00 %", { exact: true }).waitFor();
      await table.getByText("Margen -20,00 %", { exact: true }).waitFor();
      await table.getByText("Matriz desactualizada. Recalcula en la ficha.", { exact: true }).waitFor();
      await table.getByText(/Brecha del 30 % · 2026-12-11/).waitFor();
      await back();
      await open("009", true);
      await table.getByRole("columnheader", { name: /caso sintético 009/ }).waitFor();
      assert(await table.getByRole("columnheader").count() === 4, "Se esperaban tres columnas de datos");
      await back();
      await open("012");
      const fourth = details.getByRole("button", { name: "Guardar en lista corta", exact: true });
      await fourth.waitFor();
      assert(await fourth.isDisabled(), "La interfaz permitió una cuarta ficha");
      await shortlist.getByRole("button", { name: /Quitar .*009.*lista corta/ }).click();
      await shortlist.getByText("2 oportunidades guardadas.", { exact: true }).waitFor();
      await page.reload();
      await shortlist.getByText("2 oportunidades guardadas.", { exact: true }).waitFor();
      await shortlist.getByRole("button", { name: "Comparar lista corta" }).click();
      await checkTwo();
    }
    return "QA_BROWSER_OK oportunidades=2 comparaciones=2 descargas=4 correcciones=1 aprobaciones=2 invalidaciones=1" +
      (withStaffing ? " encaje=1 brecha=1 pendiente=1" : "") +
      (withMargin ? " escenarios=2 revisiones=1" : "") +
      (withReport ? " informes=1 correosimulado=1 reintento=1" : "") +
      (withShortlist ? " lista=1 columnas=3 recarga=1" : "");
  }

  const opportunityA = await open("003");
  assert(await folder.getByText(/Sin descarga oficial validada/).isVisible(), "Falta el respaldo manual");
  const a = await add("A", "pliego");
  if (withExtraction) {
    const panel = await extraction("Extracción disponible", true);
    await panel.getByText("Página 1", { exact: true }).waitFor();
    await panel.getByText(nativeText, { exact: true }).waitFor();
  }
  await back();
  const opportunityB = await open("006");
  assert(await folder.getByText("El expediente está vacío.").isVisible(), "B recibió documentos de A");
  const b = await add("B", "adenda");
  if (withExtraction) {
    const panel = await extraction("La extracción falló", true);
    await panel.getByText("No fue posible leer el formato o su contenido.").waitFor();
    await panel.getByRole("button", { name: "Reintentar extracción", exact: true }).waitFor();
    assert(await panel.getByText(nativeText).count() === 0, "La extracción de A apareció en B");
  }
  assert(a.opportunity_id === opportunityA && b.opportunity_id === opportunityB &&
         opportunityA !== opportunityB && a.id !== b.id, "Las cargas no quedaron aisladas");
  await back();
  assert(await open("003") === opportunityA, "El retorno abrió otra oportunidad");
  await documentList.getByText(/Documento QA A$/).waitFor();
  assert(await documentList.getByRole("listitem").count() === 1 &&
         await documentList.getByText(/Documento QA B$/).count() === 0,
         "El expediente A contiene documentos de B");

  if (withExtraction) {
    const panel = await extraction("Extracción disponible", false);
    await panel.getByText(nativeText, { exact: true }).waitFor();
  }

  const download = page.waitForResponse((res) =>
    res.request().method() === "GET" && res.url().endsWith(`/${a.id}/content`),
  );
  const saved = page.waitForEvent("download");
  await documentList.getByRole("button", { name: "Descargar archivo", exact: true }).click();
  const response = await download;
  if (response.status() !== 200) throw new Error(`Descarga privada HTTP ${response.status()}`);
  const file = await saved;
  try {
    assert(file.suggestedFilename() === "expediente-A.pdf", "El nombre descargado no es de A");
    const chunks = [];
    for await (const chunk of await file.createReadStream()) chunks.push(chunk);
    const actual = Buffer.concat(chunks);
    const expected = pdf("A");
    assert(actual.equals(expected),
           `Bytes distintos al descargar A (${actual.length}/${expected.length}; ${response.headers()["content-length"]})`);
  } finally {
    await file.delete();
  }
  return "QA_BROWSER_OK oportunidades=2 archivos=2 regreso=1 descarga=1" +
    (withExtraction ? " extraccion=1 fallo=1" : "");
}
