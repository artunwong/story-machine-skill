"""调度器（协议通道）：求助登记、步进驱动、断点重入、判罚消费——唯一允许写帧状态的机制组件。

本模块不选择下游、不解读业务内容；它只登记调用帧、传递应答、按帧恢复上下文。
"""
from __future__ import annotations
import importlib
from . import frames, supervisor, monitor, review

# 业务模块包名随顶层包推导：源码版 src.biz，skill 分发版 sm3_src.biz
MODULE_PACKAGE = __package__.rsplit('.', 1)[0] + '.biz'


class SuspendedHelp(Exception):
    """协议哨兵：模块调用 ctx.help 后抛出，run() 退出、内存栈释放。"""


class ProtocolError(Exception):
    """违反求助协议（如未完成求助时再发起）。"""


class Context:
    """功能模块唯一的对外通道：求助、日志、心跳、经验查询。"""

    def __init__(self, root, frame):
        self.root = root
        self.frame = frame

    @property
    def state(self):
        return self.frame['state']

    def log(self, msg, **kv):
        supervisor.log(self.root, self.frame['frameId'], self.frame['runId'],
                       'info', msg, **kv)

    def heartbeat(self):
        frames.heartbeat(self.root, self.frame)

    def recommend(self, limit=5):
        return review.recommend(self.root, self.frame['module'], limit)

    def help(self, module, payload, save_state=None):
        """动态嵌套求助：登记子帧后挂起自身；不等应答，协议通道稍后重入。

        save_state: 可选回调，返回 dict 并入本帧 state（应含 phase 断点标记）。
        """
        st = self.frame['state']
        pending_id = st.get('pendingChild')
        if pending_id:
            child = frames.get_frame(self.root, pending_id)
            if child and child['status'] not in frames.STATUS_FINAL:
                raise ProtocolError('存在未完成的求助，禁止发起新调用')
        child = frames.create_frame(self.root, module, payload,
                                    self.frame['runId'],
                                    parent_id=self.frame['frameId'])
        if save_state:
            st.update(save_state() or {})
        st['pendingChild'] = child['frameId']
        raise SuspendedHelp(child['frameId'])


def _load_module(name):
    return importlib.import_module(f'{MODULE_PACKAGE}.{name}')


def execute(root, frame):
    """执行一帧；幂等：终态帧直接返回已存应答。"""
    if frame['status'] in frames.STATUS_FINAL:
        return frames.make_response(
            'ok' if frame['status'] == 'done' else frame['status'],
            frame.get('answer') or {})
    resuming = frame['status'] == 'ready'
    frame['kind'] = 'resume' if resuming else frame['kind']
    frame['status'] = 'running'
    frame['startedAt'] = frame.get('startedAt') or frames.now()
    frames.record_event(root, frame, 'resume' if resuming else 'start')
    supervisor.log(root, frame['frameId'], frame['runId'], 'info',
                   f"execute module={frame['module']} kind={frame['kind']}")
    t0 = frames.now()
    try:
        mod = _load_module(frame['module'])
        request = {'trace': frames.make_trace(frame['runId'], frame['frameId'],
                                              frame.get('parentId')),
                   'task': {'module': frame['module'], 'kind': frame['kind']},
                   'input': frame['input'], 'state': frame['state']}
        resp = mod.run(request, Context(root, frame))
    except SuspendedHelp as e:
        frame['status'] = 'suspended'
        frames.record_event(root, frame, 'suspend', {'child': str(e)})
        return frames.make_response('unknown', {'suspended': str(e)})
    except ProtocolError as e:
        resp = frames.make_response('failed', {'error': f'protocol: {e}'})
        supervisor.log(root, frame['frameId'], frame['runId'], 'error', str(e))
    except Exception as e:  # noqa: BLE001 - 兜底，业务异常不拖垮协议通道
        resp = frames.make_response('failed', {'error': str(e)})
        supervisor.log(root, frame['frameId'], frame['runId'], 'error',
                       f'exception: {e}')
    resp.setdefault('metrics', {}).setdefault('elapsedMs',
                                              int((frames.now() - t0) * 1000))
    frame['metrics'] = resp['metrics']
    frame['status'] = 'done' if resp['status'] == 'ok' else resp['status']
    frame['answer'] = resp['answer']
    frame['finishedAt'] = frames.now()
    frames.record_event(root, frame, 'finish', {'status': resp['status']})
    return resp


def promote_ready(root, run_id):
    """子帧终态 → 父帧转 ready，并把子应答装填为 childAnswer。"""
    for f in frames.frames_of_run(root, run_id):
        if f['status'] != 'suspended':
            continue
        child = frames.get_frame(root, f['state'].get('pendingChild'))
        if child and child['status'] in frames.STATUS_FINAL:
            f['state'].pop('pendingChild', None)
            f['input'] = dict(f['input'])
            f['input']['childAnswer'] = {
                'status': 'ok' if child['status'] == 'done' else child['status'],
                'answer': child.get('answer') or {},
                'childModule': child['module'],
            }
            f['status'] = 'ready'
            frames.record_event(root, f, 'ready', {'child': child['frameId']})


def consume_verdicts(root, run_id):
    """判罚执行（帧状态变更唯一入口）：按监控事件把帧置 timed_out。"""
    for v in monitor.pending_verdicts(root):
        if v.get('runId') != run_id:
            continue
        f = frames.get_frame(root, v['frameId'])
        if f and f['status'] in frames.STATUS_OPEN:
            f['status'] = 'timed_out'
            f['answer'] = {'error': 'timeout verdict', 'verdictId': v['verdictId']}
            f['finishedAt'] = frames.now()
            frames.record_event(root, f, 'timeout', {'verdictId': v['verdictId']})
        monitor.mark_consumed(root, v)


def step(root, run_id):
    """推进一轮：消费判罚 → 提升 ready → 执行可执行帧。返回是否仍有待推进。"""
    consume_verdicts(root, run_id)
    promote_ready(root, run_id)
    progressed = False
    for f in frames.frames_of_run(root, run_id):
        if f['status'] in ('pending', 'ready'):
            execute(root, frames.get_frame(root, f['frameId']))
            progressed = True
    remaining = [f for f in frames.frames_of_run(root, run_id)
                 if f['status'] in ('pending', 'ready', 'running')]
    return progressed or bool(remaining)


def run(root, module, payload):
    """顶层入口：创建 run 并步进至无帧可推进，返回根帧应答。"""
    run_id = frames.new_id()
    root_frame = frames.create_frame(root, module, payload, run_id)
    guard = 0
    while step(root, run_id):
        guard += 1
        if guard > 1000:
            break
    f = frames.get_frame(root, root_frame['frameId'])
    used_llm = any(frame.get('metrics', {}).get('llmUsed', False)
                   for frame in frames.frames_of_run(root, run_id))
    return {'runId': run_id,
            **frames.make_response(
                'ok' if f['status'] == 'done' else f['status'],
                f.get('answer') or {},
                llm_used=used_llm)}


def resume(root, run_id):
    """重启恢复：等价于对 run 重新步进（帧即全部上下文）。"""
    return step(root, run_id)
