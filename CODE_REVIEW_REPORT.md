# CardPilot Code Review Report

> 封版與最終交付請優先參考 `docs/RELEASE_HANDOFF.md`。本文件保留為原始 code review 修復紀錄。

更新日期: 2026-03-18

## 1. 本次已修復

### 區塊 A: `packages/poker-evaluator`

- `packages/poker-evaluator/src/card-utils.ts`
  - 問題: `normalizeHand()` 後方註解文字被破壞，直接吃掉函式結尾，導致 TypeScript 語法錯誤。
  - 影響: `@cardpilot/poker-evaluator`、`@cardpilot/advice-engine`、`@cardpilot/cfr-solver`、`@cardpilot/game-server`、`@cardpilot/bot-client` 全部跟著 typecheck 失敗。
  - 修正:
    - 重建整個 `card-utils.ts` 為可編譯版本。
    - 補回 `normalizeHand()` 正常回傳。
    - `createShuffledDeck()` 改成從 `FULL_DECK` 複製，不再每次重新建 52 張牌。
  - 預防:
    - 不要把註解直接插進函式主體中間。
    - 做效能優化時，先跑 `npm run typecheck`，避免「優化成功但檔案已壞」。

### 區塊 B: `apps/web`

- `apps/web/src/hooks/useGameSocketEvents.ts`
  - 問題: setter 型別被寫成「只接受值」，但實際用法有大量 `setState(prev => ...)` updater callback。
  - 影響: `npm run build:web` 失敗，雖然 `typecheck` 一度沒有攔住，但正式 build 直接中斷。
  - 修正:
    - 改成 `Dispatch<SetStateAction<T>>`。
    - 清掉 hook 內已經沒用的 imports、helper、參數。
    - 移除沒有實際作用的多餘 prop 傳遞。
  - 預防:
    - 抽 React hook 時，setter 一律先用 `Dispatch<SetStateAction<T>>`。
    - 只要 hook 內有 `prev => ...`，就不能把 setter 型別寫成 `(value: T) => void`。

- `apps/web/src/contexts/GameContext.tsx`
  - 問題: `preAction` state 只保留 setter，value 本身沒有被任何地方讀取，形成冗餘狀態。
  - 修正:
    - 將狀態型別補正為 `PreAction | null`。
    - 保留 setter，移除未使用 state value 對 lint 的干擾。
  - 預防:
    - 如果 context 只需要 setter，不要把未使用的 state value 留成具名變數。

### 區塊 C: Repo Hygiene

- 根目錄 `echo`
  - 問題: 明顯是命令輸出殘留檔，不屬於專案代碼。
  - 修正: 已移除。

- 根目錄 `EXIT CODE `
  - 問題: 也是命令輸出殘留檔，檔名含特殊字元與尾端空白。
  - 狀態: 尚未透過 patch 流程安全刪除。
  - 建議: 後續以檔案總管或手動 shell 清除一次。

- `_test-compile.ts`
  - 問題: 有無用 import，造成 root lint warning。
  - 修正: 已移除無用 import。

## 2. 驗證結果

已通過:

- `npm run typecheck`
- `npm run test`
- `npm run build:web`
- `npm run build:server`

目前未完全通過:

- `npm run lint`
  - 結果: `0 errors`, `195 warnings`
  - 性質: 目前主要是 unused imports / unused params / unused locals，屬於技術債，不是 build blocker

## 3. 剩餘問題分區

### 區塊 A: `apps/web`

- `apps/web/src/App.tsx`
  - 問題類型: 單檔過大、未使用 state / imports 偏多、可維護性低。
  - 風險: 之後再抽 context / hooks 時，很容易再出現型別漂移。

- `apps/web/src/components/TableContainer.tsx`
  - 問題類型: 新抽出的容器有未使用變數。

- `apps/web/src/pages/solver/*`
  - 問題類型: 多個元件存在未使用 props / locals。

### 區塊 B: `apps/game-server`

- `apps/game-server/src/server.ts`
  - 問題類型: 未使用 type / local 過多，檔案過大。

- `apps/game-server/src/services/fast-battle-pool.ts`
  - 問題類型: 未使用 payload / constant，且輪詢式等待邏輯仍偏重。

### 區塊 C: `packages/cfr-solver`

- 問題集中在 CLI、pipeline、vectorized solver 腳本。
- 主要是未使用 helper / debug 變數殘留。
- 這一塊 warning 數量最多，適合單獨開一輪「solver 清潔」。

### 區塊 D: 其他 packages

- `packages/advice-engine`
  - 以未使用參數、暫存變數為主。

- `packages/shared-types`
  - 少量未使用 type import。

- `packages/poker-evaluator`
  - 目前只剩極少量 lint warning，阻塞已解除。

## 4. 下一輪建議順序

1. 先清 `apps/web/src/App.tsx` 與 `apps/web/src/components/TableContainer.tsx`
2. 再清 `apps/game-server/src/server.ts` 與 `apps/game-server/src/services/fast-battle-pool.ts`
3. 最後單獨整理 `packages/cfr-solver` 的 CLI / script warning

## 5. 防再錯規則

- React setter 型別不要手寫成普通函式，直接用 `Dispatch<SetStateAction<T>>`
- 抽 hook / context 後，立刻跑 `typecheck + build`
- 做效能優化前後都跑一次 `typecheck`
- 無用 state、無用 import、無用 helper 不要先留著「晚點再清」
- 根目錄不要保留命令輸出檔，避免污染 review 結果
