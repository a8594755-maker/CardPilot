"""Phase 2 eval matrix — candidate × opponent benchmark orchestrator.

Each candidate is benched against each opponent in the suite. For Slumbot,
delegates to the existing `path_b_slumbot_bench.py`. For internal opponents
(non-Slumbot), runs in-process via vec_game_state (TODO: implemented in Day -2).

Outputs a single CSV matrix + per-cell JSON dump + summary MD report.

Usage:
  python eval_matrix.py \
    --candidates heuristic_v3 heuristic_v3_1 \
    --opponents slumbot fold call random scripted_aggro \
    --hands-quick 20400 \
    --hands-smoke 100 \
    --smoke \
    --out reports/phase2/eval_matrix/teacher_lock
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'alpha_holdem'))
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR / 'common'))
from manifest import write_manifest, write_md_report
from internal_bench import run_match as internal_run_match


VERSION = '0.1.0-skeleton'

SLUMBOT_BENCH_SCRIPT = REPO_ROOT / 'scripts' / 'alpha_holdem' / 'path_b_slumbot_bench.py'

# Opponents available in the suite (Day -3 skeleton: only Slumbot wired up)
SUITE = {
    'slumbot':           {'kind': 'slumbot'},
    # Internal opponents below — wiring deferred to Day -2 internal_bench.py
    'fold':              {'kind': 'internal', 'strategy': 'fold'},
    'call':              {'kind': 'internal', 'strategy': 'call'},
    'random':            {'kind': 'internal', 'strategy': 'random'},
    'heuristic_v3':      {'kind': 'internal', 'strategy': 'heuristic_v3'},
    'heuristic_v3_1':    {'kind': 'internal', 'strategy': 'heuristic_v3_1'},
    'pathb10m':          {'kind': 'internal', 'strategy': 'model', 'model_path': 'scripts/alpha_holdem/models/path_b_smoke_10M.pt'},
    'pathb50m':          {'kind': 'internal', 'strategy': 'model', 'model_path': 'scripts/alpha_holdem/models/path_b_smoke_50M.pt'},
    'v4_final':          {'kind': 'internal', 'strategy': 'model', 'model_path': 'models/alpha_holdem_v4_final.pt'},
    'scripted_aggro':    {'kind': 'internal', 'strategy': 'scripted_aggro'},          # TODO Day -2
    'scripted_station':  {'kind': 'internal', 'strategy': 'scripted_station'},        # TODO Day -2
    'scripted_jammer':   {'kind': 'internal', 'strategy': 'scripted_jammer'},         # TODO Day -2
    'slumbot_proxy':     {'kind': 'internal', 'strategy': 'slumbot_proxy'},           # TODO Day -1
}


def bench_vs_slumbot(candidate: str, *, n_sessions: int, hands_per_session: int,
                     out_dir: Path, tag: str, dump: bool = False) -> dict:
    """Delegate to path_b_slumbot_bench.py and parse its summary file."""
    cmd = [
        sys.executable, '-X', 'utf8', '-u',
        str(SLUMBOT_BENCH_SCRIPT),
        '--strategy', candidate if not candidate.endswith('.pt') else 'model',
        '--sessions', str(n_sessions),
        '--hands-per-session', str(hands_per_session),
        '--tag', tag,
        '--out-dir', str(out_dir),
        '--device', 'cpu',
    ]
    if candidate.endswith('.pt'):
        cmd.extend(['--model', candidate])
    if dump:
        cmd.append('--dump-slumbot')
    print(f'[bench Slumbot] {candidate} {n_sessions}x{hands_per_session}')
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace')
    elapsed = time.time() - t0
    summary_path = out_dir / f'{tag}_summary.txt'
    if not summary_path.exists():
        return {'error': 'no summary file', 'stderr': proc.stderr[-2000:], 'elapsed_s': elapsed}
    # Parse: hands=X / bb100=X / ci_bb100_rough=±X
    parsed = {'elapsed_s': elapsed}
    for line in summary_path.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            k, _, v = line.partition('=')
            parsed[k.strip()] = v.strip()
    return parsed


def bench_vs_internal(candidate: str, opponent: str, *, n_hands: int,
                      out_dir: Path, tag: str, seed: int = 42,
                      parallel_games: int = 256) -> dict:
    """Internal in-process bench using vec_game_state via internal_bench.run_match."""
    print(f'[bench internal] {candidate} vs {opponent} ({n_hands} hands)')
    result = internal_run_match(candidate, opponent, n_hands,
                                 seed=seed, parallel_games=parallel_games)
    # Mirror the slumbot result shape so downstream CSV/MD works uniformly.
    flat = {
        'bb100': f'{result["bb100"]:+.2f}',
        'sb_bb100': f'{result["sb_bb100"]:+.2f}',
        'bb_bb100': f'{result["bb_bb100"]:+.2f}',
        'ci_bb100_rough': f'+/-{result["ci_bb100"]:.1f}',
        'hands': result['n_hands'],
        'elapsed_s': result['elapsed_s'],
        'opponent_kind': 'internal',
        'full_result_json': str(out_dir / f'{tag}_full.json'),
    }
    # Persist full result
    (out_dir / f'{tag}_full.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return flat


def _candidate_display_name(cand: str) -> str:
    """Generate a filesystem-safe short display name from a candidate string."""
    if cand.endswith('.pt'):
        return Path(cand).stem
    return cand.replace(':', '_').replace('/', '_').replace('\\', '_')


def _candidate_internal_name(cand: str) -> str:
    """Convert a candidate identifier to the form get_policy() understands.

    A bare .pt path needs `anchor:` prefix so frozen_anchor.load_frozen_anchor_callable
    is invoked. Built-in strategy names pass through unchanged.
    """
    if cand.endswith('.pt'):
        return f'anchor:{cand}'
    return cand


def run_matrix(candidates: list[str], opponents: list[str], *,
               hands_quick: int, hands_smoke: int, smoke: bool,
               out_dir: Path, dump: bool) -> dict:
    """Returns a nested dict: matrix[candidate][opponent] = bench_result."""
    matrix = {}
    for cand in candidates:
        disp = _candidate_display_name(cand)
        matrix[disp] = {}
        for opp in opponents:
            if opp not in SUITE:
                matrix[disp][opp] = {'error': f'unknown opponent {opp}'}
                continue
            kind = SUITE[opp]['kind']
            tag = f'{disp}_vs_{opp}'
            if kind == 'slumbot':
                n_sessions = 4 if smoke else 12
                hpsess = hands_smoke // n_sessions if smoke else hands_quick // n_sessions
                hpsess = max(hpsess, 25)
                cell_dir = out_dir / 'cells' / tag
                cell_dir.mkdir(parents=True, exist_ok=True)
                # For Slumbot, pass the raw candidate (path or strategy name)
                result = bench_vs_slumbot(cand, n_sessions=n_sessions,
                                          hands_per_session=hpsess,
                                          out_dir=cell_dir, tag=tag, dump=dump)
            else:
                cell_dir = out_dir / 'cells' / tag
                cell_dir.mkdir(parents=True, exist_ok=True)
                n_h = 1000 if smoke else 20400
                internal_name = _candidate_internal_name(cand)
                result = bench_vs_internal(internal_name, opp, n_hands=n_h,
                                            out_dir=cell_dir, tag=tag,
                                            parallel_games=128)
            matrix[disp][opp] = result
            print(f'  {disp} vs {opp}: {result.get("bb100", result.get("status", "?"))}')
    return matrix


def to_csv(matrix: dict, out_path: Path):
    """Write candidate × opponent bb100 matrix as CSV."""
    if not matrix:
        return
    opponents = sorted({o for cand in matrix.values() for o in cand.keys()})
    lines = ['candidate,' + ','.join(opponents)]
    for cand, row in matrix.items():
        cells = []
        for opp in opponents:
            r = row.get(opp, {})
            cells.append(str(r.get('bb100', r.get('status', 'NA'))))
        lines.append(f'{cand},' + ','.join(cells))
    out_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--candidates', nargs='+', required=True,
                   help='Strategy names (heuristic_v3, etc) or .pt paths')
    p.add_argument('--opponents', nargs='+', required=True,
                   help=f'Suite members: {list(SUITE.keys())}')
    p.add_argument('--hands-quick', type=int, default=20400)
    p.add_argument('--hands-smoke', type=int, default=100)
    p.add_argument('--smoke', action='store_true', help='Use hands-smoke; tiny bench for skeleton validation')
    p.add_argument('--dump', action='store_true', help='--dump-slumbot for Slumbot benches')
    p.add_argument('--out', required=True, help='Output directory for matrix.csv + manifest.json + report.md')
    p.add_argument('--seed', type=int, default=137)
    args = p.parse_args()

    out_dir = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    matrix = run_matrix(args.candidates, args.opponents,
                        hands_quick=args.hands_quick, hands_smoke=args.hands_smoke,
                        smoke=args.smoke, out_dir=out_dir, dump=args.dump)
    elapsed = time.time() - t0

    csv_path = out_dir / 'matrix.csv'
    to_csv(matrix, csv_path)

    json_path = out_dir / 'matrix.json'
    json_path.write_text(json.dumps(matrix, indent=2), encoding='utf-8')

    write_manifest(out_dir / 'manifest.json',
                   script='phase2/eval_matrix.py', version=VERSION,
                   args=vars(args), seed=args.seed,
                   outputs=[csv_path, json_path],
                   extra={'elapsed_s': elapsed,
                          'n_candidates': len(args.candidates),
                          'n_opponents': len(args.opponents)})

    md_lines = []
    md_lines.append(f'Candidates: {", ".join(args.candidates)}')
    md_lines.append(f'Opponents:  {", ".join(args.opponents)}')
    md_lines.append(f'Mode:       {"smoke ("+str(args.hands_smoke)+" hands)" if args.smoke else "quick ("+str(args.hands_quick)+" hands)"}')
    md_lines.append(f'Elapsed:    {elapsed:.1f}s')
    md_lines.append('')
    md_lines.append('## Matrix (bb/100)')
    md_lines.append('')
    md_lines.append('See `matrix.csv` for full data. Per-cell JSON in `cells/<cand>_vs_<opp>/`.')

    write_md_report(out_dir / 'report.md',
                    title=f'Phase 2 eval matrix ({"smoke" if args.smoke else "quick"})',
                    sections=[('Configuration', '\n'.join(md_lines))])

    print(f'\n[OK] Matrix written to {out_dir}')
    print(f'  CSV:      {csv_path}')
    print(f'  JSON:     {json_path}')
    print(f'  Report:   {out_dir / "report.md"}')
    print(f'  Manifest: {out_dir / "manifest.json"}')


if __name__ == '__main__':
    main()
