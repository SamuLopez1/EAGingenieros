import { companyName } from "./brand";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "./api/client";
import { categories, downloadEvidence, fetchProfile, fetchVersions, saveProfile, uploadEvidence } from "./api/profile";
import type { ProfileEntry, Version } from "./api/profile";
import "./design/profile.css";

const blank: ProfileEntry = {
  category: "experiencia", title: "", description: "", service_line: null, role: null,
  dedication_percent: null, amount: null, unit: null, starts_on: null, ends_on: null,
  status: "pendiente", evidence: [],
};
type Snapshot = Awaited<ReturnType<typeof fetchProfile>>;
const formatDate = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" });

function EntryForm({ entry, change, remove, busy, setUploading }: {
  entry: ProfileEntry; change: (entry: ProfileEntry) => void; remove: () => void; busy: boolean; setUploading: (value: boolean) => void;
}) {
  const [file, setFile] = useState<File>();
  const [notice, setNotice] = useState("");
  async function attach() {
    if (!file) return;
    setUploading(true);
    setNotice("");
    try {
      const stored = await uploadEvidence(file);
      if (entry.evidence.some((ref) => ref.document_id === stored.id)) {
        setNotice("El archivo ya está asociado a este registro.");
      } else {
        change({ ...entry, status: "pendiente", evidence: [...entry.evidence, { document_id: stored.id, locator: "" }] });
        setNotice(`Archivo asociado: ${stored.filename}. Indica el localizador.`);
        setFile(undefined);
      }
    } catch (error) {
      setNotice(error instanceof ApiError && error.status === 503
        ? "El análisis antivirus no está disponible. Reintenta la carga."
        : "No fue posible adjuntar la evidencia. Comprueba el tipo y el tamaño.");
    } finally {
      setUploading(false);
    }
  }

  function field(name: "service_line" | "role" | "unit" | "starts_on" | "ends_on" | "amount" | "dedication_percent",
    label: string, type = "text", maxLength = 160) {
    return <label>{label}<input type={type} value={entry[name] ?? ""} maxLength={maxLength}
      step={type === "number" ? (name === "amount" ? "0.0001" : "0.01") : undefined}
      min={name === "dedication_percent" ? 0 : undefined} max={name === "dedication_percent" ? 100 : undefined}
      required={name === "role" && entry.category === "disponibilidad"}
      onChange={(event) => change({ ...entry, [name]: event.target.value || null, status: "pendiente" })} /></label>;
  }

  return <fieldset className="profile-editor" disabled={busy}>
    <legend>{entry.title || "Nuevo registro"}</legend>
    <label>Tipo<select value={entry.category} onChange={(event) => change({
      ...entry, category: event.target.value as ProfileEntry["category"], dedication_percent: null, status: "pendiente",
    })}>{Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Título<input required maxLength={160} value={entry.title}
      onChange={(event) => change({ ...entry, title: event.target.value, status: "pendiente" })} /></label>
    <label>Descripción<textarea maxLength={1500} value={entry.description}
      onChange={(event) => change({ ...entry, description: event.target.value, status: "pendiente" })} /></label>
    {field("service_line", "Línea de servicio")}
    {field("role", "Cargo")}
    {entry.category === "disponibilidad" ? field("dedication_percent", "Dedicación (%)", "number") : null}
    {field("starts_on", "Inicio", "date")}
    {field("ends_on", "Fin", "date")}
    {field("amount", "Valor o cantidad", "number")}
    {field("unit", "Unidad", "text", 32)}
    {entry.evidence.map((ref, index) => (
      <div key={index} className="profile-evidence">
        <label>Localizador de evidencia {index + 1}<input value={ref.locator} required maxLength={240}
          onChange={(event) => change({ ...entry, status: "pendiente", evidence: entry.evidence.map((item, position) =>
            position === index ? { ...item, locator: event.target.value } : item) })} /></label>
        <button type="button" onClick={() => change({ ...entry, status: "pendiente",
          evidence: entry.evidence.filter((_, position) => position !== index) })}>Quitar evidencia {index + 1}</button>
      </div>
    ))}
    {entry.evidence.length < 8 ? <div className="profile-evidence">
      <label>Archivo de evidencia<input type="file" accept=".pdf,.docx,.xlsx"
        onChange={(event) => setFile(event.target.files?.[0])} /></label>
      <button type="button" disabled={!file} onClick={() => void attach()}>Adjuntar archivo</button>
    </div> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <label>Revisión<select value={entry.status} onChange={(event) =>
      change({ ...entry, status: event.target.value as ProfileEntry["status"] })}>
      <option value="pendiente">Pendiente</option>
      <option value="verificado" disabled={!entry.evidence.every((ref) => ref.locator.trim()) || !entry.evidence.length}>
        Verificado por revisión humana
      </option>
    </select></label>
    <button type="button" onClick={remove}>Retirar de la nueva versión</button>
  </fieldset>;
}

export default function CompanyProfile({ editable }: { editable: boolean }) {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [history, setHistory] = useState<Version[]>([]);
  const [selected, setSelected] = useState<number>();
  const [draft, setDraft] = useState<ProfileEntry[]>();
  const [editingIndex, setEditingIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [message, setMessage] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchProfile(undefined, controller.signal), fetchVersions(undefined, controller.signal)])
      .then(([profile, versions]) => { setSnapshot(profile); setHistory(versions); })
      .catch(() => { if (!controller.signal.aborted) setMessage("No se pudo cargar el perfil."); });
    return () => controller.abort();
  }, [refresh]);

  async function select(version?: number) {
    setBusy(true);
    setMessage("");
    try { setSnapshot(await fetchProfile(version)); setSelected(version); }
    catch { setMessage("No se pudo abrir la versión."); }
    finally { setBusy(false); }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!snapshot || !draft || busy || attaching) return;
    setBusy(true);
    setMessage("");
    try {
      const saved = await saveProfile(snapshot.version, draft);
      setSnapshot(saved);
      setDraft(undefined);
      setRefresh((value) => value + 1);
    } catch (error) {
      setMessage(error instanceof ApiError && error.status === 409
        ? "El perfil cambió. Cancela esta edición y vuelve a cargar la versión actual."
        : "No se guardó el perfil. Revisa fechas, valores y evidencias.");
    } finally { setBusy(false); }
  }

  const entry = draft?.[editingIndex];
  const lastVersion = history.at(-1)?.version;
  return <main className="company-profile">
    <h1>Perfil empresarial{companyName === "EAG" ? "" : ' · ' + companyName}</h1>
    {message ? <p role="alert">{message}</p> : null}
    {!snapshot ? <button type="button" onClick={() => setRefresh((value) => value + 1)}>Cargar perfil</button> : (
      <>
        <p>Versión {snapshot.version || "sin registrar"} · Disponibilidad {snapshot.availability_status}</p>
        <fieldset disabled={busy || Boolean(draft)}>
          <legend>Historial</legend>
          <label>Versión <select value={selected ?? ""} onChange={(event) =>
            void select(event.target.value ? Number(event.target.value) : undefined)}>
            <option value="">Actual</option>
            {history.map((version) => <option key={version.version} value={version.version}>
              {version.version} · {formatDate.format(new Date(version.created_at))}
            </option>)}
          </select></label>
          {history.length >= 50 ? <button type="button" onClick={async () => {
            setBusy(true);
            try {
              const older = await fetchVersions(lastVersion);
              setHistory([...history, ...older]);
              if (!older.length) setMessage("Se alcanzó la primera versión.");
            } catch { setMessage("No se pudo cargar más historial."); }
            finally { setBusy(false); }
          }}>Versiones anteriores</button> : null}
          {selected ? <p>Autor: {history.find((version) => version.version === selected)?.author_id}</p> : null}
        </fieldset>
        {draft ? <form className="profile-editor" onSubmit={save}>
          {draft.length ? <label>Registro que se edita<select value={editingIndex} disabled={busy || attaching}
            onChange={(event) => setEditingIndex(Number(event.target.value))}>
            {draft.map((item, index) => <option key={index} value={index}>{item.title || "Registro nuevo"}</option>)}
          </select></label> : null}
          {entry ? <EntryForm key={editingIndex} entry={entry} busy={busy || attaching} setUploading={setAttaching} change={(updated) => {
            setDraft((items) => items?.map((item, index) => index === editingIndex ? updated : item));
          }} remove={() => {
            setDraft(draft.filter((_, index) => index !== editingIndex));
            setEditingIndex(0);
          }} /> : null}
          <div className="profile-actions">
            <button type="button" disabled={busy || attaching || draft.length >= 150} onClick={() => {
              setEditingIndex(draft.length);
              setDraft([...draft, { ...blank }]);
            }}>Añadir registro</button>
            <button type="submit" disabled={busy || attaching}>Guardar nueva versión</button>
            <button type="button" disabled={busy || attaching} onClick={() => { setDraft(undefined); void select(); }}>Cancelar</button>
          </div>
        </form> : (
          <>
            {editable && !selected ? <button type="button" disabled={busy} onClick={() => {
              setEditingIndex(0);
              setDraft(snapshot.entries);
            }}>Editar perfil</button> : null}
            {!snapshot.entries.length ? <p>El perfil todavía no tiene registros.</p> : null}
            <ul className="profile-entries">
              {snapshot.entries.map((item, index) => <li key={index}>
                <h2>{item.title}</h2>
                <p>{categories[item.category]} · {item.status}{item.service_line ? ` · ${item.service_line}` : ""}</p>
                {item.description ? <p>{item.description}</p> : null}
                {item.role ? <p>Cargo: {item.role}</p> : null}
                {item.category === "disponibilidad" ? <p>Dedicación: {
                  item.dedication_percent === null ? "pendiente" : `${item.dedication_percent}%`
                }</p> : null}
                {(item.starts_on || item.ends_on || item.category === "disponibilidad") ? (
                  <p>Periodo: {item.starts_on ?? "pendiente"} a {item.ends_on ?? "pendiente"}</p>
                ) : null}
                {item.amount !== null ? <p>Valor: {item.amount} {item.unit}</p> : null}
                {item.evidence.map((ref, refIndex) => <button key={refIndex} type="button"
                  onClick={() => void downloadEvidence(ref.document_id).catch(() => setMessage("No se pudo descargar la evidencia."))}>
                  Descargar evidencia · {ref.locator}
                </button>)}
              </li>)}
            </ul>
          </>
        )}
      </>
    )}
  </main>;
}
