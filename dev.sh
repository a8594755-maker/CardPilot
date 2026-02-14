#!/bin/bash

# CardPilot 开发服务器管理脚本

COMMAND=$1

case $COMMAND in
  start)
    echo "🚀 启动 CardPilot 开发服务器..."
    
    # 检查端口占用
    PORT_4000=$(lsof -ti:4000 2>/dev/null)
    if [ ! -z "$PORT_4000" ]; then
      echo "⚠️  端口 4000 被占用，正在停止现有进程..."
      kill -9 $PORT_4000 2>/dev/null
      sleep 1
    fi
    
    # 启动后端
    echo "📡 启动后端服务器 (端口 4000)..."
    (cd apps/game-server && npm run dev > /tmp/game-server.log 2>&1 &)
    
    # 等待后端启动
    sleep 3
    
    # 检查后端状态
    if curl -s http://localhost:4000/health > /dev/null; then
      echo "✅ 后端启动成功"
    else
      echo "❌ 后端启动失败，查看日志: tail -f /tmp/game-server.log"
    fi
    
    # 启动前端
    echo "🎨 启动前端开发服务器 (端口 5173)..."
    (cd apps/web && npm run dev > /tmp/web.log 2>&1 &)
    
    sleep 2
    
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  🃏 CardPilot 开发服务器已启动"
    echo "═══════════════════════════════════════════════════"
    echo ""
    echo "  📱 前端: http://localhost:5173"
    echo "  🔌 后端: http://localhost:4000"
    echo ""
    echo "  日志文件:"
    echo "    后端: tail -f /tmp/game-server.log"
    echo "    前端: tail -f /tmp/web.log"
    echo ""
    echo "  停止服务: ./dev.sh stop"
    echo "═══════════════════════════════════════════════════"
    ;;
    
  stop)
    echo "🛑 停止 CardPilot 服务器..."
    
    # 查找并停止相关进程
    pkill -f "tsx src/server.ts" 2>/dev/null
    pkill -f "vite" 2>/dev/null
    
    echo "✅ 所有服务已停止"
    ;;
    
  restart)
    ./dev.sh stop
    sleep 1
    ./dev.sh start
    ;;
    
  status)
    echo "📊 服务状态:"
    echo ""
    
    # 检查后端
    if curl -s http://localhost:4000/health > /dev/null 2>&1; then
      echo "  ✅ 后端: http://localhost:4000 (运行中)"
    else
      echo "  ❌ 后端: 未运行"
    fi
    
    # 检查前端
    if curl -s http://localhost:5173/ > /dev/null 2>&1; then
      echo "  ✅ 前端: http://localhost:5173 (运行中)"
    else
      echo "  ❌ 前端: 未运行"
    fi
    
    echo ""
    echo "进程列表:"
    ps aux | grep -E "(tsx|vite)" | grep -v grep | grep -v "dev.sh" || echo "  无相关进程"
    ;;
    
  logs)
    echo "📜 实时日志 (按 Ctrl+C 退出)..."
    tail -f /tmp/game-server.log /tmp/web.log 2>/dev/null
    ;;
    
  *)
    echo "CardPilot 开发服务器管理脚本"
    echo ""
    echo "用法: ./dev.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start    启动所有服务"
    echo "  stop     停止所有服务"
    echo "  restart  重启所有服务"
    echo "  status   查看服务状态"
    echo "  logs     查看实时日志"
    echo ""
    ;;
esac
