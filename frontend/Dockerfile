# ─────────────────────────────────────────────────────────────────────────────
# Frontend Dockerfile — multi-stage build
#
# Stage 1 (builder): Node 20 Alpine — installs deps and compiles the React app
#                    with Vite (tsc + vite build) into a static /app/dist folder.
# Stage 2 (serve):   nginx Alpine  — copies only the compiled assets; the Node
#                    runtime is discarded entirely, keeping the image tiny.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy lockfile and manifest first to maximise layer caching — npm ci only
# reruns when these two files change, not on every source edit.
# NOTE: NODE_ENV must NOT be set to "production" here — npm ci would skip
# devDependencies (typescript, vite, eslint …) which are needed to compile.
# Vite sets NODE_ENV=production internally when it runs `vite build`.
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Copy the rest of the source.
COPY . .

# VITE_API_URL is read by Vite at build time and baked into the bundle.
# Default is empty — the nginx proxy in Stage 2 forwards /api/* to the
# backend container, so no explicit URL is needed for Docker Compose.
# Override only when building for a remote backend:
#   docker build --build-arg VITE_API_URL=https://api.example.com .
ARG VITE_API_URL=""
RUN VITE_API_URL=${VITE_API_URL} npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

# Remove the default nginx welcome page bundled with the image.
RUN rm -rf /usr/share/nginx/html/*

# Copy the compiled static assets from the builder stage.
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default site block with our custom config (SPA fallback +
# /api proxy to the backend container + long-lived cache headers).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Validate the nginx configuration at build time so a bad config is caught
# before the image is pushed or run.
RUN nginx -t

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
