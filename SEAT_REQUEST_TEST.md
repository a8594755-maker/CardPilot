# 座位請求功能測試指南

## 功能說明

- **房主**：創建房間的人自動成為房主
- **座位請求**：非房主玩家需要房主批准才能入座
- **房主控制面板**：顯示所有待處理的座位請求

## 測試步驟

### 1. 創建房間（成為房主）

1. 打開瀏覽器開發者工具（F12）查看 Console
2. 在大廳點擊 "Create Room"
3. 設定盲注、買入範圍
4. 選擇 Public 或 Private
5. 點擊 "Create Room"
6. **檢查控制台**：應該看到 `[OWNERSHIP] isHost: true`

### 2. 第二個玩家加入（測試座位請求）

1. 打開**無痕模式**或另一個瀏覽器
2. 輸入房間代碼加入房間
3. 點擊任意空座位
4. 選擇買入金額
5. 點擊 "Request Seat"
6. **檢查控制台**：
   - 玩家端：`Seat request sent for seat #X`
   - 房主端：`[SEAT_REQUEST] Received pending request`

### 3. 房主批准座位請求

1. 在房主的瀏覽器中
2. **查看控制欄**：應該顯示 "🎫 1 Request"（閃爍動畫）
3. **查看桌面上方**：應該出現綠色的座位請求面板
4. 點擊 "✓ Approve" 批准
5. 玩家應該成功入座

## 調試檢查點

### 控制台日誌（房主端）

```
[OWNERSHIP] isHost: true ownerId: guest-xxx userId: guest-xxx
[SEAT_REQUESTS] Current requests: 1 [{orderId: "req_xxx", ...}]
[SEAT_REQUESTS] isHostOrCoHost: true isHost: true isCoHost: false
```

### 控制台日誌（玩家端）

```
[SEAT_REQUEST] Received pending request: {orderId: "req_xxx", ...}
```

### 服務器日誌

```
[SEAT_REQUEST] Received from guest-xxx
[SEAT_REQUEST] Room found, owner: guest-yyy
[SEAT_REQUEST] Stored request: req_xxx
[SEAT_REQUEST] Found 1 host/co-host bindings
[SEAT_REQUEST] Notifying host socket: xxx
```

## 常見問題

### Q: 看不到座位請求面板

**檢查：**

1. 確認你是房主（控制欄顯示 👑 Host）
2. 打開控制台查看 `[SEAT_REQUESTS]` 日誌
3. 確認 `seatRequests.length > 0`
4. 確認 `isHostOrCoHost: true`

### Q: 房主身份不正確

**檢查：**

1. 控制台查看 `[OWNERSHIP]` 日誌
2. 確認 `ownerId` 和 `userId` 相同
3. 重新創建房間測試

### Q: 座位請求沒有發送

**檢查：**

1. 確認不是房主（房主可以直接入座）
2. 查看控制台是否有錯誤信息
3. 檢查買入金額是否在允許範圍內

## 視覺提示

### 房主控制欄

- 顯示 "👑 Host" 標記
- 有請求時：顯示 "🎫 1 Request"（閃爍）
- 無請求時：顯示 "No requests"

### 座位請求面板

- 位置：桌面上方
- 樣式：綠色邊框，閃爍動畫
- 內容：玩家名稱、座位號、買入金額
- 按鈕：✓ Approve（綠色）、✗ Reject（紅色）
