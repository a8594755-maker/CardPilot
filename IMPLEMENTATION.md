# CardPilot Implementation Guide

## 项目架构

### 技术栈
- **Backend**: NestJS + Socket.IO + Prisma + PostgreSQL
- **Frontend**: React + TypeScript + Tailwind CSS
- **Shared**: TypeScript 类型共享包

### 目录结构
```
CardPilot/
├── apps/
│   ├── server/           # NestJS 后端服务器
│   │   ├── src/
│   │   │   ├── advice/       # GTO 建议引擎
│   │   │   ├── hand/         # 手牌逻辑
│   │   │   ├── prisma/       # Prisma schema & service
│   │   │   ├── table/        # 桌子/房间管理
│   │   │   ├── app.module.ts
│   │   │   └── main.ts
│   │   └── package.json
│   └── web/              # React 前端
│       ├── src/
│       │   ├── components/   # UI 组件
│       │   │   ├── gto-panel/
│       │   │   └── poker-table/
│       │   ├── hooks/
│       │   └── App.tsx
│       └── package.json
├── packages/
│   ├── shared-types/     # 前后端共享类型
│   └── poker-evaluator/  # 牌力计算库
└── package.json          # Workspace 根配置
```

## 快速开始

### 1. 安装依赖
```bash
# 根目录
npm install

# 安装 NestJS 服务器依赖
cd apps/server
npm install

# 回到根目录
cd ../..
```

### 2. 数据库配置
```bash
# 创建 .env 文件
echo "DATABASE_URL=postgresql://user:password@localhost:5432/cardpilot" > apps/server/.env

# 生成 Prisma 客户端
cd apps/server
npx prisma generate

# 运行迁移
npx prisma migrate dev --name init
```

### 3. 启动开发服务器
```bash
# 启动后端 (NestJS)
cd apps/server
npm run dev

# 在另一个终端启动前端
cd apps/web
npm run dev
```

## 核心功能

### Coach Mode (训练模式)
- 实时 GTO 建议
- 策略频率可视化 (Raise/Call/Fold 百分比)
- 情境分析 (位置、底池赔率、有效筹码)
- 偏離警告系统

### 游戏功能
- 6-max No Limit Hold'em
- 完整的下注流程 (Prelude → Flop → Turn → River → Showdown)
- 房间系统 (公开/私人房间)
- 座位管理

### GTO 数据库
- 基于 spot key 的查询系统
- 支持多种情境: open, defend, 3bet, 4bet
- 可扩展的 JSON 数据格式

## API 文档

### WebSocket Events

#### Client → Server
- `room:create` - 创建房间
- `room:join_code` - 通过房间码加入
- `seat:sit` - 入座
- `seat:stand` - 站起
- `hand:start` - 开始手牌
- `hand:action` - 玩家动作
- `advice:request` - 请求建议

#### Server → Client
- `connection:established` - 连接建立
- `room:created` - 房间创建成功
- `room:joined` - 加入房间成功
- `table:snapshot` - 桌子状态快照
- `hand:deal` - 发牌
- `hand:action_applied` - 动作确认
- `hand:street_advanced` - 进入下一街
- `advice:recommendation` - GTO 建议
- `hand:ended` - 手牌结束

## 开发计划

### ✅ 已完成
- [x] Prisma Schema 设计
- [x] NestJS 项目结构
- [x] Hand State Machine
- [x] Advice Engine
- [x] Preflop Chart 数据
- [x] WebSocket Gateway
- [x] Coach Mode UI

### 🚧 待完成
- [ ] 完整的牌力计算 (poker-evaluator)
- [ ] Side pot 逻辑
- [ ] 断线重连机制
- [ ] 倒數計時器
- [ ] 更多 Preflop Chart 数据
- [ ] Postflop GTO 建议
- [ ] 用户认证系统
- [ ] 手牌历史记录

## 环境变量

### apps/server/.env
```
DATABASE_URL=postgresql://user:password@localhost:5432/cardpilot
PORT=4000
```

### apps/web/.env
```
VITE_SERVER_URL=http://localhost:4000
```

## 测试

```bash
# 后端测试
cd apps/server
npm run test

# 类型检查
cd ../..
npm run typecheck
```

## 部署

### Docker (待实现)
```bash
docker-compose up -d postgres
```

### 生产构建
```bash
# 构建所有包
npm run build

# 启动生产服务器
cd apps/server
npm start
```
