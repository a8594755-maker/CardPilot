"""
Export trained SD-CFR models to ONNX or JSON format for deployment.

Usage:
  # Export to ONNX (recommended for production)
  python -m scripts.deep_cfr.export --checkpoint checkpoints/sdcfr/sdcfr_iter200.pt --format onnx

  # Export to JSON (compatible with existing CardPilot MLP loader)
  python -m scripts.deep_cfr.export --checkpoint checkpoints/sdcfr/sdcfr_iter200.pt --format json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn

from .networks import AdvantageNetwork, LeducAdvantageNetwork, StrategyBuffer


def export_onnx(
    checkpoint_path: str,
    output_path: str,
    player: int = 0,
    device: str = 'cpu',
) -> None:
    """
    Export the weighted-average network to ONNX format.
    The ONNX model takes (raw_features, legal_mask) and outputs advantages.
    """
    import onnx

    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    game = ckpt.get('game', 'leduc')
    is_leduc = game == 'leduc'

    if is_leduc:
        net = LeducAdvantageNetwork(max_actions=4)
        raw_dim = 25
        max_actions = 4
    else:
        net = AdvantageNetwork(max_actions=6)
        raw_dim = 56
        max_actions = 6

    # Reconstruct strategy buffer and compute average
    sb = StrategyBuffer()
    sb.networks = list(ckpt[f'strategy_buffer_{player}'])
    avg_dict = sb.average_strategy(net)
    net.load_state_dict(avg_dict)
    net.eval()

    # Dummy inputs
    dummy_features = torch.randn(1, raw_dim)
    dummy_mask = torch.ones(1, max_actions)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    torch.onnx.export(
        net,
        (dummy_features, dummy_mask),
        output_path,
        input_names=['raw_features', 'legal_mask'],
        output_names=['advantages'],
        dynamic_axes={
            'raw_features': {0: 'batch'},
            'legal_mask': {0: 'batch'},
            'advantages': {0: 'batch'},
        },
        opset_version=17,
    )

    # Verify
    model = onnx.load(output_path)
    onnx.checker.check_model(model)
    file_size = os.path.getsize(output_path)
    print(f"ONNX model exported: {output_path} ({file_size / 1024:.1f} KB)")
    print(f"  Game: {game} | Player: {player}")
    print(f"  Input: raw_features ({raw_dim}D) + legal_mask ({max_actions}D)")
    print(f"  Output: advantages ({max_actions}D)")


def export_json(
    checkpoint_path: str,
    output_path: str,
    player: int = 0,
    device: str = 'cpu',
) -> None:
    """
    Export the weighted-average network to JSON format.
    Compatible with CardPilot's existing MLP weight loader (with embedding extensions).
    """
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    game = ckpt.get('game', 'leduc')
    is_leduc = game == 'leduc'

    if is_leduc:
        net = LeducAdvantageNetwork(max_actions=4)
    else:
        net = AdvantageNetwork(max_actions=6)

    sb = StrategyBuffer()
    sb.networks = list(ckpt[f'strategy_buffer_{player}'])
    avg_dict = sb.average_strategy(net)
    net.load_state_dict(avg_dict)
    net.eval()

    # Serialize all parameters
    model_data = {
        'game': game,
        'game_config': ckpt.get('game_config', 'unknown'),
        'player': player,
        'iterations': ckpt.get('iteration', 0) + 1,
        'architecture': 'LeducAdvantageNetwork' if is_leduc else 'AdvantageNetwork',
        'max_actions': net.max_actions,
        'layers': {},
    }

    for name, param in net.named_parameters():
        model_data['layers'][name] = {
            'shape': list(param.shape),
            'data': param.detach().cpu().numpy().tolist(),
        }

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(model_data, f)

    file_size = os.path.getsize(output_path)
    n_params = sum(p.numel() for p in net.parameters())
    print(f"JSON model exported: {output_path} ({file_size / (1024*1024):.2f} MB)")
    print(f"  Game: {game} | Player: {player}")
    print(f"  Parameters: {n_params:,}")
    print(f"  Layers: {len(model_data['layers'])}")


def export_strategy_buffer(
    checkpoint_path: str,
    output_dir: str,
    player: int = 0,
    device: str = 'cpu',
) -> None:
    """
    Export the entire strategy buffer (all network snapshots) as individual JSON files.
    Used for the theoretically correct SD-CFR sampling strategy at inference time.
    """
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    game = ckpt.get('game', 'leduc')
    is_leduc = game == 'leduc'

    if is_leduc:
        net = LeducAdvantageNetwork(max_actions=4)
    else:
        net = AdvantageNetwork(max_actions=6)

    sb_data = ckpt[f'strategy_buffer_{player}']
    os.makedirs(output_dir, exist_ok=True)

    manifest = {
        'game': game,
        'player': player,
        'n_networks': len(sb_data),
        'networks': [],
    }

    for i, (sd, weight) in enumerate(sb_data):
        filename = f'net_{i:04d}.pt'
        torch.save(sd, os.path.join(output_dir, filename))
        manifest['networks'].append({
            'file': filename,
            'weight': weight,
        })

    with open(os.path.join(output_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)

    total_size = sum(
        os.path.getsize(os.path.join(output_dir, f'net_{i:04d}.pt'))
        for i in range(len(sb_data))
    )
    print(f"Strategy buffer exported: {output_dir}")
    print(f"  Networks: {len(sb_data)} | Total: {total_size / (1024*1024):.1f} MB")
    print(f"  Manifest: {os.path.join(output_dir, 'manifest.json')}")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='Export SD-CFR models')
    parser.add_argument('--checkpoint', type=str, required=True)
    parser.add_argument('--format', type=str, default='onnx', choices=['onnx', 'json', 'buffer'])
    parser.add_argument('--output', type=str, default=None)
    parser.add_argument('--player', type=int, default=0, choices=[0, 1])
    parser.add_argument('--device', type=str, default='cpu')

    args = parser.parse_args()

    # Default output paths
    if args.output is None:
        base = os.path.splitext(os.path.basename(args.checkpoint))[0]
        if args.format == 'onnx':
            args.output = f'models/{base}_p{args.player}.onnx'
        elif args.format == 'json':
            args.output = f'models/{base}_p{args.player}.json'
        else:
            args.output = f'models/{base}_p{args.player}_buffer/'

    if args.format == 'onnx':
        export_onnx(args.checkpoint, args.output, args.player, args.device)
    elif args.format == 'json':
        export_json(args.checkpoint, args.output, args.player, args.device)
    elif args.format == 'buffer':
        export_strategy_buffer(args.checkpoint, args.output, args.player, args.device)


if __name__ == '__main__':
    main()
