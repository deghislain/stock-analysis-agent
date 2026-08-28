# ─────────────────────────────────────────────────────────────────────────────
# Frontend Dockerfile — multi-stage build
#
# Stage 1 (builder): Node 20 Alpine — installs deps and compiles the React app
#                    with Vite into a static /app/dist folder.
# Stage 2 (serve):   nginx Alpine  — serves the static files; replaces the
#                    Node runtime entirely so the production image is tiny.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first to maximise layer caching — npm install only reruns
# when package.json or package-lock.json changes.
COPY package.json package-lock.json* ./
RUN npm ci --silent

# Copy the rest of the source and build.
# VITE_API_URL is baked into the bundle at build time if provided; defaults to
# '' (empty) so the Vite proxy or nginx config handles routing to /api.
COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

# Remove the default nginx welcome page.
RUN rm -rf /usr/share/nginx/html/*

# Copy the compiled static assets from the builder stage.
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our custom nginx configuration.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
