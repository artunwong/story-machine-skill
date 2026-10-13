"""根据主题与冲突选择叙事写法与文体，输出驱动后续求助的调用序列。"""
from __future__ import annotations
import json
from sm3_src.harness.frames import make_response
from sm3_src.harness.llm import chat, parse_json, LLMUnavailable, LLMResponseError

PALETTE = {
    'chronological':  {'label': '正叙线性', 'sequence': ['outline']},
    'in_medias_res':  {'label': '悬念先行', 'sequence': ['outline']},
    'flashback':      {'label': '倒叙',     'sequence': ['outline']},
    'frame_narrative':{'label': '框架叙事', 'sequence': ['character', 'outline']},
    'parallel':       {'label': '并列对照', 'sequence': ['outline', 'character']},
    'circular':       {'label': '循环结构', 'sequence': ['outline']},
    'epistolary':     {'label': '书信日记体', 'sequence': ['outline']},
    'incremental':    {'label': '重复递进', 'sequence': ['outline']},
}

FORM_PALETTE = {
    'fable':      {'label': '寓言童话', 'hint': '拟人角色+象征冲突+结尾寓意'},
    'prose':      {'label': '散文',     'hint': '抒情写意，重意境轻情节，段落松散'},
    'microfic':   {'label': '微小说',   'hint': '短幅完整情节，反转或留白收尾'},
    'poem':       {'label': '诗歌',     'hint': '分行成节，意象与节奏承载主题'},
    'gatha':      {'label': '偈颂',     'hint': '佛偈式颂句，偈+本事缘起两段'},
    'myth':       {'label': '神话',     'hint': '超自然主角、宏大象征、训诫或奇迹'},
}


def run(request, ctx):
    inp = request['input']
    rejected = inp.get('rejected', [])
    rejected_forms = inp.get('rejectedForms', [])
    try:
        content = chat(
            ctx.root,
            '你是叙事结构与文体顾问。只返回合法 JSON，不要 Markdown，不要解释。',
            json.dumps({
                'task': '根据主题、体裁偏好、人物与冲突，选择最合适的叙事写法与文体，'
                        '两者共同服务吸引读者与传播核心主题。',
                'theme': inp.get('theme', ''),
                'genreHint': inp.get('genre', '寓言'),
                'profile': inp.get('profile', {}),
                'conflict': inp.get('conflict', {}),
                'rejectedTechniques': rejected,
                'rejectedForms': rejected_forms,
                'candidates': {k: v['label'] for k, v in PALETTE.items()},
                'formCandidates': {k: v['label'] for k, v in FORM_PALETTE.items()},
                'requirements': {
                    'form': '从 formCandidates 选文体；genreHint 仅为参考可推翻，'
                            '推翻时 reason 须说明该文体为何更利于传播主题',
                    'reason': '引用主题/冲突说明为何适配，非模板句',
                    'hook': '开篇钩子建议，怎么吸引读者',
                    'structureHint': '该写法下的段落时间线安排说明',
                    'mustChooseFrom': list(PALETTE.keys()),
                    'mustChooseFormFrom': list(FORM_PALETTE.keys()),
                    'avoid': '不得选择 rejectedTechniques/rejectedForms 中已否决项',
                },
                'outputShape': {'technique': {
                    'name': 'string', 'label': 'string', 'reason': 'string',
                    'hook': 'string', 'structureHint': 'string',
                    'form': {'name': 'string', 'label': 'string'}}},
            }, ensure_ascii=False),
        )
        tech = parse_json(content).get('technique')
        required = ('name', 'label', 'reason', 'hook', 'structureHint')
        if not isinstance(tech, dict):
            raise LLMResponseError('写法应答缺少 technique 对象')
        if any(not isinstance(tech.get(f), str) or not tech[f].strip()
               for f in required):
            raise LLMResponseError(f'technique 必须包含非空字段: {required}')
        name = tech['name']
        if name not in PALETTE:
            raise LLMResponseError(f'写法名 {name} 不在候选集 {sorted(PALETTE)}')
        if name in rejected:
            raise LLMResponseError(f'写法 {name} 已被否决，不得重复选择')
        form = tech.get('form')
        if not isinstance(form, dict) or form.get('name') not in FORM_PALETTE:
            raise LLMResponseError(f'technique.form.name 必须在候选集 {sorted(FORM_PALETTE)}')
        if form['name'] in rejected_forms:
            raise LLMResponseError(f'文体 {form["name"]} 已被否决，不得重复选择')
        form['label'] = FORM_PALETTE[form['name']]['label']
        tech['sequence'] = PALETTE[name]['sequence']
    except (LLMUnavailable, LLMResponseError, OSError, ValueError) as exc:
        return make_response('failed', {'stage': 'technique', 'error': str(exc)})
    return make_response('ok', {'technique': tech, 'source': 'llm'},
                       llm_used=True)
