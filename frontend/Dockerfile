FROM node:20-alpine

WORKDIR /app

# 先装依赖以利用层缓存
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 80

# 开发模式：HMR 友好；生产可改为 build + start
CMD ["npm", "run", "dev"]
