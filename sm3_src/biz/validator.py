"""对最终草稿做结构化验收（非空/结构/主题回声/一段一情节/结尾不复述），给出放行结论。"""
from __future__ import annotations
import difflib
import re
from sm3_src.harness.frames import make_response

PIVOT_WORDS = ('后来', '第二天', '可是', '但是', '于是', '最后', '几年后', '那天')


def _compact(text):
    """去标点空白后比较：诗/偈颂分行标点不影响主题回声判定。"""
    return re.sub(r'\W+', '', text)


def run(request, ctx):
    draft = request['input'].get('draft', {})
    theme = request['input'].get('theme', '')
    story = draft.get('story', '')
    technique = (draft.get('technique') or {}).get('name', '')
    paragraphs = [p.strip() for p in story.split('\n\n') if p.strip()]
    overloaded = [i + 1 for i, p in enumerate(paragraphs)
                  if sum(p.count(w) for w in PIVOT_WORDS) >= 3]
    # 循环结构的首尾呼应是刻意设计，不做复述判罚
    ending_repeated = bool(
        technique != 'circular' and len(paragraphs) >= 2
        and difflib.SequenceMatcher(
            None, paragraphs[0], paragraphs[-1]).ratio() >= 0.8)
    checks = {
        'nonEmpty': bool(story.strip()),
        'hasStructure': story.count('\n\n') >= 2,
        'themeEcho': not theme or _compact(theme) in _compact(story),
        'oneBeatPerParagraph': not overloaded,
        'endingNotRestatement': not ending_repeated,
    }
    passed = all(checks.values())
    return make_response('ok' if passed else 'failed',
                         {'checks': checks, 'approved': passed,
                          'overloadedParagraphs': overloaded})
