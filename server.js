const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');

const app = express();
app.use(cors());

const server = http.createServer(app);

// 設定 Socket.io (允許任何前端連線)
const io = new Server(server, {
  cors: {
    origin: "*", // 之後上線可以改成你的 Vercel 網址
    methods: ["GET", "POST"]
  }
});

// 遊戲狀態 (存記憶體，速度最快)
let gameState = {
  players: {},
  pot: 0
};

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', players: Object.keys(gameState.players).length });
});

io.on('connection', (socket) => {
  console.log('一位玩家連線了:', socket.id);

  // 當玩家加入
  socket.on('join_game', (name) => {
    gameState.players[socket.id] = { name: name, stack: 1000 };
    // 廣播給所有人：有新人來了
    io.emit('update_state', gameState);
  });

  // 當玩家下注
  socket.on('bet', (amount) => {
    if (gameState.players[socket.id]) {
      gameState.players[socket.id].stack -= amount;
      gameState.pot += amount;
      // 廣播給所有人：底池變了
      io.emit('update_state', gameState);
    }
  });

  socket.on('disconnect', () => {
    console.log('玩家斷線:', socket.id);
    delete gameState.players[socket.id];
    io.emit('update_state', gameState);
  });
});

const PORT = process.env.PORT || 3001;
server.listen(PORT, () => {
  console.log(`撲克伺服器正在運行，Port: ${PORT}`);
});
