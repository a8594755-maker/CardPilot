"""
export_onnx.py

Load a trained RiverEVNet checkpoint and export to ONNX for TypeScript inference
via onnxruntime-node / onnxruntime-web.

The exported model accepts 4 separate float32 inputs (matching the TypeScript
wasm-cfr-bridge.ts NNRiverValueFn interface) and returns two normalised CFV arrays.
The caller must multiply outputs by effectiveStack to restore chip values.

Usage:
    python export_onnx.py \
        --checkpoint checkpoints/river_ev_v1/best_model.pt \
        --output models/river_ev_v1.onnx \
        --validate

Inputs  (dynamic batch size B):
    board_onehot  (B, 208)   float32 — 4 cards × 52-dim one-hot
    pot_features  (B,   3)   float32 — [potOffset/es, startingPot/es, es/200]
    oop_reach     (B, 1326)  float32 — OOP reach probabilities
    ip_reach      (B, 1326)  float32 — IP reach probabilities

Outputs:
    cfv_oop_norm  (B, 1326)  float32 — OOP CFV / effectiveStack
    cfv_ip_norm   (B, 1326)  float32 — IP CFV / effectiveStack
"""

import sys
import os
import argparse
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

# ── Import model from sibling training script ────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_river_ev import RiverEVNet, NUM_COMBOS  # type: ignore


# ─── ONNX export wrapper ─────────────────────────────────────────────────────

class ONNXExportWrapper(nn.Module):
    """
    Wraps RiverEVNet to accept 4 separate tensors instead of a pre-concatenated
    input. This matches what the TypeScript bridge will construct at runtime.
    """

    def __init__(self, net: RiverEVNet):
        super().__init__()
        self.net = net

    def forward(
        self,
        board_onehot: torch.Tensor,   # (B, 208)
        pot_features: torch.Tensor,   # (B, 3)
        oop_reach:    torch.Tensor,   # (B, 1326)
        ip_reach:     torch.Tensor,   # (B, 1326)
    ):
        x   = torch.cat([board_onehot, pot_features, oop_reach, ip_reach], dim=1)
        out = self.net(x)
        cfv_oop_norm = out[:, :NUM_COMBOS]
        cfv_ip_norm  = out[:, NUM_COMBOS:]
        return cfv_oop_norm, cfv_ip_norm


# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_model_from_checkpoint(checkpoint_path: str, device: torch.device) -> RiverEVNet:
    """Load model weights and architecture config from a saved checkpoint."""
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    cfg  = ckpt["config"]
    model = RiverEVNet(
        hidden_dim=cfg["hidden_dim"],
        num_blocks=cfg["num_blocks"],
        input_dim=cfg.get("input_dim",  2863),
        output_dim=cfg.get("output_dim", 2652),
    ).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    val_loss = ckpt.get("val_loss", float("nan"))
    epoch    = ckpt.get("epoch", "?")
    print(f"  Loaded checkpoint: epoch={epoch}, val_loss={val_loss:.6f}")
    print(f"  Architecture: hidden={cfg['hidden_dim']}, blocks={cfg['num_blocks']}, "
          f"params={model.num_parameters:,}")
    return model


def export_model(wrapper: ONNXExportWrapper, output_path: str, opset: int,
                 batch_size: int = 1) -> None:
    """Export to ONNX with dynamic batch size (uses legacy TorchScript path)."""
    # Move to CPU for export — avoids dynamo device-mismatch issues on CUDA
    cpu_wrapper = wrapper.cpu()
    cpu_wrapper.eval()

    B = batch_size
    dummy_board = torch.zeros(B, 208,        dtype=torch.float32)
    dummy_pot   = torch.zeros(B,   3,        dtype=torch.float32)
    dummy_oop   = torch.zeros(B, NUM_COMBOS, dtype=torch.float32)
    dummy_ip    = torch.zeros(B, NUM_COMBOS, dtype=torch.float32)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        cpu_wrapper,
        (dummy_board, dummy_pot, dummy_oop, dummy_ip),
        output_path,
        input_names=["board_onehot", "pot_features", "oop_reach", "ip_reach"],
        output_names=["cfv_oop_norm", "cfv_ip_norm"],
        dynamic_axes={
            "board_onehot": {0: "batch_size"},
            "pot_features": {0: "batch_size"},
            "oop_reach":    {0: "batch_size"},
            "ip_reach":     {0: "batch_size"},
            "cfv_oop_norm": {0: "batch_size"},
            "cfv_ip_norm":  {0: "batch_size"},
        },
        opset_version=opset,
        do_constant_folding=True,
        dynamo=False,
        verbose=False,
    )
    size_mb = Path(output_path).stat().st_size / 1e6
    print(f"  Exported: {output_path}  ({size_mb:.1f} MB)")


