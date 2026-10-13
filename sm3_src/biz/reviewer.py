"""产出证据化评审意见与放行建议，对照冲突与提纲逐项核查，绝不改稿。"""
from __future__ import annotations
import json
from sm3_src.harness.frames import make_response
from sm3_src.harness.llm import chat, parse_json, LLMUnavailable, LLMResponseError

DIMENSIONS = ('structure', 'causality', 'impact', 'theme_fidelity',
              'genre_fit', 'readability', 'concision', 'logic_soundness')


def run(request, ctx):
    inp = request['input']
    story = inp.get('story', '')
    try:
        content = chat(
            ctx.root,
            '你是严格的中文寓言编辑。只返回合法 JSON，不要 Markdown，不要改写原稿。',
            json.dumps({
                'task': '评审故事：对照冲突与提纲逐项核查，每维度引原文证据给分，'
                        '标出最弱点并给出改进预算。',
                'story': story,
                'conflict': inp.get('conflict', {}),
                'outline': inp.get('outline', {}),
                'genre': inp.get('genre', '寓言'),
                'technique': inp.get('technique', {}),
                'dimensions': {
                    'structure': '起因/发展/转折/结局齐备，兑现提纲 beats',
                    'causality': '事件间有因果而非巧合拼接',
                    'impact': '高潮有具体冲击画面，结尾非抽象复述',
                    'theme_fidelity': '主题词出现且寓意兑现',
                    'genre_fit': '符合所选文体的质感与分段习惯（散文/诗/偈颂各有章法）',
                    'readability': '一段一情节，转折密集处提示拆段',
                    'concision': '无重复解释，句子推进情节或形成冲击',
                    'logic_soundness': '内部逻辑自洽：数量/规模/时限/物理常识合理；'
                                       '冲突与提纲承诺的代价在正文实际兑现；'
                                       '无前提悬空、因果倒置或与设定矛盾的情节',
                },
                'outputShape': {
                    'score': 'integer 1-5',
                    'dimensionScores': {d: 'integer 1-5' for d in DIMENSIONS},
                    'issues': [{'severity': 'low|medium|high',
                                'dimension': 'string',
                                'paragraph': 'integer',
                                'issue': 'string'}],
                    'weakestPoint': {'dimension': 'string', 'evidence': 'string'},
                    'improvementBudget': ['string'],
                    'techniqueVerdict': 'string  # 一句话判断所选写法是否适配并增强吸引力',
                    'formVerdict': 'string  # 一句话判断所选文体是否适配主题并利于传播',
                    'approve': 'boolean',
                    'feedback': 'string',
                },
            }, ensure_ascii=False),
        )
        result = parse_json(content)
        if not isinstance(result.get('score'), int):
            raise LLMResponseError('评审应答缺少整数 score')
        if not isinstance(result.get('issues'), list):
            raise LLMResponseError('评审应答缺少 issues 数组')
        if not isinstance(result.get('approve'), bool):
            raise LLMResponseError('评审应答缺少布尔 approve')
        if not isinstance(result.get('feedback'), str):
            raise LLMResponseError('评审应答缺少 feedback')
        if 'techniqueVerdict' in result and not isinstance(result['techniqueVerdict'], str):
            raise LLMResponseError('techniqueVerdict 必须是字符串')
        if 'formVerdict' in result and not isinstance(result['formVerdict'], str):
            raise LLMResponseError('formVerdict 必须是字符串')
        dims = result.get('dimensionScores')
        if not isinstance(dims, dict) or any(
                not isinstance(dims.get(d), int) for d in DIMENSIONS):
            raise LLMResponseError(f'dimensionScores 必须包含整数维度: {DIMENSIONS}')
    except (LLMUnavailable, LLMResponseError, OSError, ValueError) as exc:
        return make_response('failed', {'stage': 'reviewer', 'error': str(exc)})
    result['source'] = 'llm'
    return make_response('ok', result, llm_used=True)
