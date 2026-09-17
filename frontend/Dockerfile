# Frontend image: build the Vite SPA, then serve it with nginx.
# nginx also reverse-proxies /api to the backend so SPA + API share one origin.

# ---- build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- serve stage ----
FROM nginx:1.27-alpine
# Static SPA output.
COPY --from=build /app/dist /usr/share/nginx/html
# Our server config (SPA fallback + /api proxy with prefix strip).
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
