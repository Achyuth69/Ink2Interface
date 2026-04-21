# Stage 1: Build React app
FROM node:22-alpine AS builder
WORKDIR /app

# Accept backend URL at build time (set in Railway frontend service variables)
ARG VITE_API_URL=http://localhost:8080
ENV VITE_API_URL=$VITE_API_URL

COPY package.json package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY . .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
