"""OpenAI-backed Stage-2 judge.

Wires `LLMJudge` to OpenAI's Chat Completions API in JSON mode. The HTTP call is
injectable so this runs in tests with a fake transport and no API key. It uses
stdlib `urllib` — no `openai` package required (though you may swap one in).

    from boba_gate.llm_openai import build_openai_judge
    from boba_gate import Gate
    judge = build_openai_judge(api_key=os.environ["OPENAI_API_KEY"],
                               model="gpt-4o-mini")
    gate = Gate(judge=judge)

The judge already handles timeouts/errors by falling back to the deterministic
RuleBasedJudge (see stage2_judge.LLMJudge), so a flaky API never blocks the gate.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, Optional

from .gate.stage2_judge import LLMJudge

_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _urllib_chat(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - fixed host
        return json.loads(resp.read().decode("utf-8"))


def make_openai_call(api_key: str, model: str = "gpt-4o-mini",
                     temperature: float = 0.2, timeout: float = 8.0,
                     base_url: str = _CHAT_URL,
                     http_post: Optional[Callable[..., dict]] = None
                     ) -> Callable[[str, str], dict]:
    """Return an `llm_call(system, user) -> dict` for LLMJudge.

    Requests JSON output and parses the assistant message content as JSON. Raises
    on HTTP/parse errors — LLMJudge catches these and falls back.
    """
    post = http_post or _urllib_chat

    def _call(system: str, user: str) -> dict:
        payload = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = post(base_url, payload, api_key, timeout)
        content = resp["choices"][0]["message"]["content"]
        return json.loads(content)

    return _call


def build_openai_judge(api_key: str, model: str = "gpt-4o-mini",
                       **kwargs) -> LLMJudge:
    return LLMJudge(make_openai_call(api_key, model=model, **kwargs))
