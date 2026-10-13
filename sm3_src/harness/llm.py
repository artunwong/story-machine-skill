"""模型能力：按独立配置调用 LLM；未配置或调用失败直接报告错误。"""
from __future__ import annotations
import json, os, urllib.request
from pathlib import Path

class LLMUnavailable(Exception):
    pass


class LLMResponseError(Exception):
    pass

def _env(root):
    cfg = {}
    for p in (Path(root) / 'config' / '.env', Path(root) / '.env'):
        if p.exists():
            for line in p.read_text(encoding='utf-8').splitlines():
                if '=' in line and not line.strip().startswith('#'):
                    k, _, v = line.partition('=')
                    cfg[k.strip()] = v.strip()
    # 进程环境变量优先：skill 分发版由宿主 session 注入端点
    for k in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg

def chat(root, system, user, timeout=60):
    cfg = _env(root)
    key, base, model = cfg.get('LLM_API_KEY', ''), cfg.get('LLM_BASE_URL', ''), cfg.get('LLM_MODEL', '')
    if not key or key.startswith('replace') or not base:
        raise LLMUnavailable('LLM provider 未配置，见 .env.example')
    req = urllib.request.Request(
        base.rstrip('/') + '/chat/completions',
        data=json.dumps({'model': model,
                         'messages': [{'role': 'system', 'content': system},
                                      {'role': 'user', 'content': user}]}).encode(),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode())['choices'][0]['message']['content']


def parse_json(content):
    """解析模型 JSON；格式错误不得静默降级。"""
    text = content.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f'LLM 返回不是合法 JSON: {exc}') from exc
    if not isinstance(value, dict):
        raise LLMResponseError('LLM 返回 JSON 顶层必须是对象')
    return value
