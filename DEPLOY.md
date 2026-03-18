# 🚀 CardPilot 部署指南

## 方案一：快速免费部署 (推荐)

### 1️⃣ 部署后端 (Railway - 免费)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

**手动部署步骤：**

1. 注册 [Railway](https://railway.app) 账号 (用 GitHub 登录)
2. 新建 Project → Deploy PostgreSQL
3. 获取数据库连接字符串
4. 部署后端服务:

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 进入后端目录
cd apps/game-server

# 初始化项目
railway init

# 添加环境变量
railway variables set DATABASE_URL="postgresql://..."
railway variables set PORT="4000"
railway variables set NODE_ENV="production"

# 部署
railway up
```

**获取部署后的 URL：** `https://cardpilot-api.up.railway.app`

---

### 2️⃣ 部署前端 (Netlify - 免费)

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start)

**手动部署步骤：**

1. 注册 [Netlify](https://app.netlify.com/) 账号
2. 导入 GitHub 仓库
3. 配置:
   - **Base directory**: 留空 (仓库根目录)
   - **Build command**: `npm run build -w @cardpilot/web`
   - **Publish directory**: `apps/web/dist`

4. 添加环境变量:

   ```
   VITE_SERVER_URL=https://你的后端地址
   ```

5. 点击 **Deploy site**

---

## 方案二：一键部署脚本

### 后端部署脚本

```bash
#!/bin/bash
# deploy-backend.sh

echo "🚀 部署 CardPilot 后端..."

# 1. 确保你在 apps/game-server 目录
cd apps/game-server

# 2. 创建 Dockerfile
cat > Dockerfile << 'EOF'
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 4000
CMD ["node", "dist/server.js"]
EOF

# 3. 构建
docker build -t cardpilot-backend .

# 4. 推送到 Railway/Render
# 参考具体平台文档

echo "✅ 后端部署完成"
```

### 前端部署脚本

```bash
#!/bin/bash
# deploy-frontend.sh

echo "🎨 部署 CardPilot 前端..."

cd apps/web

# 1. 安装依赖
npm install

# 2. 构建
npm run build

# 3. 部署到 Netlify
netlify deploy --prod --dir=dist

echo "✅ 前端部署完成"
```

---

## 方案三：Docker 完整部署

### 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: cardpilot
      POSTGRES_PASSWORD: your_password
      POSTGRES_DB: cardpilot
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - '5432:5432'

  backend:
    build: ./apps/game-server
    ports:
      - '4000:4000'
    environment:
      - DATABASE_URL=postgresql://cardpilot:your_password@postgres:5432/cardpilot
      - PORT=4000
      - NODE_ENV=production
    depends_on:
      - postgres

  frontend:
    build: ./apps/web
    ports:
      - '80:80'
    environment:
      - VITE_SERVER_URL=http://localhost:4000

volumes:
  postgres_data:
```

### 运行

```bash
docker-compose up -d
```

---

## 📋 部署检查清单

### 后端检查

- [ ] PostgreSQL 数据库已创建
- [ ] 数据库连接字符串正确
- [ ] Socket.IO CORS 配置允许前端域名
- [ ] 环境变量设置完成
- [ ] 健康检查端点 `/health` 可访问

### 前端检查

- [ ] VITE_SERVER_URL 指向正确后端
- [ ] 构建成功无错误
- [ ] 图片资源路径正确
- [ ] WebSocket 连接正常

### 域名配置 (可选)

- [ ] 购买域名
- [ ] 配置 DNS 解析
- [ ] 设置 SSL 证书
- [ ] 更新 CORS 白名单

---

## 🔧 常见问题

### 1. CORS 错误

```
修改 apps/game-server/src/server.ts:
```

```typescript
const io = new Server(httpServer, {
  cors: {
    origin: ['https://你的前端域名.netlify.app', 'http://localhost:5173'],
    credentials: true,
  },
});
```

### 2. WebSocket 连接失败

确保使用 `wss://` 而不是 `ws://` (HTTPS 页面需要安全 WebSocket)

### 3. 数据库连接失败

检查 Railway/Render 的数据库连接字符串格式

---

## 💡 推荐配置

| 服务   | 平台             | 费用           | 特点               |
| ------ | ---------------- | -------------- | ------------------ |
| 前端   | Netlify          | 免费           | 自动部署，CDN 加速 |
| 后端   | Railway          | 免费 $5/月额度 | 自动扩展           |
| 数据库 | Railway Postgres | 免费           | 自动备份           |
| 备选   | Render           | 免费           | 支持 WebSocket     |

---

## 🎯 下一步

1. 选择部署平台 (Netlify + Railway 推荐)
2. 准备 GitHub 仓库
3. 按上述步骤部署
4. 分享链接给朋友！

需要我帮你配置具体的部署文件吗？
