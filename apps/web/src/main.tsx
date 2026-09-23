import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { SessionProvider } from "./auth/SessionProvider";
import "./design/tokens.css";
import "./design/app.css";
import "./styles.css";

/**
 * Cliente de consultas.
 *
 * `refetchOnWindowFocus` se desactiva a propósito: el analista alterna entre
 * esta aplicación y el portal de la fuente oficial, y cada vuelta de foco
 * recargaría la tabla y le haría perder la fila que estaba leyendo.
 *
 * `retry: 1` y no el valor por defecto: si la API no responde al segundo
 * intento, el problema no es transitorio y conviene decirlo en lugar de
 * mantener la pantalla cargando.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30_000,
    },
  },
});

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Missing root element");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
