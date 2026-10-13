"""体外监控：只读帧的时间/心跳客观指标，超时输出判罚事件；绝不改写任务栈。"""
from __future__ import annotations
import json
from pathlib import Path
from . import frames, review

EVENT_DIR = 'work/events'

def _event_dir(root):
    p = Path(root) / EVENT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p

def scan(root):
    """扫描活动帧，超时输出判罚事件文件；不修改任何帧。"""
    verdicts, current = [], frames.now()
    for f in frames.all_frames(root):
        if f['status'] not in ('pending', 'running', 'suspended', 'ready'):
            continue
        if not f.get('startedAt'):
            continue
        threshold = review.timeout_seconds(root, f['module'])
        heartbeat_age = current - (f.get('heartbeatAt') or f['startedAt'])
        if current - f['startedAt'] > threshold or heartbeat_age > threshold:
            v = {'verdictId': frames.new_id(), 'type': 'timeout',
                 'frameId': f['frameId'], 'runId': f['runId'],
                 'module': f['module'], 'at': current,
                 'basis': {'startedAt': f['startedAt'], 'now': current,
                           'heartbeatAge': round(heartbeat_age, 2),
                           'threshold': threshold}}
            path = _event_dir(root) / f"verdict-{v['verdictId']}.json"
            path.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')
            verdicts.append(v)
    return verdicts

def pending_verdicts(root):
    out = []
    for p in _event_dir(root).glob('verdict-*.json'):
        try:
            v = json.loads(p.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if not v.get('consumedAt'):
            v['_path'] = str(p)
            out.append(v)
    return out

def mark_consumed(root, verdict):
    path = Path(verdict.pop('_path'))
    verdict['consumedAt'] = frames.now()
    path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')
