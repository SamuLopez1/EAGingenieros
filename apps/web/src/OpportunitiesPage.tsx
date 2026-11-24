import { companyName, simulatedMailbox } from "./brand";
import { DossierSection } from "./DossierSection";
import { ShortlistPanel, ShortlistToggle } from "./ShortlistPanel";
import { useShortlist } from "./useShortlist";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  deleteFilter,
  fetchFilterOptions,
  fetchOpportunities,
  fetchOpportunity,
  fetchSavedFilters,
  saveFilter,
  triggerSync,
} from "./api/client";
import type { FilterCriteria, Opportunity, OpportunityPage, SavedFilter } from "./api/contracts";
import { OpportunityTable } from "./design/OpportunityTable";
import { formatDate, formatColombiaDateTime, formatDateTime, officialSecopUrl } from "./design/format";
import { validityLabels } from "./design/validity";
import { CatalogFreshness } from "./design/CatalogFreshness";
import "./design/tokens.css";
import "./design/app.css";

const sorts = {
  published_desc: "Publicación: más reciente",
  published_asc: "Publicación: más antigua",
  entity_asc: "Entidad: A–Z",
  title_asc: "Título: A–Z",
  synced_desc: "Última carga: más reciente",
} as const;
const fields = [
  "q", "entity", "location", "status", "validity", "modality",
  "closing_from", "closing_to", "published_from", "published_to", "sort",
] as const;
function criteriaFromUrl(params: URLSearchParams): FilterCriteria {
  const sort = params.get("sort") ?? "published_desc";
  const validity = params.get("validity");
  return {
    q: params.get("q") ?? "",
    entity: params.get("entity") ?? "",
    location: params.get("location") ?? "",
    validity: validity && Object.hasOwn(validityLabels, validity)
      ? (validity as FilterCriteria["validity"]) : null,
    closing_from: params.get("closing_from") || null,
    closing_to: params.get("closing_to") || null,
    status: params.get("status") ?? "",
    modality: params.get("modality") ?? "",
    published_from: params.get("published_from") || null,
    published_to: params.get("published_to") || null,
    sort: Object.hasOwn(sorts, sort) ? (sort as FilterCriteria["sort"]) : "published_desc",
  };
}
type Load = { key: string; page?: OpportunityPage; error?: string };
function message(error: unknown): string {
  if (error instanceof ApiError) {
    if ([401, 403].includes(error.status))
      return "La sesión no permite esta operación. Vuelve a iniciar sesión.";
    if (error.status === 422)
      return "Revisa los filtros: el rango de fechas o los parámetros no son válidos.";
    if (error.status === 409) return "Ya existe un filtro compartido con ese nombre.";
  }
  return "No fue posible completar la consulta. Comprueba la conexión y vuelve a intentarlo.";
}
export default function OpportunitiesPage({ role }: { role: "administrador" | "analista" }) {
  const shortlist = useShortlist();
  const [url, setUrl] = useState(() => window.location.search);
  const [revision, setRevision] = useState(0);
  const [load, setLoad] = useState<Load>({ key: "" });
  const lastGood = useRef<Load>({ key: "" });
  const [detail, setDetail] = useState<{ id: string; item?: Opportunity; error?: string }>({
    id: "",
  });
  const heading = useRef<HTMLHeadingElement>(null);
  const returnFocus = useRef<number | null>(null);
  const [options, setOptions] = useState({ statuses: [] as string[], modalities: [] as string[] });
  const [optionError, setOptionError] = useState(false);
  const [optionRevision, setOptionRevision] = useState(0);
  const [saved, setSaved] = useState<SavedFilter[]>([]);
  const [savedRevision, setSavedRevision] = useState(0);
  const [savedError, setSavedError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const params = new URLSearchParams(url);
  const criteria = criteriaFromUrl(params);
  const pageNumber = Math.max(1, Math.min(10000, Math.floor(Number(params.get("page")) || 1)));
  const limit = [10, 25, 50, 100].includes(Number(params.get("limit")))
    ? Number(params.get("limit"))
    : 25;
  const offset = (pageNumber - 1) * limit;
  const selectedId = params.get("opportunity") ?? "";
  const selectedFilter = saved.find((item) => String(item.id) === params.get("saved"));
  const requestKey = JSON.stringify({ ...criteria, limit, offset });
  const key = `${requestKey}:${revision}`;
  function navigate(next: URLSearchParams) {
    window.history.pushState(null, "", `${window.location.pathname}${next.size ? `?${next}` : ""}`);
    setUrl(window.location.search);
  }
  useEffect(() => {
    const pop = () => setUrl(window.location.search);
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    if (!simulatedMailbox || selectedId || busy) return;
    const refresh = window.setInterval(() => {
      if (document.visibilityState === "visible") setRevision((value) => value + 1);
    }, 20_000);
    return () => window.clearInterval(refresh);
  }, [selectedId, busy]);
  useEffect(() => {
    const controller = new AbortController();
    fetchOpportunities(JSON.parse(requestKey), controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        lastGood.current = { key: requestKey, page };
        setLoad({ key, page });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setLoad({
            key,
            error: message(error),
            page: lastGood.current.key === requestKey ? lastGood.current.page : undefined,
          });
      });
    return () => controller.abort();
  }, [key, requestKey]);
  useEffect(() => {
    const controller = new AbortController();
    fetchFilterOptions(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setOptions(value);
          setOptionError(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptionError(true);
      });
    return () => controller.abort();
  }, [optionRevision]);
  useEffect(() => {
    const controller = new AbortController();
    fetchSavedFilters(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setSaved(items);
          setSavedError("");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setSavedError(
            "No fue posible cargar los filtros compartidos. Puedes usar los controles de búsqueda.",
          );
      });
    return () => controller.abort();
  }, [savedRevision]);
  useEffect(() => {
    const controller = new AbortController();
    if (selectedId)
      fetchOpportunity(Number(selectedId), controller.signal)
        .then((item) => {
          if (!controller.signal.aborted) setDetail({ id: selectedId, item });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setDetail({
              id: selectedId,
              error:
                error instanceof ApiError && error.status === 404
                  ? "La oportunidad no existe."
                  : message(error),
            });
        });
    return () => controller.abort();
  }, [selectedId]);
  useEffect(() => {
    if (selectedId && detail.id === selectedId) heading.current?.focus();
    if (!selectedId && returnFocus.current)
      document.getElementById(`opportunity-${returnFocus.current}`)?.focus();
  }, [selectedId, detail]);
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const field of [...fields, "limit"]) {
      const value = String(form.get(field) ?? "").trim();
      if (value) next.set(field, value);
    }
    if (params.get("saved")) next.set("saved", params.get("saved")!);
    navigate(next);
  }
  function detailUrl(id: number) {
    const next = new URLSearchParams(url);
    next.set("opportunity", String(id));
    return `?${next}`;
  }
  function openDetail(id: number) {
    returnFocus.current = id;
    const next = new URLSearchParams(url);
    next.set("opportunity", String(id));
    navigate(next);
  }
  async function persist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const action = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value");
    setBusy(true);
    setNotice("");
    try {
      const result = await saveFilter(
        String(form.get("name") ?? "").trim(),
        criteria,
        action === "update" ? selectedFilter?.id : undefined,
      );
      setNotice(`Filtro «${result.name}» guardado para ${companyName}.`);
      setSavedRevision((value) => value + 1);
      const next = new URLSearchParams(url);
      next.set("saved", String(result.id));
      navigate(next);
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  }
  async function removeSaved() {
    if (!selectedFilter) return;
    setBusy(true);
    try {
      await deleteFilter(selectedFilter.id);
      setSavedRevision((value) => value + 1);
      const next = new URLSearchParams(url);
      next.delete("saved");
      navigate(next);
      setNotice("Filtro compartido eliminado.");
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  }
  async function sync() {
    setBusy(true);
    setNotice("Sincronizando…");
    try {
      const result = await triggerSync(simulatedMailbox ? {} : { limit: 50 });
      const counts = `${result.records_created} nuevas, ${result.records_updated} actualizadas, ${result.records_unchanged} sin cambios.`;
      setNotice(
        result.outcome === "completed"
          ? `Carga terminada: ${counts}`
          : `La sincronización falló. La copia puede estar desactualizada; se conserva el avance disponible: ${counts}`,
      );
      setRevision((value) => value + 1);
      setOptionRevision((value) => value + 1);
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  }
  const current = load.key === key ? load : null;
  const page = current?.page;
  const item = detail.id === selectedId ? detail.item : undefined;
  const officialUrl = officialSecopUrl(item?.official_url);
  return (
    <>
      <header className="top">
        <div className="wrap top-in">
          <div className="brand">
            <span className="mark" aria-hidden="true" />
            {companyName} · Licitaciones
          </div>
          <span className="env env-db">Catálogo SECOP II</span>
        </div>
      </header>
      <main className="wrap">
        <section className="head">
          <div>
            <h1>Oportunidades</h1>
            <p className="lead">
              Consulta los procesos incorporados desde SECOP II. La decisión de participar requiere
              revisión humana.
            </p>
            {simulatedMailbox ? <p>
              Este catálogo incorpora procesos publicados con recepción futura.
              {" "}<a href="https://www.datos.gov.co/d/p6dx-8zbt" target="_blank"
                rel="noreferrer">Consultar el histórico completo de SECOP II</a>
            </p> : null}
          </div>
          {role === "administrador" ? (
            <button className="btn btn-s" disabled={busy} onClick={() => void sync()}>
              Sincronizar ahora
            </button>
          ) : null}
        </section>
        {notice ? (
          <p className="banner banner-warn" role="status">
            {notice}
          </p>
        ) : null}
        <ShortlistPanel selection={shortlist} viewKey={selectedId} detailHref={detailUrl} onOpen={openDetail} />
        {selectedId ? (
          <section className="panel opportunity-detail" aria-label="Detalle de oportunidad">
            <a
              className="btn btn-s"
              href={`?${new URLSearchParams([...params].filter(([name]) => name !== "opportunity"))}`}
              onClick={(event) => {
                event.preventDefault();
                const next = new URLSearchParams(url);
                next.delete("opportunity");
                navigate(next);
              }}
            >
              ← Volver al listado
            </a>
            <h2 tabIndex={-1} ref={heading}>
              {item?.title || "Detalle de oportunidad"}
            </h2>
            {detail.id !== selectedId ? <p role="status">Cargando detalle…</p> : null}
            {detail.id === selectedId && detail.error ? <p role="alert">{detail.error}</p> : null}
            {item ? (
              <>
                <p>{item.entity || "Entidad no informada"}</p>
                <dl>
                  <div>
                    <dt>Identificador SECOP</dt>
                    <dd>{item.source_id}</dd>
                  </div>
                  <div>
                    <dt>Fuente</dt>
                    <dd>{item.source_dataset}</dd>
                  </div>
                  <div>
                    <dt>Referencia</dt>
                    <dd>{item.reference || "No informada"}</dd>
                  </div>
                  <div>
                    <dt>Estado SECOP</dt>
                    <dd>{item.status || "No informado"}</dd>
                  </div>
                  <div>
                    <dt>Vigencia según catálogo</dt>
                    <dd>{validityLabels[item.validity]}</dd>
                  </div>
                  <div>
                    <dt>Fase SECOP</dt>
                    <dd>{item.phase || "No informada"}</dd>
                  </div>
                  <div>
                    <dt>Ubicación de la entidad</dt>
                    <dd>{[item.city, item.department].filter(Boolean).join(", ") || "No informada"}</dd>
                  </div>
                  <div>
                    <dt>Fecha de cierre (UTC)</dt>
                    <dd>{item.reception_at ? formatDateTime(item.reception_at) : "No informada"}</dd>
                  </div>
                  <div>
                    <dt>Modalidad</dt>
                    <dd>{item.modality || "No informada"}</dd>
                  </div>
                  <div>
                    <dt>Publicación (UTC)</dt>
                    <dd>{formatDate(item.published_at)}</dd>
                  </div>
                  <div>
                    <dt>Última carga (hora Colombia)</dt>
                    <dd>{formatColombiaDateTime(item.last_synced_at)}</dd>
                  </div>
                </dl>
                <p className="detail-source-note">
                  {item.validity === "desconocida"
                    ? "La fuente no aporta información suficiente para confirmar la vigencia."
                    : "La vigencia se estima con los datos sincronizados."}{" "}
                  Comprueba el plazo y la disponibilidad en el proceso oficial.
                </p>
                {officialUrl ? (
                  <a href={officialUrl} target="_blank" rel="noopener noreferrer">
                    Ver proceso en SECOP ↗
                  </a>
                ) : (
                  <p>La fuente no informó un enlace oficial válido.</p>
                )}
                <ShortlistToggle selection={shortlist} id={item.id} />
                <DossierSection key={item.id} opportunityId={item.id} role={role} />
              </>
            ) : null}
          </section>
        ) : (
          <>
            <section className="panel filters" aria-label="Filtros de oportunidades">
              <div className="filter-intro">
                <h2>Explorar catálogo</h2>
                <p>Fechas en UTC. El rango de cierre incluye ambos días.</p>
              </div>
              <form key={url} onSubmit={apply}>
                <div className="filter-grid">
                  <label className="search-field">
                    Buscar
                    <input
                      name="q"
                      type="search"
                      maxLength={200}
                      defaultValue={criteria.q}
                      placeholder="Título, entidad o referencia"
                    />
                  </label>
                  <label>
                    Entidad
                    <input name="entity" maxLength={200} defaultValue={criteria.entity} />
                  </label>
                  <label>
                    Ubicación de la entidad
                    <input
                      name="location" maxLength={200} defaultValue={criteria.location}
                      placeholder="Ciudad o departamento"
                    />
                  </label>
                  <label>
                    Vigencia
                    <select name="validity" defaultValue={criteria.validity ?? ""}>
                      <option value="">Todas las vigencias</option>
                      {Object.entries(validityLabels).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Estado SECOP
                    <select name="status" defaultValue={criteria.status}>
                      <option value="">Todos los estados</option>
                      {[...new Set([...options.statuses, criteria.status].filter(Boolean))].map(
                        (value) => (
                          <option key={value}>{value}</option>
                        ),
                      )}
                    </select>
                  </label>
                  <label>
                    Modalidad
                    <select name="modality" defaultValue={criteria.modality}>
                      <option value="">Todas las modalidades</option>
                      {[...new Set([...options.modalities, criteria.modality].filter(Boolean))].map(
                        (value) => (
                          <option key={value}>{value}</option>
                        ),
                      )}
                    </select>
                  </label>
                  <label>
                    Cierre desde (UTC)
                    <input name="closing_from" type="date" defaultValue={criteria.closing_from ?? ""} />
                  </label>
                  <label>
                    Cierre hasta (UTC)
                    <input
                      name="closing_to" type="date" max="9999-12-30"
                      defaultValue={criteria.closing_to ?? ""}
                    />
                  </label>
                  <label>
                    Publicación desde (UTC)
                    <input
                      name="published_from"
                      type="date"
                      defaultValue={criteria.published_from ?? ""}
                    />
                  </label>
                  <label>
                    Publicación hasta (UTC)
                    <input
                      name="published_to"
                      type="date"
                      max="9999-12-30"
                      defaultValue={criteria.published_to ?? ""}
                    />
                  </label>
                  <label>
                    Orden
                    <select name="sort" defaultValue={criteria.sort}>
                      {Object.entries(sorts).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Resultados por página
                    <select name="limit" defaultValue={limit}>
                      {[10, 25, 50, 100].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="filter-actions">
                  <button className="btn btn-p" type="submit">
                    Aplicar filtros
                  </button>
                  <button
                    type="button"
                    className="btn btn-s"
                    onClick={() => navigate(new URLSearchParams())}
                  >
                    Limpiar filtros
                  </button>
                </div>
              </form>
              {optionError ? (
                <p role="status">
                  No se pudieron actualizar las opciones de estado y modalidad. Se conservan las
                  opciones anteriores y el catálogo.
                  <button
                    className="btn btn-s"
                    onClick={() => setOptionRevision((value) => value + 1)}
                  >
                    Reintentar opciones
                  </button>
                </p>
              ) : null}
            </section>
            <section className="panel saved-filters" aria-label={`Filtros compartidos de ${companyName}`}>
              <label>
                Filtros compartidos de {companyName}
                <select
                  value={params.get("saved") ?? ""}
                  onChange={(event) => {
                    const preset = saved.find((entry) => String(entry.id) === event.target.value);
                    if (!preset) {
                      const next = new URLSearchParams(url);
                      next.delete("saved");
                      navigate(next);
                      return;
                    }
                    const next = new URLSearchParams();
                    for (const field of fields) {
                      const value = preset.criteria[field];
                      if (value) next.set(field, value);
                    }
                    next.set("saved", String(preset.id));
                    next.set("limit", String(limit));
                    navigate(next);
                  }}
                >
                  <option value="">Selecciona un filtro guardado</option>
                  {saved.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.name}
                    </option>
                  ))}
                </select>
              </label>
              {savedError ? <p role="status">{savedError}</p> : null}
              {selectedFilter &&
              fields.some((field) => criteria[field] !== selectedFilter.criteria[field]) ? (
                <p role="status">
                  Has ajustado este filtro en tu búsqueda. Los cambios no se comparten hasta que un
                  administrador los guarde.
                </p>
              ) : null}
              {role === "administrador" ? (
                <form
                  key={selectedFilter?.id ?? "new"}
                  onSubmit={(event) => void persist(event)}
                  className="saved-editor"
                >
                  <label>
                    Nombre del filtro
                    <input
                      name="name"
                      required
                      maxLength={100}
                      defaultValue={selectedFilter?.name ?? ""}
                    />
                  </label>
                  <button className="btn btn-s" name="action" value="new" disabled={busy}>
                    Guardar nuevo
                  </button>
                  <button
                    className="btn btn-s"
                    name="action"
                    value="update"
                    disabled={busy || !selectedFilter}
                  >
                    Actualizar seleccionado
                  </button>
                  <button
                    type="button"
                    className="btn btn-s"
                    disabled={busy || !selectedFilter}
                    onClick={() => void removeSaved()}
                  >
                    Eliminar seleccionado
                  </button>
                </form>
              ) : (
                <p>
                  Los administradores gestionan estos filtros. Puedes aplicarlos o ajustar tu
                  búsqueda.
                </p>
              )}
            </section>
            {page ? <CatalogFreshness page={page} /> : null}
            {current?.error ? (
              <div role="alert" className="banner banner-warn">
                {current.error}{" "}
                {page ? "Los resultados anteriores pueden estar desactualizados." : ""}
                <button className="btn btn-s" onClick={() => setRevision((value) => value + 1)}>
                  Reintentar consulta
                </button>
              </div>
            ) : null}
            {!current ? (
              <p role="status" className="empty">
                Cargando oportunidades…
              </p>
            ) : null}
            {page ? (
              <>
                <p className="result-count" role="status">
                  {page.total} resultados · Página {pageNumber}
                </p>
                <section className="panel" aria-label="Resultados">
                  {page.items.length ? (
                    <OpportunityTable
                      items={page.items}
                      detailHref={detailUrl}
                      action={(id) => <ShortlistToggle selection={shortlist} id={id} />}
                      onOpen={openDetail}
                    />
                  ) : (
                    <div className="empty">
                      <h2>No hay resultados para estos filtros</h2>
                      <p>
                        Ajusta la búsqueda o limpia los filtros. El catálogo puede no contener todos
                        los procesos.
                      </p>
                      <button className="btn btn-s" onClick={() => navigate(new URLSearchParams())}>
                        Ver todo el catálogo
                      </button>
                    </div>
                  )}
                </section>
                <nav className="pager" aria-label="Paginación">
                  <span className="pager-info">
                    {page.total ? Math.min(offset + 1, page.total) : 0}–
                    {Math.min(offset + page.items.length, page.total)} de {page.total}
                  </span>
                  <div className="pager-actions">
                    <button
                      className="btn btn-s"
                      disabled={pageNumber <= 1}
                      onClick={() => {
                        const next = new URLSearchParams(url);
                        next.set("page", String(pageNumber - 1));
                        navigate(next);
                      }}
                    >
                      Anterior
                    </button>
                    <button
                      className="btn btn-s"
                      disabled={offset + limit >= page.total}
                      onClick={() => {
                        const next = new URLSearchParams(url);
                        next.set("page", String(pageNumber + 1));
                        navigate(next);
                      }}
                    >
                      Siguiente
                    </button>
                  </div>
                </nav>
              </>
            ) : null}
          </>
        )}
        <p className="footnote">
          Fuente: SECOP II. Los campos ausentes se muestran como desconocidos. Este catálogo no
          confirma vigencia, relevancia ni aptitud de {companyName} para participar.
        </p>
      </main>
    </>
  );
}
