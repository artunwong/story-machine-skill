"""产出故事草稿：按 technique.sequence 动态求助上游，可行即成稿，可按评审 feedback 改稿。"""
from __future__ import annotations
import json
from sm3_src.harness.frames import make_response
from sm3_src.harness.llm import chat, parse_json, LLMUnavailable, LLMResponseError


def run(request, ctx):
    inp = request['input']
    st = request['state']
    phase = st.get('phase', 'start')

    # 1. 求人物
    if phase == 'start':
        ctx.help('character', {'theme': inp.get('theme', ''),
                               'genre': inp.get('genre', '寓言')},
                 save_state=lambda: {'phase': 'awaiting_profile'})

    if phase == 'awaiting_profile':
        child = inp['childAnswer']
        if child['status'] != 'ok':
            return make_response('failed', {'stage': 'character',
                                            'downstream': child['status']})
        st['profile'] = child['answer'].get('profile', {})
        ctx.help('conflict', {'theme': inp.get('theme', ''),
                              'genre': inp.get('genre', '寓言'),
                              'profile': st['profile']},
                 save_state=lambda: {'phase': 'awaiting_conflict'})

    # 2. 求冲突
    if phase == 'awaiting_conflict':
        child = inp['childAnswer']
        if child['status'] != 'ok':
            return make_response('failed', {'stage': 'conflict',
                                            'downstream': child['status']})
        st['conflict'] = child['answer'].get('conflict', {})
        ctx.help('technique', {'theme': inp.get('theme', ''),
                               'genre': inp.get('genre', '寓言'),
                               'profile': st['profile'],
                               'conflict': st['conflict'],
                               'rejected': inp.get('rejectedTechniques', []),
                               'rejectedForms': inp.get('rejectedForms', [])},
                 save_state=lambda: {'phase': 'awaiting_technique'})

    # 3. 求写法 + 可行性自检
    if phase == 'awaiting_technique':
        child = inp['childAnswer']
        if child['status'] != 'ok':
            return make_response('failed', {'stage': 'technique',
                                            'downstream': child['status']})
        st['technique'] = child['answer'].get('technique', {})
        form = st['technique'].get('form') or {}
        if form.get('label'):
            st['effectiveGenre'] = form['label']  # 文体由 technique 决策，覆盖 genreHint
        st['phase'] = 'check_feasibility'
        # 不立即落盘 phase，让 execute 完成本轮
        return _check_feasibility(request, ctx, st, inp)

    if phase == 'check_feasibility':
        return _check_feasibility(request, ctx, st, inp)

    if phase == 'awaiting_sequence':
        child = inp['childAnswer']
        if child['status'] != 'ok':
            return make_response('failed', {'stage': child.get('childModule'),
                                            'downstream': child['status']})
        key = 'outline' if child.get('childModule') == 'outline' else 'extra'
        st.setdefault('sequenceResults', {})[key] = child['answer']
        return _advance_sequence(request, ctx, st, inp)

    if phase == 'compose':
        return _compose(request, ctx, st, inp)

    return make_response('failed', {'error': f'unknown phase: {phase}'})


def _check_feasibility(request, ctx, st, inp):
    """LLM 自检：当前写法能否成稿；不能则返回 techniqueSuitable=false。"""
    try:
        content = chat(
            ctx.root,
            '你是写作可行性评估员。只返回合法 JSON。',
            json.dumps({
                'task': '评估给定写法/文体/人物/冲突能否成稿；写法或文体任一不适合即 false。',
                'technique': st['technique'],
                'profile': st['profile'],
                'conflict': st['conflict'],
                'outputShape': {'feasible': 'boolean', 'reason': 'string'},
            }, ensure_ascii=False),
        )
        r = parse_json(content)
        feasible = bool(r.get('feasible', True))
    except (LLMUnavailable, LLMResponseError, OSError, ValueError):
        feasible = True  # 自检失败不阻塞，继续走流程
    if not feasible:
        return make_response('ok', {'techniqueSuitable': False,
                                    'reason': r.get('reason', '写法不适合成稿'),
                                    'technique': st['technique'],
                                    'source': 'llm'}, llm_used=True)
    st['phase'] = 'awaiting_sequence'
    return _advance_sequence(request, ctx, st, inp)


def _advance_sequence(request, ctx, st, inp):
    """按 technique.sequence 动态推进求助；完成后进入 compose。"""
    seq = st['technique'].get('sequence', ['outline'])
    done = len(st.get('sequenceResults', {}))
    if done >= len(seq):
        st['phase'] = 'compose'
        return _compose(request, ctx, st, inp)
    nxt = seq[done]
    st['pendingSeqIndex'] = done
    payload = {'theme': inp.get('theme', ''),
               'genre': st.get('effectiveGenre', inp.get('genre', '寓言')),
               'profile': st['profile'], 'conflict': st['conflict'],
               'technique': st['technique']}
    ctx.help(nxt, payload,
             save_state=lambda: {'phase': 'awaiting_sequence'})


def _compose(request, ctx, st, inp):
    ctx.heartbeat()
    outline = st.get('sequenceResults', {}).get('outline', {}).get('outline', {})
    story, last_err = None, None
    for _ in range(2):  # 结构错误重试一次，仍失败则如实报错（不降级）
        try:
            content = chat(
                ctx.root,
                '你是中文作家，按指定文体创作。只返回合法 JSON，不要 Markdown，不要解释。',
                json.dumps({
                    'task': '依据写法、文体、提纲、人物、冲突创作，兑现因果链与高潮，文体质感必须符合指定文体。',
                    'theme': inp.get('theme', ''),
                    'genre': st.get('effectiveGenre', inp.get('genre', '寓言')),
                    'profile': st['profile'],
                    'conflict': st['conflict'],
                    'technique': st['technique'],
                    'outline': outline,
                    'feedback': inp.get('feedback', ''),
                    'length': int(inp.get('length', 500)),
                    'constraint': '正文自然包含完整主题词；一段一情节；按所选写法的时间线叙述。',
                    'outputShape': {'story': 'string'},
                }, ensure_ascii=False),
            )
            story = parse_json(content).get('story')
            last_err = None
            break
        except (LLMUnavailable, OSError, ValueError, LLMResponseError) as exc:
            last_err = exc
    try:
        if not isinstance(story, str) or not story.strip():
            raise (last_err or LLMResponseError('写作应答缺少非空 story 字段'))
    except (LLMUnavailable, LLMResponseError, OSError, ValueError) as exc:
        return make_response('failed', {'stage': 'writer', 'error': str(exc)})
    return make_response('ok', {
        'profile': st['profile'], 'conflict': st['conflict'],
        'technique': st['technique'], 'outline': outline,
        'story': story, 'source': 'llm',
        'genre': st.get('effectiveGenre', inp.get('genre', '寓言')),
        'round': int(inp.get('round', 1)),
        'techniqueSuitable': True}, llm_used=True)
