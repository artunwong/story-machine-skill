"""CLI：run / step / resume / monitor / audit / stack；系统可脱离 AI Session 独立运行。"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from sm3_src.harness import channel, monitor, review, supervisor, frames


def main(argv=None):
    ap = argparse.ArgumentParser(prog='story_machine3')
    ap.add_argument('--root', default='.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_run = sub.add_parser('run')
    p_run.add_argument('--theme', required=True)
    p_run.add_argument('--genre', default='寓言')
    p_run.add_argument('--length', type=int, default=500)
    p_step = sub.add_parser('step'); p_step.add_argument('run_id')
    p_resume = sub.add_parser('resume'); p_resume.add_argument('run_id')
    sub.add_parser('monitor')
    p_audit = sub.add_parser('audit'); p_audit.add_argument('run_id')
    p_stack = sub.add_parser('stack'); p_stack.add_argument('run_id')
    sub.add_parser('doctor')
    args = ap.parse_args(argv)
    root = Path(args.root)

    if args.cmd == 'run':
        out = channel.run(root, 'story', {'theme': args.theme,
                                          'genre': args.genre,
                                          'length': args.length})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out['status'] == 'ok' else 1
    if args.cmd == 'step':
        more = channel.step(root, args.run_id)
        print(json.dumps({'runId': args.run_id, 'more': more}, ensure_ascii=False))
        return 0
    if args.cmd == 'resume':
        more = channel.resume(root, args.run_id)
        print(json.dumps({'runId': args.run_id, 'more': more}, ensure_ascii=False))
        return 0
    if args.cmd == 'monitor':
        print(json.dumps(monitor.scan(root), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == 'audit':
        print(json.dumps(review.audit_run(root, args.run_id),
                         ensure_ascii=False, indent=2))
        return 0
    if args.cmd == 'stack':
        print(json.dumps(supervisor.call_stack(root, args.run_id),
                         ensure_ascii=False, indent=2))
        return 0
    if args.cmd == 'doctor':
        import os
        from sm3_src.harness.llm import _env
        cfg = _env(root)
        report = {
            'python': sys.version.split()[0],
            'root': str(root.resolve()),
            'llm': {
                'base': bool(cfg.get('LLM_BASE_URL')),
                'key': bool(cfg.get('LLM_API_KEY')) and not cfg['LLM_API_KEY'].startswith('replace'),
                'model': cfg.get('LLM_MODEL', ''),
                'viaEnv': any(os.environ.get(k) for k in
                              ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL')),
            },
            'dirsWritable': all(
                _writable(root / d) for d in ('work/stacks', 'logs', 'memory')),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        ok = report['llm']['base'] and report['llm']['key'] and report['dirsWritable']
        return 0 if ok else 1
    return 2


def _writable(d):
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / '.w'; t.write_text('x', encoding='utf-8'); t.unlink()
        return True
    except OSError:
        return False


if __name__ == '__main__':
    sys.exit(main())
