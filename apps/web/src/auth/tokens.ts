/**
 * Almacenamiento de los tokens de sesión.
 *
 * Decisión y su motivo
 * --------------------
 * Se usa `sessionStorage`, no `localStorage`. La diferencia importa: cualquier
 * script que llegue a ejecutarse en esta página puede leer ambos, pero
 * `sessionStorage` no sobrevive al cierre de la pestaña, así que la ventana de
 * exposición de un token robado es de una sesión de trabajo y no indefinida.
 *
 * El riesgo no es teórico en esta aplicación: la interfaz muestra texto que
 * viene de los pliegos —título, entidad, referencia— y ese contenido es no
 * confiable por definición. React lo escapa al renderizarlo, pero la defensa no
 * debe depender de un único mecanismo.
 *
 * El precio es que hay que volver a iniciar sesión al cerrar el navegador. La
 * solución completa es que el servidor entregue el token de refresco en una
 * cookie `httpOnly`, que ningún script puede leer; eso exige cambiar la API,
 * que hoy devuelve los tokens en el cuerpo. Queda como endurecimiento
 * pendiente y así se declara en vez de fingir que ya está resuelto.
 *
 * El token de acceso vive además en memoria, para que la ruta caliente de cada
 * petición no toque el almacenamiento del navegador.
 */

const ACCESS_KEY = "eag.access_token";
const REFRESH_KEY = "eag.refresh_token";

let accessToken: string | null = null;
let refreshToken: string | null = null;

function storage(): Storage | null {
  // En pruebas y en renderizado en servidor no hay sessionStorage. Se degrada a
  // memoria en lugar de fallar: la sesión funciona, solo que no persiste.
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

/** Recupera los tokens guardados. Se llama una vez al arrancar. */
export function loadTokens(): void {
  const store = storage();
  if (!store) return;
  accessToken = store.getItem(ACCESS_KEY);
  refreshToken = store.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  accessToken = access;
  refreshToken = refresh;
  const store = storage();
  if (!store) return;
  store.setItem(ACCESS_KEY, access);
  store.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  accessToken = null;
  refreshToken = null;
  const store = storage();
  if (!store) return;
  store.removeItem(ACCESS_KEY);
  store.removeItem(REFRESH_KEY);
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  return refreshToken;
}

export function hasSession(): boolean {
  return accessToken !== null;
}
