import type { Validity } from "../api/contracts";

export const validityLabels: Record<Validity, string> = {
  abierto: "Abierto",
  cerrado: "Cerrado",
  vencido: "Vencido",
  desconocida: "Vigencia desconocida",
};
