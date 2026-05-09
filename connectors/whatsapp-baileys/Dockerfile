# syntax=docker/dockerfile:1.6
FROM node:20-slim AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

FROM node:20-slim
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package*.json ./
COPY src ./src

RUN mkdir -p /app/auth /app/cache && \
    groupadd -r connector --gid 10001 && \
    useradd -r -g connector -u 10001 -d /app -s /sbin/nologin connector && \
    chown -R connector:connector /app

USER connector

EXPOSE 3000
ENV NODE_ENV=production

CMD ["node", "src/index.js"]
