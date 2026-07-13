FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# BUILD_ENV=production 时在构建阶段完成 next build，容器启动直接 next start
ARG BUILD_ENV=development
RUN if [ "$BUILD_ENV" = "production" ]; then npm run build; fi

EXPOSE 80

CMD ["sh", "-c", "if [ \"$BUILD_ENV\" = \"production\" ]; then npm run start; else npm run dev; fi"]
