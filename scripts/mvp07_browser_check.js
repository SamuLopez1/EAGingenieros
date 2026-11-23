// Chrome, FastAPI, Vite y PostgreSQL; identidad y antivirus de fixture.
async (page) => {
  page.setDefaultTimeout(12000);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const details = page.getByRole("region", { name: "Detalle de oportunidad" });
  const folder = page.getByRole("region", { name: "Expediente", exact: true });
  const documentList = folder.getByRole("list", { name: "Documentos del expediente" });
  const withExtraction = new URL(page.url()).searchParams.has("qa_extraction");
  const nativeText = "Texto sintetico verificable de la oportunidad A, version uno.";
  function textPdf() {
    const stream = `BT /F1 12 Tf 20 100 Td (${nativeText}) Tj ET`;
    const objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 250] /Contents 4 0 R " +
        "/Resources << /Font << /F1 5 0 R >> >> >>",
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ];
    let pdf = "%PDF-1.4\n% EAG-QA-A\n";
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

  const pdf = (label) => withExtraction && label === "A" ? textPdf() : Buffer.from(`%PDF-1.4\n% EAG-QA-${label}\n%%EOF\n`);
  await page.getByLabel("Correo", { exact: true }).fill("analista@fixture.invalid");
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
