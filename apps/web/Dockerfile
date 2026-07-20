# Build context is apps/web (a plain npm package, no workspace path deps).
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Baked in at build time — Vite inlines env vars into the static bundle,
# so this must be the real public API origin for whatever environment
# this image is built for (e.g. https://api.example.com).
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
