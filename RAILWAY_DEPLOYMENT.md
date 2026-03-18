# 🚂 Railway 後端部署指南

## 步驟 1：部署後端到 Railway

1. **前往 Railway**: https://railway.app
2. **登入/註冊** (可用 GitHub 登入)
3. **New Project** → **Deploy from GitHub repo**
4. **選擇此專案**: `CardPilot`
5. **配置服務**:
   - Root Directory: `apps/game-server`
   - Build Command: `npm install && npm run build`
   - Start Command: `npm start`

## 步驟 2：設置環境變數（可選）

在 Railway 專案設置中添加（如果需要 Supabase，三個要一起設）：

```
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

若不使用 Supabase，請三個都不要設，伺服器會以 guest/local 模式啟動。

## 步驟 3：獲取 Railway 後端網址

部署完成後，Railway 會給你一個網址，例如：

```
https://cardpilot-game-server-production.up.railway.app
```

## 步驟 4：更新前端配置

### 選項 A：使用環境變數（推薦）

在 Netlify 專案設置中添加環境變數：

```
VITE_SERVER_URL=https://your-railway-url.railway.app
```

然後重新部署 Netlify 專案。

### 選項 B：直接修改代碼

在 `apps/web/src/App.tsx` 第 9 行修改：

```typescript
const SERVER = 'https://your-railway-url.railway.app';
```

## 步驟 5：重新部署前端

```bash
cd apps/web
npm run build
# 將 dist 目錄重新部署到 Netlify
```

## ✅ 測試

訪問你的 Netlify 網站，應該可以正常連接到 Railway 後端了！

---

## 🔧 故障排除

**如果連接失敗**：

1. 檢查 Railway 後端日誌
2. 確認 CORS 設置正確
3. 確認前端的 SERVER 網址正確

**檢查後端是否運行**：
訪問 `https://your-railway-url.railway.app/` 應該看到 "Cannot GET /"（這是正常的，表示服務器在運行）
