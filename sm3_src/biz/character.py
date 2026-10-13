"""按主题生成或复用人物档案，只输出人物数据。"""
from __future__ import annotations
import json
from pathlib import Path
from sm3_src.harness.frames import make_response, new_id
from sm3_src.harness.llm import chat, parse_json, LLMUnavailable, LLMResponseError


def run(request, ctx):
    theme = request['input'].get('theme', '')
    idx_path = Path(ctx.root) / 'characters' / 'index.json'
    idx = json.loads(idx_path.read_text(encoding='utf-8')) if idx_path.exists() else {}
    for cid, meta in idx.items():
        if theme and theme in (meta.get('themes') or []) and meta.get('source') == 'llm':
            ctx.log('reuse character', characterId=cid)
            return make_response('ok', {'profile': meta['profile'], 'reused': True,
                                        'source': 'stored_llm'})
    try:
        content = chat(
            ctx.root,
            '你是故事人物设计师。只返回合法 JSON，不要 Markdown。',
            json.dumps({
                'task': '根据主题设计一个适合寓言故事的主角。',
                'theme': theme,
                'requiredFields': ['name', 'role', 'desire', 'flaw'],
                'outputShape': {'profile': {
                    'name': 'string',
                    'role': 'string',
                    'desire': 'string',
                    'flaw': 'string',
                }},
            }, ensure_ascii=False),
        )
        profile = parse_json(content).get('profile')
        required = ('name', 'role', 'desire', 'flaw')
        if not isinstance(profile, dict):
            raise LLMResponseError('人物应答缺少 profile 对象')
        if any(not isinstance(profile.get(field), str) or not profile[field].strip()
               for field in required):
            raise LLMResponseError(f'人物 profile 必须包含非空字段: {required}')
    except (LLMUnavailable, LLMResponseError, OSError, ValueError) as exc:
        return make_response('failed', {'stage': 'character', 'error': str(exc)})
    cid = new_id()[:12]
    matched_id = next((cid for cid, meta in idx.items()
                       if theme and theme in (meta.get('themes') or [])), None)
    character_id = matched_id or cid
    idx[character_id] = {'themes': [theme], 'profile': profile, 'source': 'llm'}
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    ctx.log('created character', characterId=character_id, source='llm')
    return make_response('ok', {'profile': profile, 'reused': False,
                                'source': 'llm'}, llm_used=True)
