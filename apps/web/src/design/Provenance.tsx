/**
 * Componentes de procedencia.
 *
 * Todos los exports de este módulo son componentes, que es lo que exige la
 * regla `react-refresh/only-export-components`. Los textos y significados
 * viven en `platform.ts`.
 *
 * Dos reglas del sistema de diseño se aplican aquí y no son negociables:
 *
 *   1. Ninguna señal depende solo del color. La plataforma lleva su etiqueta
 *      escrita, no únicamente un color de fondo.
 *   2. Un posible duplicado se **señala**, nunca se fusiona. El sistema no
 *      colapsa dos filas por su cuenta porque la medición no respalda ninguna
 *      clave que garantice que son el mismo proceso; decidirlo es del analista.
 */

import type { Platform } from "../api/contracts";
import { PLATFORM_LABELS, PLATFORM_MEANINGS } from "./platform";

export function SourceBadge({
  platform,
  label,
}: {
  platform: Platform;
  label?: string;
}) {
  // Tolerante a un valor inesperado a propósito: la interfaz y la API se
  // despliegan por separado, y una plataforma que este código aún no conoce
  // debe mostrarse tal cual, no tumbar la página entera con una pantalla en
  // blanco. El texto visible sigue siendo el dato, así que no se inventa nada.
  const known = typeof platform === "string" && platform in PLATFORM_LABELS;
  const text = label || PLATFORM_LABELS[platform] || String(platform ?? "");
  const modifier = known ? platform.toLowerCase().replace("_", "-") : "unknown";
  return (
    <span
      className={`source-badge source-${modifier}`}
      title={known ? PLATFORM_MEANINGS[platform] : "Plataforma no reconocida."}
    >
      {text}
    </span>
  );
}

/**
 * Aviso de posible duplicado entre plataformas.
 *
 * Aparece solo cuando el mismo NIT y la misma referencia normalizada existen
 * en más de una plataforma. Se redacta como posibilidad —«posible»— y no como
 * hecho, porque la referencia puede coincidir entre entidades distintas: el
 * valor `001-2026` aparece más de mil veces en SECOP II.
 */
export function DuplicateNotice({
  platforms,
}: {
  platforms: readonly string[];
}) {
  if (platforms.length < 2) return null;
  return (
    <span
      className="dup-flag"
      title={
        "El mismo NIT y la misma referencia aparecen en más de una plataforma. " +
        "Puede ser el mismo proceso publicado dos veces, o dos procesos " +
        "distintos con referencias coincidentes. El sistema no los fusiona: " +
        "compruébelo antes de decidir."
      }
    >
      Posible duplicado
      <span className="dup-platforms"> · {platforms.join(" + ")}</span>
    </span>
  );
}
