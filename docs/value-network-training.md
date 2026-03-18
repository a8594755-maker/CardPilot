# Value Network 訓練指南

## 概述

訓練一個神經網路來預測撲克牌局在 street boundary（flop→turn, turn→river）的 per-hand-class EV，用於替代 heuristic estimator 做 depth-limited solving。

- **模型**：ValueNetwork（PyTorch → ONNX）
- **輸入**：board cards + pot/stacks + reaches（169 hand classes）
- **輸出**：每個 hand class 的預測 EV
- **數據**：由 CFR solver 生成的 1.57M transition records（23.6GB）

---

## 步驟一：環境準備

### 系統需求

| 項目     | 最低需求            | 建議                       |
| -------- | ------------------- | -------------------------- |
| OS       | Windows/Linux/macOS | Linux                      |
| Python   | 3.10+               | 3.12                       |
| GPU      | CUDA GPU（任意）    | RTX 3090/4090（24GB VRAM） |
| RAM      | 48GB                | 64GB                       |
| 磁碟空間 | 30GB（數據+模型）   | 50GB                       |

> **RAM 不足 48GB？** 訓練時加 `--max-samples 500000`，只用 1/3 數據（~16GB RAM）

### 安裝 Python 依賴

```bash
# 建立虛擬環境（推薦）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安裝 PyTorch（CUDA 12.6）
pip install torch --index-url https://download.pytorch.org/whl/cu126

# 安裝 ONNX（模型匯出用）
pip install onnx

# 驗證 CUDA
python -c "import torch; print(f'PyTorch {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

如果你的 CUDA 版本不是 12.6，去 https://pytorch.org/get-started/locally/ 選對應版本。

---

## 步驟二：取得程式碼和數據

### 程式碼

```bash
git clone https://github.com/a8594755-maker/EZ-GTO.git
cd EZ-GTO
```

訓練相關檔案在 `tools/coaching/` 目錄：

```
tools/coaching/
├── train_value_network.py   # 主訓練腳本
├── value_dataset.py         # 數據讀取 & 預處理
└── value_network.py         # 模型架構定義
```

### 數據

把以下 16 個 .bin 檔案複製到電腦上的任意位置（例如 `~/data/value-net/`）：

```
r00.bin  r01.bin  r02.bin  r03.bin
r04.bin  r05.bin  r06.bin  r07.bin
r08.bin  r09.bin  r10.bin  r11.bin
r12.bin  r13.bin  r14.bin  r15.bin
```

- 每個檔案約 1.5GB
- 總計 23.6GB
- 共 1,566,414 筆 transition records
- 格式：VNET binary（flop→turn 10,560 筆 + turn→river 1,555,854 筆）
- 來源位置（原始機器）：`D:\EZ-GTO-data\value-net\`

---

## 步驟三：開始訓練

```bash
cd EZ-GTO/tools/coaching

# 完整訓練（需 48GB+ RAM）
PYTHONUNBUFFERED=1 python train_value_network.py \
  --input ~/data/value-net/r00.bin \
          ~/data/value-net/r01.bin \
          ~/data/value-net/r02.bin \
          ~/data/value-net/r03.bin \
          ~/data/value-net/r04.bin \
          ~/data/value-net/r05.bin \
          ~/data/value-net/r06.bin \
          ~/data/value-net/r07.bin \
          ~/data/value-net/r08.bin \
          ~/data/value-net/r09.bin \
          ~/data/value-net/r10.bin \
          ~/data/value-net/r11.bin \
          ~/data/value-net/r12.bin \
          ~/data/value-net/r13.bin \
          ~/data/value-net/r14.bin \
          ~/data/value-net/r15.bin \
  --out ~/data/value_network_v1.onnx \
  --checkpoint-dir ~/data/checkpoints/ \
  --epochs 30 \
  --batch-size 2048 \
  --amp

# 如果 RAM 不足，限制樣本數
# 加上：--max-samples 500000
```

### Windows 版本

```powershell
cd EZ-GTO\tools\coaching