def validate_onnx(onnx_path: str, wrapper: ONNXExportWrapper,
                  device: torch.device, n_samples: int = 4) -> bool:
    """
    Run a forward pass through both PyTorch and ONNX and compare outputs.
    Returns True if max absolute difference < 1e-4.
    """
    try:
        import onnxruntime as ort
    except ImportError:
        print("  Warning: onnxruntime not installed, skipping ONNX validation.")
        return True

    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if device.type == "cuda"
        else ["CPUExecutionProvider"]
    )
    sess = ort.InferenceSession(onnx_path, providers=providers)

    B = n_samples
    rng = np.random.default_rng(0)

    # Realistic-ish dummy inputs
    board_np = np.zeros((B, 208),      dtype=np.float32)
    for b in range(B):
        # place one-hot for 4 distinct cards
        cards = rng.choice(52, 4, replace=False)
        for i, c in enumerate(cards):
            board_np[b, i * 52 + c] = 1.0
    pot_np = np.array([[0.2, 0.5, 0.5]] * B, dtype=np.float32)  # normalised pot feats
    oop_np = (rng.random((B, NUM_COMBOS)).astype(np.float32) * 0.01).clip(0, 1)
    ip_np  = (rng.random((B, NUM_COMBOS)).astype(np.float32) * 0.01).clip(0, 1)

    # PyTorch reference — wrapper was moved to CPU in export_model(), use CPU here
    cpu = torch.device("cpu")
    wrapper.cpu()
    with torch.no_grad():
        pt_out = wrapper(
            torch.from_numpy(board_np),
            torch.from_numpy(pot_np),
            torch.from_numpy(oop_np),
            torch.from_numpy(ip_np),
        )
    pt_oop = pt_out[0].cpu().numpy()
    pt_ip  = pt_out[1].cpu().numpy()

    # ONNX
    ort_oop, ort_ip = sess.run(None, {
        "board_onehot": board_np,
        "pot_features": pot_np,
        "oop_reach":    oop_np,
        "ip_reach":     ip_np,
    })

    max_diff_oop = float(np.abs(pt_oop - ort_oop).max())
    max_diff_ip  = float(np.abs(pt_ip  - ort_ip).max())
    max_diff     = max(max_diff_oop, max_diff_ip)

    threshold = 1e-4
    ok = max_diff < threshold
    status = "PASS" if ok else "FAIL"
    print(f"  Validation [{status}]: max_abs_diff={max_diff:.2e} (threshold={threshold:.0e})")
    if not ok:
        print(f"    OOP diff: {max_diff_oop:.2e}  IP diff: {max_diff_ip:.2e}")
    return ok


# ─── Argument parsing ────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export trained RiverEVNet to ONNX",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--checkpoint", required=True,
                   help="Path to .pt checkpoint (e.g. checkpoints/river_ev_v1/best_model.pt)")
    p.add_argument("--output",     default="models/river_ev_v1.onnx",
                   help="Output .onnx file path")
    p.add_argument("--opset",      type=int, default=17,
                   help="ONNX opset version (17 recommended)")
    p.add_argument("--validate",   action="store_true",
                   help="Run numerical validation with onnxruntime after export")
    p.add_argument("--batch-size", type=int, default=1,
                   help="Dummy input batch size for tracing (does not affect dynamic axes)")
    return p.parse_args()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    args   = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    print(f"\nLoading model from: {args.checkpoint}")
    model   = load_model_from_checkpoint(args.checkpoint, device)
    wrapper = ONNXExportWrapper(model).to(device)
    wrapper.eval()

    # Verify ONNX package is available before exporting
    try:
        import onnx
        print(f"  onnx version: {onnx.__version__}")
    except ImportError:
        print("Error: 'onnx' package not installed. Run: pip install onnx>=1.15.0")
        sys.exit(1)

    print(f"\nExporting to ONNX (opset {args.opset}) ...")
    export_model(wrapper, args.output, args.opset, args.batch_size)

    # Optional ONNX graph check
    try:
        import onnx
        model_proto = onnx.load(args.output)
        onnx.checker.check_model(model_proto)
        print("  ONNX graph check: OK")
    except Exception as e:
        print(f"  ONNX graph check: WARN ({e})")

    if args.validate:
        print("\nValidating ONNX vs PyTorch ...")
        ok = validate_onnx(args.output, wrapper, device, n_samples=8)
        if not ok:
            print("  !! Validation failed - check AMP settings or opset compatibility")
            sys.exit(1)

    print(f"\nDone. Model saved to: {args.output}")
    print("\nTypeScript integration notes:")
    print("  Inputs:  board_onehot(B,208), pot_features(B,3), oop_reach(B,1326), ip_reach(B,1326)")
    print("  Outputs: cfv_oop_norm(B,1326), cfv_ip_norm(B,1326)")
    print("  Remember to multiply outputs by effectiveStack to get chip values.")


if __name__ == "__main__":
    main()
