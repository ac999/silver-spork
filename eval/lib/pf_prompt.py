"""promptfoo prompt function: emits the chat messages for a test plus the per-tier request config.

promptfoo merges the returned `config` into the provider config for this one request, which is how
the sampling parameters and chat_template_kwargs from models.json (one source of truth) and the
per-case max_tokens / tools reach llama-server without being copied into promptfooconfig.yaml.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import toolloop  # noqa: E402

_CFG = None


def _models():
    global _CFG
    if _CFG is None:
        _CFG = toolloop.load_models()
    return _CFG


def build_prompt(context: dict) -> dict:
    vars_ = context.get("vars") or {}
    provider_id = (context.get("provider") or {}).get("id") or ""
    tier = vars_.get("tier") or provider_id.rsplit(":", 1)[-1]
    cfg = _models()
    mcfg = cfg["models"].get(tier, {})
    # Pass the CASE's raw max_tokens, not vars.max_tokens: gen_tests.py already stored the effective budget
    # (with the thinking allowance) there, and request_body adds the allowance itself.
    case_max = (vars_.get("case") or {}).get("max_tokens")
    body = toolloop.request_body(cfg, mcfg, tier, vars_.get("messages") or [], vars_.get("tools"), case_max)
    sampling = mcfg.get("sampling", {})
    # temperature/top_p are keys promptfoo knows (with omitDefaults they are only sent when set);
    # everything else (top_k, min_p, chat_template_kwargs, ...) goes through `passthrough` verbatim.
    config = {k: v for k, v in sampling.items() if k in ("temperature", "top_p")}
    config["max_tokens"] = body["max_tokens"]
    config["tools"] = body.get("tools") or []
    config["passthrough"] = {k: v for k, v in sampling.items() if k not in ("temperature", "top_p")}
    if body.get("chat_template_kwargs"):
        config["passthrough"]["chat_template_kwargs"] = body["chat_template_kwargs"]
    return {"prompt": body["messages"], "config": config}
