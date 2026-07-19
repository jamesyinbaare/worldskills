FROM node:20-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci

COPY . .

EXPOSE 3000

# Fresh named volumes for /app/node_modules start empty and hide the
# image layer. npm ci never rewrites package-lock.json (avoids watch loops).
CMD ["sh", "-c", "npm ci && npm run dev:docker"]
