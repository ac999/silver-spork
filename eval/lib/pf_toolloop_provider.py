"""promptfoo file:// provider that drives a multi-turn tool-calling scenario with scripted results.

Configured per test by gen_tests.py:
    provider: { id: file://lib/pf_toolloop_provider.py, config: { tier: <Tier>, timeout: 1800000 } }

`output` is the model's final text answer; `metadata.toolloop` carries the whole transcript
(calls with args and scripted results, per-turn responses, problems, timings) for the assertions in
lib/pf_asserts.py (tool_sequence, tool_hygiene, tool_final_answer) and for the scorecard hook.
"""
from __future__ import annotations

import json
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


def _messages(prompt, vars_: dict) -> list[dict]:
    if isinstance(prompt, str):
        try:
            parsed = json.loads(prompt)
            if isinstance(parsed, list) and parsed and all(isinstance(m, dict) and "role" in m for m in parsed):
                return [dict(m) for m in parsed]
        except ValueError:
            pass
    if vars_.get("messages"):
        return [dict(m) for m in vars_["messages"]]
    return [{"role": "user", "content": str(prompt)}]


def call_api(prompt, options: dict, context: dict) -> dict:
    config = (options or {}).get("config") or {}
    vars_ = (context or {}).get("vars") or {}
    tier = config.get("tier") or vars_.get("tier")
    cfg = _models()
    if tier not in cfg["models"]:
        return {"error": f"unknown tier {tier!r}; known: {sorted(cfg['models'])}"}
    mcfg = cfg["models"][tier]
    case = vars_.get("case") or {}
    suite = vars_.get("suite") or {}
    if case.get("expected_calls") is None:
        return {"error": "pf_toolloop_provider is only for cases with `expected_calls`"}
    try:
        run = toolloop.drive(cfg, mcfg, tier, suite, case, _messages(prompt, vars_))
    except toolloop.ServerUnavailable as e:
        return {"error": f"server unavailable: {e}"}
    except Exception as e:  # noqa: BLE001 - surface as a promptfoo error row
        return {"error": f"{type(e).__name__}: {e}"}
    status, note = toolloop.judge(run, case)
    usage = run.get("usage") or {}
    return {
        "output": run["content"],
        "tokenUsage": {"prompt": usage.get("prompt_tokens"), "completion": usage.get("completion_tokens"),
                       "total": usage.get("total_tokens")},
        "metadata": {"toolloop": {**run, "status": status, "note": note, "tier": tier}},
    }
