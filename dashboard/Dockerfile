FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
COPY .next .next
COPY public public
COPY next.config.ts package.json package-lock.json ./
RUN npm install --omit=dev --ignore-scripts
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "-p", "3000"]