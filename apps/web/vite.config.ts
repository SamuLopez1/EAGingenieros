import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Sin `rewrite`. El prefijo `/api` NO es una marca del proxy: es parte
      // real de las rutas de FastAPI (`/api/v1/...`, `/api/health`). Eliminarlo
      // convertía `/api/v1/opportunities` en `/v1/opportunities`, una ruta que
      // la API no sirve, y el listado devolvía 404. El smoke test no lo
      // detectaba porque solo comprobaba `/api/health`, que coincidía por
      // casualidad al existir `/health` en la raíz.
      //
      // El servidor de producción (nginx) tampoco reescribe, así que desarrollo
      // y despliegue resuelven exactamente las mismas rutas.
      "/api": {
        target: apiTarget,
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
