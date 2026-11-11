# 1) React ilovani build qilish
FROM node:24-alpine AS client
WORKDIR /app/client
COPY client/package.json client/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY client/ ./
RUN npm run build

# 2) Server: API + build qilingan ilova (bitta port)
FROM node:24-alpine
ENV NODE_ENV=production \
    PORT=3001
WORKDIR /app/server
COPY server/package.json server/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY server/src ./src
COPY --from=client /app/client/dist /app/client/dist

# Bot konteyneri bilan bir xil UID (1000) — /data dagi baza va taqdimotlarga ikkalasi ham yoza oladi
USER node
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:3001/api/health || exit 1
CMD ["node", "--disable-warning=ExperimentalWarning", "src/index.js"]
