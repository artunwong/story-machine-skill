"""接收创作主题，自主求助写作、评审改稿与验收，组装最终结果。"""
from __future__ import annotations
from sm3_src.harness.frames import make_response
from sm3_src.harness.review import record_route

MAX_REVIEW_ROUNDS = 3
MAX_TECHNIQUE_RETRIES = 2  # 业务模块内部参数，可调


def run(request, ctx):
    inp = request['input']
    st = request['state']
    theme = st.get('theme') or inp.get('theme', '未命名主题')
    genre = st.get('genre') or inp.get('genre', '寓言')
    phase = st.get('phase', 'start')

    if phase == 'start':
        ctx.log('accept theme', theme=theme, genre=genre)
        recs = ctx.recommend()
        if recs:
            ctx.log('route hint', hints=recs)
        ctx.help('writer', {'theme': theme, 'genre': genre,
                            'length': inp.get('length', 500),
                            'round': st.get('round', 1)},
                 save_state=lambda: {'phase': 'awaiting_draft',
                                     'theme': theme, 'genre': genre})

    if phase == 'awaiting_draft':
        child = inp['childAnswer']
        if child['status'] != 'ok':
            return make_response('failed',
                                 {'stage': 'writer', 'downstream': child['status']})
        st['draft'] = child['answer']
        if st['draft'].get('techniqueSuitable') is False:
            # writer 自检写法不可行：记负样本并重选
            tech = st['draft'].get('technique', {})
            tech_name = tech.get('name', '')
            if tech_name:
                record_route(ctx.root, 'story', f'technique:{tech_name}',
                             score=-0.5, note='writer_selfcheck_rejected')
            st['rejectedTechniques'] = st.get('rejectedTechniques', []) + [tech_name]
            form_name = (tech.get('form') or {}).get('name', '')
            if form_name:
                record_route(ctx.root, 'story', f'form:{form_name}',
                             score=-0.5, note='writer_selfcheck_rejected')
                st['rejectedForms'] = st.get('rejectedForms', []) + [form_name]
            for k in ('profile', 'conflict', 'outline', 'technique', 'draft',
                      'sequenceResults'):
                st.pop(k, None)
            st['techniqueRetries'] = st.get('techniqueRetries', 0) + 1
            if st['techniqueRetries'] < MAX_TECHNIQUE_RETRIES:
                ctx.help('writer', {'theme': st['theme'], 'genre': st['genre'],
                                    'length': 500, 'round': st.get('round', 1) + 1,
                                    'rejectedTechniques': st['rejectedTechniques'],
                                    'rejectedForms': st.get('rejectedForms', [])},
                         save_state=lambda: {'phase': 'awaiting_draft',
                                             'round': st.get('round', 1) + 1})
            else:
                return make_response('failed', {'error': 'technique retries exhausted'})
        ctx.help('reviewer', {'story': st['draft'].get('story', ''),
                              'genre': st['draft'].get('genre', st['genre']),
                              'conflict': st['draft'].get('conflict', {}),
                              'outline': st['draft'].get('outline', {}),
                              'technique': st['draft'].get('technique', {})},
                 save_state=lambda: {'phase': 'awaiting_review'})

    if phase == 'awaiting_review':
        child = inp['childAnswer']
        review_result = child['answer'] if child['status'] == 'ok' else {}
        st['lastReview'] = review_result
        rnd = st.get('round', 1)
        technique_verdict = str(review_result.get('techniqueVerdict', ''))
        form_verdict = str(review_result.get('formVerdict', ''))
        technique_bad = any(k in technique_verdict + form_verdict
                            for k in ('不适合', '不匹配', '换写法', '换文体', '重新选择'))
        retries = st.get('techniqueRetries', 0)
        if technique_bad and retries < MAX_TECHNIQUE_RETRIES:
            # 回退：记负样本、清上游产物、重选写法
            if st.get('draft', {}).get('technique'):
                record_route(ctx.root, 'story',
                             f"technique:{st['draft']['technique']['name']}",
                             score=-0.5, note='rejected_by_reviewer')
            st['rejectedTechniques'] = st.get('rejectedTechniques', []) + [
                st['draft'].get('technique', {}).get('name')]
            form_name = (st['draft'].get('technique', {}).get('form') or {}).get('name', '')
            if form_name:
                record_route(ctx.root, 'story', f'form:{form_name}',
                             score=-0.5, note='rejected_by_reviewer')
                st['rejectedForms'] = st.get('rejectedForms', []) + [form_name]
            for k in ('profile', 'conflict', 'outline', 'technique', 'draft',
                      'sequenceResults'):
                st.pop(k, None)
            st['techniqueRetries'] = retries + 1
            ctx.help('writer', {'theme': st['theme'], 'genre': st['genre'],
                                'length': 500, 'round': rnd + 1,
                                'feedback': st.get('lastFeedback', ''),
                                'rejectedTechniques': st['rejectedTechniques'],
                                'rejectedForms': st.get('rejectedForms', [])},
                     save_state=lambda: {'phase': 'awaiting_draft',
                                         'round': rnd + 1})
        elif review_result.get('approve') or rnd >= MAX_REVIEW_ROUNDS:
            ctx.help('validator', {'draft': st['draft'], 'genre': st['genre'],
                                   'theme': st['theme']},
                     save_state=lambda: {'phase': 'awaiting_verdict'})
        else:
            st['lastFeedback'] = review_result.get('feedback', '')
            ctx.help('writer', {'theme': st['theme'], 'genre': st['genre'],
                                'length': 500, 'round': rnd + 1,
                                'feedback': st['lastFeedback'],
                                'rejectedTechniques': st.get('rejectedTechniques', []),
                                'rejectedForms': st.get('rejectedForms', [])},
                     save_state=lambda: {'phase': 'awaiting_draft',
                                         'round': rnd + 1})

    if phase == 'awaiting_verdict':
        child = inp['childAnswer']
        return make_response('ok', {'theme': st['theme'],
                                    'genre': st['draft'].get('genre', st['genre']),
                                    'draft': st['draft'],
                                    'review': st.get('lastReview', {}),
                                    'rounds': st.get('round', 1),
                                    'techniqueRetries': st.get('techniqueRetries', 0),
                                    'validation': child['answer'],
                                    'validated': child['status'] == 'ok'})
    return make_response('failed', {'error': f'unknown phase: {phase}'})
