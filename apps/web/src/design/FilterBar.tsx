/**
 * Barra de filtros del listado.
 *
 * Es un componente controlado: no guarda estado propio. El estado de los
 * filtros vive en la página, junto con la consulta y la URL, porque tres
 * copias del mismo estado —una en el componente, otra en la consulta y otra en
 * la dirección— acaban divergiendo y muestran resultados que no corresponden a
 * lo que dicen los campos.
 */

import type { OpportunityFilters, Platform } from "../api/contracts";
import { PLATFORM_LABELS } from "./platform";

export interface FilterBarProps {
  filters: OpportunityFilters;
  onChange: (patch: Partial<OpportunityFilters>) => void;
  onClear: () => void;
  /** Número de filtros activos, para que el botón de limpiar tenga sentido. */
  activeCount: number;
}

const PLATFORMS: Platform[] = ["SECOP_I", "SECOP_II"];

export function FilterBar({ filters, onChange, onClear, activeCount }: FilterBarProps) {
  return (
    <form
      className="filters"
      role="search"
      aria-label="Filtros de oportunidades"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="filter-field filter-grow">
        <label htmlFor="f-q">Buscar</label>
        <input
          id="f-q"
          type="search"
          placeholder="Referencia, título o entidad"
          value={filters.q ?? ""}
          onChange={(event) => onChange({ q: event.target.value })}
        />
      </div>

      <div className="filter-field">
        <label htmlFor="f-platform">Plataforma</label>
        <select
          id="f-platform"
          value={filters.platform ?? ""}
          onChange={(event) =>
            onChange({
              platform: (event.target.value || undefined) as Platform | undefined,
            })
          }
        >
          <option value="">Todas</option>
          {PLATFORMS.map((platform) => (
            <option key={platform} value={platform}>
              {PLATFORM_LABELS[platform]}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-field">
        <label htmlFor="f-estado">Estado</label>
        <input
          id="f-estado"
          type="text"
          placeholder="Cualquiera"
          value={filters.estado ?? ""}
          onChange={(event) => onChange({ estado: event.target.value })}
        />
      </div>

      <div className="filter-field">
        <label htmlFor="f-modalidad">Modalidad</label>
        <input
          id="f-modalidad"
          type="text"
          placeholder="Cualquiera"
          value={filters.modalidad ?? ""}
          onChange={(event) => onChange({ modalidad: event.target.value })}
        />
      </div>

      <div className="filter-field">
        <label htmlFor="f-nit">NIT de la entidad</label>
        <input
          id="f-nit"
          type="text"
          inputMode="numeric"
          placeholder="Solo dígitos"
          value={filters.entity_nit ?? ""}
          onChange={(event) => onChange({ entity_nit: event.target.value })}
        />
      </div>

      <div className="filter-field">
        <label htmlFor="f-desde">Publicadas desde</label>
        <input
          id="f-desde"
          type="date"
          value={filters.desde ? filters.desde.slice(0, 10) : ""}
          onChange={(event) =>
            onChange({
              // El filtro se envía con hora explícita: una fecha suelta se
              // interpretaría a medianoche y dejaría fuera los procesos
              // publicados durante el propio día indicado.
              desde: event.target.value ? `${event.target.value}T00:00:00Z` : undefined,
            })
          }
        />
      </div>

      <div className="filter-field">
        <label htmlFor="f-hasta">Publicadas hasta</label>
        <input
          id="f-hasta"
          type="date"
          value={filters.hasta ? filters.hasta.slice(0, 10) : ""}
          onChange={(event) =>
            onChange({
              hasta: event.target.value ? `${event.target.value}T23:59:59Z` : undefined,
            })
          }
        />
      </div>

      <div className="filter-actions">
        <button
          type="button"
          className="btn btn-s"
          onClick={onClear}
          disabled={activeCount === 0}
        >
          Limpiar{activeCount > 0 ? ` (${activeCount})` : ""}
        </button>
      </div>
    </form>
  );
}