$env:PYTHONUNBUFFERED=1
python train_value_network.py `
  --input D:\data\value-net\r00.bin D:\data\value-net\r01.bin D:\data\value-net\r02.bin D:\data\value-net\r03.bin D:\data\value-net\r04.bin D:\data\value-net\r05.bin D:\data\value-net\r06.bin D:\data\value-net\r07.bin D:\data\value-net\r08.bin D:\data\value-net\r09.bin D:\data\value-net\r10.bin D:\data\value-net\r11.bin D:\data\value-net\r12.bin D:\data\value-net\r13.bin D:\data\value-net\r14.bin D:\data\value-net\r15.bin `
  --out D:\data\value_network_v1.onnx `
  --checkpoint-dir D:\data\checkpoints `
  --epochs 30 --batch-size 2048 --amp
```

---

## 參數說明

| 參數               | 預設值                  | 說明                                 |
| ------------------ | ----------------------- | ------------------------------------ |
| `--input`          | (必填)                  | .bin 數據檔路徑（可多個）            |
| `--out`            | `value_network_v1.onnx` | 輸出 ONNX 模型路徑                   |
| `--epochs`         | 30                      | 訓練回合數                           |
| `--batch-size`     | 2048                    | 批次大小（GPU VRAM 不夠就降到 1024） |
| `--lr`             | 3e-4                    | 學習率                               |
| `--weight-decay`   | 1e-4                    | L2 正則化                            |
| `--dropout`        | 0.1                     | Dropout 比率                         |
| `--trunk-dim`      | 1024                    | 模型 trunk 寬度                      |
| `--amp`            | off                     | 啟用混合精度訓練（推薦，更快）       |
| `--patience`       | 5                       | Early stopping 耐心值                |
| `--val-ratio`      | 0.1                     | 驗證集比例                           |
| `--max-samples`    | 0 (全部)                | 限制載入筆數（RAM 不夠時用）         |
| `--checkpoint-dir` | `checkpoints/`          | checkpoint 儲存位置                  |
| `--grad-clip`      | 1.0                     | 梯度裁剪                             |
| `--seed`           | 42                      | 隨機種子                             |

---

## 預期輸出

### 訓練過程

```
Device: cuda
Loading r00.bin... 97680 records
Loading r01.bin... 97672 records
...
Total raw records: 1566414
Aggregated: 1566414 samples (F→T: 10560, T→R: 1555854)

Model: ValueNetwork (xxx parameters)
Train: 1409772 samples, Val: 156642 samples

Epoch  1/30 | Train Loss: 0.xxxx | Val Loss: 0.xxxx | Time: xxxs
Epoch  2/30 | Train Loss: 0.xxxx | Val Loss: 0.xxxx | Time: xxxs
...
```

### 輸出檔案

- `value_network_v1.onnx` — 最終 ONNX 模型（用於推理）
- `checkpoints/best_model.pt` — 最佳 PyTorch checkpoint
- `checkpoints/epoch_XX.pt` — 每個 epoch 的 checkpoint

---

## 訓練完成後

把 `value_network_v1.onnx` 複製回主機：

```
C:\Users\a8594\EZ-GTO\EZ-GTO\data\nn-training\value_network_v1.onnx
```

這個模型會被 `value-network-runtime.ts` 載入，用於 CFR solver 的 depth-limited evaluation。

---

## 疑難排解

| 問題                            | 解法                                                     |
| ------------------------------- | -------------------------------------------------------- |
| `CUDA out of memory`            | 降低 `--batch-size`（1024 或 512）                       |
| `Killed`（Linux OOM）           | 加 `--max-samples 500000`                                |
| `JavaScript heap out of memory` | 這是 data generation 的問題，不影響 Python 訓練          |
| PyTorch 找不到 CUDA             | 確認 `nvidia-smi` 有輸出，PyTorch 版本對應 CUDA 版本     |
| 模型不收斂                      | 檢查數據是否完整（每檔 ~97K records），試降低 lr 到 1e-4 |
