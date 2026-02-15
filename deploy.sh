#!/bin/bash

# CardPilot 一键部署脚本
# 使用: ./deploy.sh [backend|frontend|all]

set -euo pipefail

ACTION="${1:-}"
RAILWAY_TOKEN=""
NETLIFY_AUTH_TOKEN=""
NETLIFY_SITE_ID=""
BACKEND_URL=""

case "$ACTION" in
  backend)
    RAILWAY_TOKEN="${2:-}"
    ;;
  frontend)
    NETLIFY_AUTH_TOKEN="${2:-}"
    NETLIFY_SITE_ID="${3:-}"
    ;;
  all)
    RAILWAY_TOKEN="${2:-}"
    NETLIFY_AUTH_TOKEN="${3:-}"
    NETLIFY_SITE_ID="${4:-}"
    ;;
esac

show_help() {
  echo "🚀 CardPilot 部署脚本"
  echo ""
  echo "使用方法:"
  echo "  ./deploy.sh backend <RAILWAY_TOKEN>     - 部署后端"
  echo "  ./deploy.sh frontend <NETLIFY_AUTH_TOKEN> <NETLIFY_SITE_ID> - 部署前端"
  echo "  ./deploy.sh all <RAILWAY_TOKEN> <NETLIFY_AUTH_TOKEN> <NETLIFY_SITE_ID> - 部署全部"
  echo ""
  echo "获取 Token:"
  echo "  Railway: https://railway.app/account/tokens"
  echo "  Netlify: https://app.netlify.com/user/applications#personal-access-tokens"
  echo ""
  echo "获取 NETLIFY_SITE_ID:"
  echo "  Netlify 项目设置 -> Site details -> Site information -> API ID"
}

deploy_backend() {
  echo "📡 部署后端到 Railway..."
  
  if [ -z "$RAILWAY_TOKEN" ]; then
    echo "❌ 错误: 需要提供 Railway Token"
    show_help
    exit 1
  fi
  
  # 检查 railway CLI
  if ! command -v railway &> /dev/null; then
    echo "📦 安装 Railway CLI..."
    npm install -g @railway/cli
  fi
  
  # 登录
  echo "🔑 登录 Railway..."
  railway login --token "$RAILWAY_TOKEN"
  
  # 进入后端目录
  pushd apps/game-server > /dev/null
  
  # 初始化项目 (如果不存在)
  if [ ! -f .railway/config.json ]; then
    echo "🆕 初始化 Railway 项目..."
    railway init --name cardpilot-backend
  fi
  
  # 部署
  echo "🚀 开始部署..."
  railway up --detach
  
  # 获取 URL
  BACKEND_URL="$(railway domain | tr -d '[:space:]')"
  echo "✅ 后端部署成功!"
  echo "🌐 后端地址: $BACKEND_URL"
  echo ""
  echo "⚠️  请记下这个地址，部署前端时需要用到"
  
  popd > /dev/null
}

deploy_frontend() {
  echo "🎨 部署前端到 Netlify..."
  
  if [ -z "$NETLIFY_AUTH_TOKEN" ]; then
    echo "❌ 错误: 需要提供 Netlify Auth Token"
    show_help
    exit 1
  fi

  if [ -z "$NETLIFY_SITE_ID" ]; then
    echo "❌ 错误: 需要提供 Netlify Site ID"
    show_help
    exit 1
  fi
  
  # 检查 Netlify CLI
  if ! command -v netlify &> /dev/null; then
    echo "📦 安装 Netlify CLI..."
    npm install -g netlify-cli
  fi
  
  if [ -z "$BACKEND_URL" ]; then
    echo ""
    read -p "请输入后端地址 (例如: https://cardpilot-api.up.railway.app): " BACKEND_URL
  fi
  
  if [ -z "$BACKEND_URL" ]; then
    echo "❌ 错误: 需要提供后端地址"
    exit 1
  fi
  
  # 构建前端
  echo "🔧 构建前端..."
  VITE_SERVER_URL="$BACKEND_URL" npm run build -w @cardpilot/web

  # 部署
  echo "🚀 开始部署..."
  netlify deploy --prod --dir=apps/web/dist --site "$NETLIFY_SITE_ID" --auth "$NETLIFY_AUTH_TOKEN"
  
  echo "✅ 前端部署成功!"
}

# 主逻辑
case $ACTION in
  backend)
    deploy_backend
    ;;
  frontend)
    deploy_frontend
    ;;
  all)
    deploy_backend
    echo ""
    echo "========================================"
    echo ""
    deploy_frontend
    ;;
  *)
    show_help
    exit 1
    ;;
esac

echo ""
echo "🎉 部署完成!"
echo ""
echo "📋 下一步:"
echo "  1. 在 Railway Dashboard 添加 PostgreSQL 数据库"
echo "  2. 复制数据库连接字符串到 Railway 环境变量 DATABASE_URL"
echo "  3. 在 Netlify 项目设置中添加环境变量 VITE_SERVER_URL"
echo "  4. 重新部署以应用更改"
