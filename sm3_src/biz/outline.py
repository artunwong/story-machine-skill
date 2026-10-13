"""把主题、人物与冲突展开为起承转合的因果链提纲。"""
from __future__ import annotations
import json
from sm3_src.harness.frames import make_response
from sm3_src.harness.llm import chat, parse_json, LLMUnavailable, LLMResponseError


def run(request, ctx):
    inp = request['input']
    try:
        content = chat(
            ctx.root,
            '你是故事结构师。只返回合法 JSON，不要 Markdown，不要解释。',
            json.dumps({
                'task': '把主题、人物与冲突展开为起承转合的因果链提纲。',
                'theme': inp.get('theme', ''),
                'genre': inp.get('genre', '寓言'),
                'profile': inp.get('profile', {}),
                'conflict': inp.get('conflict', {}),
                'requirements': {
                    'causal_chain': '≥4 个顺序因果节点，节点间有因果而非并列',
                    'climax': '落在转折之后，呈现冲突的解决方式',
                    'beats': '起承转合四段各一句话',
                },
                'outputShape': {'outline': {
                    'causal_chain': ['string'],
                    'climax': 'string',
                    'beats': {'setup': 'string', 'development': 'string',
                              'turning': 'string', 'resolution': 'string'}}},
            }, ensure_ascii=False),
        )
        outline = parse_json(content).get('outline')
        if not isinstance(outline, dict):
            raise LLMResponseError('提纲应答缺少 outline 对象')
        chain = outline.get('causal_chain')
        if not isinstance(chain, list) or len(chain) < 4:
            raise LLMResponseError('causal_chain 至少需要 4 个因果节点')
        if any(not isinstance(n, str) or not n.strip() for n in chain):
            raise LLMResponseError('causal_chain 节点必须为非空字符串')
        beats = outline.get('beats')
        for key in ('setup', 'development', 'turning', 'resolution'):
            if not isinstance(beats, dict) or not beats.get(key):
                raise LLMResponseError(f'beats 缺少字段: {key}')
        if not isinstance(outline.get('climax'), str) or not outline['climax'].strip():
            raise LLMResponseError('outline 缺少非空 climax')
    except (LLMUnavailable, LLMResponseError, OSError, ValueError) as exc:
        return make_response('failed', {'stage': 'outline', 'error': str(exc)})
    return make_response('ok', {'outline': outline, 'source': 'llm'},
                       llm_used=True)
