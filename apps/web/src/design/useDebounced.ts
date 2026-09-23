import { useEffect, useState } from "react";

/**
 * Retrasa la propagación de un valor.
 *
 * Se usa para el campo de búsqueda: sin esto, cada pulsación de tecla lanzaría
 * una consulta y el listado parpadearía mientras se escribe. El retraso se
 * aplica al valor que va a la consulta, no al que se muestra en el campo, para
 * que el texto aparezca de inmediato y solo la petición espere.
 */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return settled;
}
