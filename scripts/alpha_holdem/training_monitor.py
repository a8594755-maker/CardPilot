"""Read-only localhost progress dashboard; never starts or changes training."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import time
import psutil


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def status(base):
    process = read(base/'train10m/process.json')
    live = False
    try:
        live = abs(psutil.Process(process['pid']).create_time()-process['create_time']) < .1
    except (KeyError, psutil.Error):
        pass
    rows = []
    path = base/'training/h1_training_metrics.jsonl'
    if path.exists():
        with path.open('rb') as f:
            f.seek(max(0, path.stat().st_size-4_000_000))
            for line in f.read().splitlines(keepends=True):
                if line.endswith(b'\n'):
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    latest = rows[-1] if rows else {}
    hands = latest.get('environment_hand_accounting', {}).get('completed_hands', 0)
    now = time.time()
    last = datetime.fromisoformat(latest['recorded_at']).timestamp() if rows else None
    rate = None
    if len(rows) > 1:
        first = rows[max(0, len(rows)-21)]
        seconds = last-datetime.fromisoformat(first['recorded_at']).timestamp()
        if seconds > 0:
            rate = (hands-first['environment_hand_accounting']['completed_hands'])/seconds
    terminal = read(base/'train10m/terminal.json')
    result = read(base/'train10m/result.json')
    state = 'RUNNING' if live else 'STOPPED / inspect logs'
    if live and last and now-last > 600:
        state = 'RUNNING / metrics stale >10min'
    if terminal:
        state = 'FINALIZING' if terminal.get('exit_code') == 0 else 'FAILED'
    if result:
        state = 'COMPLETED'
        hands = result['physical_hands']
    remaining = max(0, 10_000_000-hands)/rate if rate and live else None
    checkpoint = base/'training/latest.pt'
    return dict(run=base.name, state=state, actual_hands=hands, target=10_000_000,
                percent=round(hands/100_000, 3), iteration=latest.get('iteration'),
                transition_hands=latest.get('hands'), physical_hands_per_second=rate,
                eta_utc=datetime.fromtimestamp(now+remaining, timezone.utc).isoformat() if remaining else None,
                remaining_hours=remaining/3600 if remaining else None,
                metrics_age_seconds=round(now-last) if last else None,
                checkpoint_saved_at=datetime.fromtimestamp(checkpoint.stat().st_mtime, timezone.utc).isoformat() if checkpoint.exists() else None,
                free_disk_gib=round(shutil.disk_usage(base).free/2**30, 2),
                pid=process.get('pid'), checked_at=datetime.now(timezone.utc).isoformat())


PAGE = '''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaHoldem training monitor</title><style>body{font:17px system-ui;max-width:850px;margin:40px auto;padding:0 20px;color:#e9eef5;background:#101820}h1{font-size:26px}progress{width:100%;height:25px}dl{display:grid;grid-template-columns:1fr 1fr;gap:14px}dd{margin:0;overflow-wrap:anywhere}small{color:#b6c6d8}#error{color:#ffa4a4}</style>
<h1>AlphaHoldem · 0 → 1,000 万手</h1><p id="run"></p><p id="state" aria-live="polite">读取中…</p><progress id="bar" max="10000000" value="0" aria-label="训练完成手数"></progress>
<dl id="data"></dl><p id="error"></p><small>每 10 秒刷新；手数在完整训练批次后更新。ETA 使用最近最多 20 个批次的实际手数/墙钟时间，不代表棋力提升；初期估计可能变化。此面板只读，不启动测试、不重启训练。电脑需保持开机且不休眠。</small>
<script>async function refresh(){try{const s=await(await fetch('/status',{cache:'no-store'})).json();document.getElementById('run').textContent=s.run;document.getElementById('state').textContent=s.state;document.getElementById('bar').value=s.actual_hands;const fields=[['实际完成手数',s.actual_hands.toLocaleString()+' / 10,000,000 ('+s.percent+'%)'],['实际速度',s.physical_hands_per_second?s.physical_hands_per_second.toFixed(1)+' 手/秒':'等待多个批次'],['预计结束（浏览器当地时间）',s.eta_utc?new Date(s.eta_utc).toLocaleString():'暂不可估计'],['预计剩余',s.remaining_hours?s.remaining_hours.toFixed(2)+' 小时':'—'],['迭代',s.iteration??'—'],['提供训练数据的手数',s.transition_hands?.toLocaleString()??'—'],['最近 checkpoint',s.checkpoint_saved_at?new Date(s.checkpoint_saved_at).toLocaleString():'尚未首次保存'],['日志距今',s.metrics_age_seconds===null?'—':s.metrics_age_seconds+' 秒'],['磁盘剩余',s.free_disk_gib+' GiB'],['训练 PID',s.pid??'—']];const el=document.getElementById('data');el.replaceChildren();for(const [k,v]of fields){let a=document.createElement('dt'),b=document.createElement('dd');a.textContent=k;b.textContent=v;el.append(a,b)}document.getElementById('error').textContent=''}catch(e){document.getElementById('error').textContent='无法刷新监控：'+e}}refresh();setInterval(refresh,10000);</script></html>'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--port', type=int, default=8766)
    args = p.parse_args()
    if not (args.run_dir/'contract.json').is_file():
        p.error('run contract missing')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/', '/status'):
                self.send_error(404)
                return
            payload = (json.dumps(status(args.run_dir)) if self.path == '/status' else PAGE).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json' if self.path == '/status' else 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    print(f'Monitor: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
