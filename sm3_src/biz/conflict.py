"""为主题与人物提炼故事核心冲突——阻力、两难选择与选择代价。"""
from __future__ import annotations
import json
from sm3_src.harness.frames import make_response
from sm3_src.harness.llm import chat, parse_json, LLMUnavailable, LLMResponseError


def run(request, ctx):
    inp = request['input']
    try:
        content = chat(
            ctx.root,
            '你是故事冲突设计师。只返回合法 JSON，不要 Markdown，不要解释。',
            json.dumps({
                'task': '根据主题与人物弱点提炼故事核心冲突。',
                'theme': inp.get('theme', ''),
                'genre': inp.get('genre', '寓言'),
                'profile': inp.get('profile', {}),
                'requirements': {
                    'obstacle': '主角必须面对的真实阻力，与人物弱点相关',
                    'choice': '呈现两难抉择，包含"或"式对立选项，不是单选题',
                    'cost': '选择必须付出的代价，与选择后果直接挂钩',
                },
                'outputShape': {'conflict': {
                    'obstacle': 'string', 'choice': 'string', 'cost': 'string'}},
            }, ensure_ascii=False),
        )
        conflict = parse_json(content).get('conflict')
        required = ('obstacle', 'choice', 'cost')
        if not isinstance(conflict, dict):
            raise LLMResponseError('冲突应答缺少 conflict 对象')
        if any(not isinstance(conflict.get(f), str) or not conflict[f].strip()
               for f in required):
            raise LLMResponseError(f'conflict 必须包含非空字段: {required}')
        if '或' not in conflict['choice'] and '还是' not in conflict['choice']:
            raise LLMResponseError('choice 必须呈现两难对立选项')
    except (LLMUnavailable, LLMResponseError, OSError, ValueError) as exc:
        return make_response('failed', {'stage': 'conflict', 'error': str(exc)})
    return make_response('ok', {'conflict': conflict, 'source': 'llm'},
                       llm_used=True)
