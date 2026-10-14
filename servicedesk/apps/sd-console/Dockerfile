# sd-console: build estático (Vite) servido por nginx sem privilégio em /sd-console/.
# /sd-ops e /sd-qa são roteados pelo Traefik para os serviços (mesmo site do Chatwoot: CTI_AUTH.md §2).
FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm test && pnpm build

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html/sd-console
EXPOSE 8080
