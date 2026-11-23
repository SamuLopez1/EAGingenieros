// Chrome, FastAPI, Vite y PostgreSQL; identidad y antivirus de fixture.
async (page) => {
  page.setDefaultTimeout(12000);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const details = page.getByRole("region", { name: "Detalle de oportunidad" });
  const folder = page.getByRole("region", { name: "Expediente", exact: true });
  const documentList = folder.getByRole("list", { name: "Documentos del expediente" });
  const withComparison = new URL(page.url()).searchParams.has("qa_comparison");
  const withReport = new URL(page.url()).searchParams.has("qa_report");
  const withExtraction = new URL(page.url()).searchParams.has("qa_extraction");
  const nativeText = "Texto sintetico verificable de la oportunidad A, version uno.";
  function textPdf(label, content = nativeText) {
    const stream = `BT /F1 12 Tf 20 100 Td (${content}) Tj ET`;
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
  const pdf = (label) => withComparison && clauses[label]
    ? textPdf(label, clauses[label])
    : withExtraction && label === "A"
      ? textPdf(label)
      : Buffer.from(`%PDF-1.4\n% EAG-QA-${label}\n%%EOF\n`);
  await page.getByLabel("Correo", { exact: true }).fill(
    withComparison ? "admin@fixture.invalid" : "analista@fixture.invalid",
  );
  await page.getByLabel("Contraseña", { exact: true }).fill("Synthetic-Only-06");
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await page.getByRole("heading", { name: "Oportunidades", exact: true }).waitFor();

  async function open(reference) {
    await page.getByLabel("Buscar", { exact: true }).fill(`QA-${reference}`);
    await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
    const card = page.getByRole("link", { name: new RegExp(`caso sintético ${reference}$`) });
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
      const opportunityId = await open(reference);
      const document = await add(label, "pliego");
      await documentList.getByRole("button", { name: "Marcar en revisión" }).click();
      await documentList.getByText("Disponible · En revisión").waitFor();
      const panel = await extraction("Extracción disponible", true);
      await panel.getByText(clauses[label], { exact: true }).waitFor();
      await matrix.getByRole("button", { name: "Comparar con EAG" }).click();
      await matrix.getByText(expected, { exact: true }).waitFor();
      await matrix.getByText(clauses[label], { exact: true }).waitFor();
      for (const [name, filter] of [
        ["Abrir evidencia del expediente", `/${document.id}/content`],
        ["Abrir evidencia EAG · Página 1", "/company-profile/evidence/"],
      ]) {
        const download = page.waitForEvent("download");
        const fetched = page.waitForResponse((res) => res.url().includes(filter) && res.status() === 200);
        await matrix.getByRole("button", { name, exact: true }).click();
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
    const a = await matrixFor("003", "A", "Habilitante · Cumple");
    await matrix.getByRole("button", { name: "Corregir requisito" }).click();
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
    await back();
    const b = await matrixFor("006", "B", "Habilitante · No cumple");
    assert(a !== b, "El recorrido reabrió la ficha de A");
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
    return "QA_BROWSER_OK oportunidades=2 comparaciones=2 descargas=4 correcciones=1 aprobaciones=2 invalidaciones=1" +
      (withReport ? " informes=1 correosimulado=1 reintento=1" : "");
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
