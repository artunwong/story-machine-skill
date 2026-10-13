"""监督模块：收集模块日志、组装只读调用栈视图、识别异常；严禁参与业务。"""
from __future__ import annotations
import json
from pathlib import Path
from . import frames

LOG_FILE = 'logs/supervisor.jsonl'

def log(root, frame_id, run_id, level, msg, **kv):
    path = Path(root) / LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {'ts': frames.now(), 'runId': run_id, 'frameId': frame_id,
           'level': level, 'msg': msg, **kv}
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')

def call_stack(root, run_id):
    """把落盘帧组装为树状调用栈视图（只读）。"""
    children, roots = {}, []
    for f in frames.frames_of_run(root, run_id):
        (children.setdefault(f['parentId'], []) if f.get('parentId') else roots).append(f)

    def node(f):
        return {'frameId': f['frameId'], 'module': f['module'], 'kind': f['kind'],
                'status': f['status'],
                'children': [node(c) for c in children.get(f['frameId'], [])]}
    return [node(r) for r in roots]

def anomalies(root, run_id):
    return [{'frameId': f['frameId'], 'module': f['module'], 'status': f['status']}
            for f in frames.frames_of_run(root, run_id)
            if f['status'] in ('failed', 'timed_out')]
