# Imagen de la web. Construcción en dos etapas: la primera compila los activos
# con Node, la segunda los sirve con nginx. La imagen final no incluye Node ni
# `node_modules`, así que no arrastra herramientas de compilación a producción.

FROM node:24-alpine AS build

WORKDIR /app

# Las dependencias se copian e instalan antes que el código para aprovechar la
# caché de capas: cambiar un componente no reinstala todo el árbol.
# `npm ci` y no `npm install`: respeta el lockfile y falla si divergen.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# La web se sirve desde el mismo origen que la API, detrás de nginx, así que
# las peticiones van a rutas relativas `/api/...`. Un valor vacío aquí es
# deliberado; definir VITE_API_BASE_URL solo si la API vive en otro host.
ENV VITE_API_BASE_URL=""
RUN npm run build


FROM nginx:1.27-alpine

# Configuración propia: sirve la SPA y actúa de proxy hacia la API.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Comprobación en tiempo de construcción: sin `index.html` nginx arrancaría y
# devolvería 404 en todas las rutas, que es un fallo silencioso hasta que
# alguien abre el navegador.
RUN test -f /usr/share/nginx/html/index.html \
    && echo "Activos web presentes"

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
