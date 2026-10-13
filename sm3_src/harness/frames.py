"""持久化调用栈：帧 schema（即模块间传参契约）+ 落盘读写，系统唯一权威记录。"""
from __future__ import annotations
import json, time, uuid
from pathlib import Path

STACK_DIR = 'work/stacks'

# ---- 传参契约（契约即帧结构，一处定义）----

STATUS_OPEN = ('pending', 'running', 'suspended', 'ready')
STATUS_FINAL = ('done', 'failed', 'timed_out')

def new_id():
    return uuid.uuid4().hex

def now():
    return time.time()

def make_trace(run_id, frame_id, parent_id):
    return {'runId': run_id, 'frameId': frame_id, 'parentId': parent_id,
            'requestId': new_id()}

def make_response(status, answer=None, elapsed_ms=0, llm_used=False):
    """标准应答结构：{status, answer, metrics}。"""
    return {'status': status, 'answer': answer or {},
            'metrics': {'elapsedMs': int(elapsed_ms), 'llmUsed': bool(llm_used)}}

# ---- 帧存储 ----

def stack_dir(root):
    p = Path(root) / STACK_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p

def frame_path(root, frame_id):
    return stack_dir(root) / f'{frame_id}.json'

def create_frame(root, module, payload, run_id, parent_id=None, state=None):
    frame = {
        'frameId': new_id(), 'runId': run_id, 'parentId': parent_id,
        'module': module, 'kind': 'initial', 'status': 'pending',
        'input': payload, 'state': state or {}, 'answer': None,
        'startedAt': None, 'finishedAt': None, 'heartbeatAt': None,
        'events': [],
    }
    save_frame(root, frame)
    return frame

def save_frame(root, frame):
    frame_path(root, frame['frameId']).write_text(
        json.dumps(frame, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return frame

def get_frame(root, frame_id):
    if not frame_id:
        return None
    p = frame_path(root, frame_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None

def frames_of_run(root, run_id):
    out = []
    for f in all_frames(root):
        if f.get('runId') == run_id:
            out.append(f)
    return out

def all_frames(root):
    out = []
    for p in stack_dir(root).glob('*.json'):
        try:
            out.append(json.loads(p.read_text(encoding='utf-8')))
        except json.JSONDecodeError:
            continue
    return out

def heartbeat(root, frame):
    frame['heartbeatAt'] = now()
    save_frame(root, frame)

def record_event(root, frame, kind, detail=None):
    frame['events'].append({'kind': kind, 'at': now(), 'detail': detail or {}})
    save_frame(root, frame)
