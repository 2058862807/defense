# Render free-tier frontend/gateway image: Express gateway + Vite production
# build of the React app (src/), proxying /api/* and /ws/* to the backend
# service via PYTHON_API_URL / PYTHON_WS_URL.
#
# NOTE: `npm ci` must run BEFORE setting NODE_ENV=production, otherwise npm
# omits devDependencies (vite/esbuild) which `npm run build` requires. The
# devDependencies are intentionally kept at runtime because server.ts has a
# static `import { createServer as createViteServer } from "vite"` at module
# load (guarded at runtime, but resolved at load time).
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json vite.config.js index.html ./
COPY src ./src
COPY server.ts ./

RUN npm ci && npm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "start"]
