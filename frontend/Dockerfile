# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

# Nginx config with large buffer sizes and SPA fallback
RUN cat > /etc/nginx/conf.d/default.conf <<'NGINX'
server {
    listen 3000;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Fix "Request Header Or Cookie Too Large"
    large_client_header_buffers 4 32k;
    client_header_buffer_size 16k;

    location /api {
        proxy_pass http://orchestrator:8083;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffer_size 16k;
        proxy_buffers 4 16k;
    }

    location /ws {
        proxy_pass http://orchestrator:8083;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
