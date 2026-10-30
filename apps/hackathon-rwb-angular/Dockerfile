FROM node:22-alpine AS build
WORKDIR /web
COPY apps/hackathon-rwb-angular/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY apps/hackathon-rwb-angular/ ./
RUN npm run build
FROM nginxinc/nginx-unprivileged:alpine
COPY apps/hackathon-rwb-angular/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist/hackathon-rwb-angular/browser /usr/share/nginx/html
EXPOSE 8080
