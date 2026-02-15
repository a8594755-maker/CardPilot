# 🚀 CardPilot 快速部署指南 (5分钟上线)

## 📋 准备工作

1. **GitHub 账号** - 代码托管
2. **Netlify 账号** - 前端托管 (免费)
3. **Railway 账号** - 后端托管 (免费 $5/月额度)

---

## 第一步：推送代码到 GitHub

```bash
# 初始化 Git (如果还没做)
git init
git add .
git commit -m "Initial commit"

# 创建 GitHub 仓库并推送
gh repo create cardpilot --public --source=. --push
# 或者手动在 GitHub 创建仓库后:
git remote add origin https://github.com/你的用户名/cardpilot.git
git push -u origin main
```

---

## 第二步：部署后端 (Railway)

### 2.1 创建 PostgreSQL 数据库
1. 登录 [Railway Dashboard](https://railway.app/dashboard)
2. 点击 **New Project** → **Provision PostgreSQL**
3. 记下数据库连接信息 (后面需要)

### 2.2 部署后端服务

**方法一：一键部署 (推荐)**

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/你的用户名/cardpilot)

**方法二：手动部署**

```bash
# 1. 安装 Railway CLI
npm install -g @railway/cli

# 2. 登录
railway login

# 3. 进入后端目录
cd apps/game-server

# 4. 初始化项目
railway init --name cardpilot-backend

# 5. 添加 PostgreSQL 数据库
# 在 Railway Dashboard → 项目 → New → Database → Add PostgreSQL

# 6. 设置环境变量
railway variables set DATABASE_URL="postgresql://..."
railway variables set PORT="4000"
railway variables set NODE_ENV="production"
railway variables set CORS_ORIGIN="https://你的前端域名.netlify.app"

# 7. 部署
railway up

# 8. 生成域名
railway domain

# 记下这个地址，例如: https://cardpilot-backend.up.railway.app
```

---

## 第三步：部署前端 (Netlify)

### 3.1 导入项目
1. 登录 [Netlify Dashboard](https://app.netlify.com/)
2. 点击 **Add new site** → **Import an existing project**
3. 导入你的 GitHub 仓库

### 3.2 配置构建设置

| 设置项 | 值 |
|--------|-----|
| **Base directory** | 留空（仓库根目录） |
| **Build command** | `npm run build -w @cardpilot/web` |
| **Publish directory** | `apps/web/dist` |

### 3.3 添加环境变量

点击 **Environment Variables**，添加:

```
VITE_SERVER_URL=https://你的后端地址.railway.app
```

### 3.4 部署
点击 **Deploy site**

---

## 第四步：验证部署

### 后端健康检查
```bash
curl https://你的后端地址.railway.app/health
# 应该返回: {"ok":true}
```

### 前端访问
打开 Netlify 提供的域名，应该能看到游戏界面。

### 测试游戏
1. 创建一个房间
2. 复制房间码给朋友
3. 朋友用房间码加入
4. 开始游戏！

---

## 🔧 自定义域名 (可选)

### 前端自定义域名
1. Netlify 项目 → Domain management
2. 添加你的域名
3. 按提示配置 DNS

### 后端自定义域名
1. Railway 项目 → Settings → Domains
2. 添加自定义域名
3. 更新前端环境变量为新的后端地址
4. 重新部署前端

---

## 💰 费用说明

| 平台 | 免费额度 | 超出费用 |
|------|----------|----------|
| **Netlify** | 免费套餐可用 | Pro $19/月起 |
| **Railway** | $5/月额度 | 按需付费 |
| **PostgreSQL** | 包含在 $5 额度内 | 按存储计费 |

**小流量项目完全免费！**

---

## 🚨 常见问题

### 1. CORS 错误
```
Access-Control-Allow-Origin
```
**解决**: 在 Railway 环境变量中添加:
```
CORS_ORIGIN=https://你的前端域名.netlify.app
```

### 2. WebSocket 连接失败
**解决**: 确保使用 `wss://` 协议:
```
VITE_SERVER_URL=wss://你的后端地址.railway.app
```

### 3. 数据库连接失败
**解决**: 检查 Railway PostgreSQL 的 `DATABASE_URL` 是否正确设置

### 4. 图片不显示
**解决**: 确保 `apps/web/public/cards/` 文件夹已提交到 Git

---

## 📞 需要帮助？

1. Railway 文档: https://docs.railway.app
2. Netlify 文档: https://docs.netlify.com
3. Socket.IO 部署指南: https://socket.io/docs/v4/

---

## 🎉 部署成功后

你可以分享这个链接给朋友：
```
https://你的项目名.netlify.app
```

大家打开浏览器就能一起玩扑克了！🃏
