"""复盘模块 + 路由经验知识库：离线勾稽、耗时统计、路由推荐；复盘写、业务读，弱依赖。"""
from __future__ import annotations
import json, math
from pathlib import Path
from . import frames, supervisor

KB_DIR = 'memory/knowledge'
HALF_LIFE_SEC = 7 * 86400
MAX_AGE_SEC = 90 * 86400
DEFAULT_TIMEOUT = 300

# ---- 知识库：写入（复盘产物）----

def _kb_dir(root):
    p = Path(root) / KB_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p

def record_duration(root, module, seconds):
    try:
        path = _kb_dir(root) / 'timings.json'
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        data.setdefault(module, []).append({'sec': seconds, 'ts': frames.now()})
        data[module] = data[module][-200:]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError:
        pass

def record_route(root, caller, callee, score, note=''):
    try:
        row = {'from': caller, 'to': callee, 'score': score,
               'ts': frames.now(), 'note': note}
        with (_kb_dir(root) / 'routes.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    except OSError:
        pass

# ---- 知识库：读取（监控阈值 + 业务推荐，弱依赖可降级）----

def _weight(ts):
    age = max(0.0, frames.now() - ts)
    return 0.0 if age > MAX_AGE_SEC else math.exp(-math.log(2) * age / HALF_LIFE_SEC)

def timeout_seconds(root, module):
    """监控判罚阈值：历史耗时加权 p75×1.5；样本不足用全局兜底。"""
    try:
        path = _kb_dir(root) / 'timings.json'
        if not path.exists():
            return DEFAULT_TIMEOUT
        data = json.loads(path.read_text(encoding='utf-8'))
        samples = [r['sec'] * _weight(r['ts']) for r in data.get(module, [])
                   if _weight(r['ts']) > 0]
        if len(samples) < 3:
            return DEFAULT_TIMEOUT
        samples.sort()
        return max(1.0, samples[int(len(samples) * 0.75)] * 1.5)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_TIMEOUT

def recommend(root, caller, limit=5):
    """路由推荐：按时效加权降序，仅供参考可忽略；库缺席返回空。"""
    try:
        path = _kb_dir(root) / 'routes.jsonl'
        if not path.exists():
            return []
        agg = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get('from') != caller:
                continue
            w = _weight(r.get('ts', 0))
            if w > 0:
                agg[r['to']] = agg.get(r['to'], 0.0) + r.get('score', 0) * w
        return [{'to': k, 'weight': round(v, 4)} for k, v in
                sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]]
    except OSError:
        return []

# ---- 复盘：离线勾稽 ----

def audit_run(root, run_id):
    """对已结束运行复盘：父子帧勾稽、定位解决者、经验入库。不碰运行中任务。"""
    fs = frames.frames_of_run(root, run_id)
    findings = []
    for f in fs:
        if f.get('startedAt') and f.get('finishedAt'):
            record_duration(root, f['module'], f['finishedAt'] - f['startedAt'])
        if f.get('parentId'):
            parent = frames.get_frame(root, f['parentId'])
            if parent is None:
                findings.append({'type': 'orphan_frame', 'frameId': f['frameId']})
            elif f['status'] in frames.STATUS_FINAL and f.get('answer') is None:
                findings.append({'type': 'missing_answer', 'frameId': f['frameId']})
            if parent and f['status'] == 'done':
                record_route(root, parent['module'], f['module'], 1.0, 'answered_ok')
    solved = sorted({f['module'] for f in fs
                     if f['status'] == 'done' and f.get('answer')})
    report = {'runId': run_id, 'at': frames.now(), 'frames': len(fs),
              'solvedBy': solved, 'anomalies': supervisor.anomalies(root, run_id),
              'findings': findings, 'balanced': not findings}
    out = Path(root) / 'work' / 'runs' / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / 'audit.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report
