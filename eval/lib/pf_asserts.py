"""promptfoo python assertions that call the harness checks in lib/checks.py and lib/toolloop.py.

Each function receives (output, context) and returns {"pass", "score", "reason"}.
context carries vars (case, tools, ...), config (assertion config) and providerResponse.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402
import toolloop  # noqa: E402


def _result(ok: bool, reason: str) -> dict:
    return {"pass": bool(ok), "score": 1.0 if ok else 0.0, "reason": reason}


def _text(output) -> str:
    if output is None:
        return ""
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def check(output, context: dict) -> dict:
    """Run one harness check spec (context.config.spec) against the output."""
    spec = ((context.get("config") or {}).get("spec")) or {}
    if not spec:
        return _result(False, "assertion config is missing `spec`")
    vars_ = context.get("vars") or {}
    tool_calls = output if isinstance(output, list) else []
    text = "" if tool_calls else _text(output)
    ctx = {"case": vars_.get("case") or {}, "tools": vars_.get("tools") or [], "tool_calls": tool_calls}
    try:
        status, note = checks.run_check(spec, text, ctx)
    except Exception as e:  # noqa: BLE001 - report instead of crashing the worker
        return _result(False, f"{spec.get('type')}: check raised {type(e).__name__}: {e}")
    return _result(status == "pass", f"{spec['type']}: {note}")


# --------------------------------------------------------------------------- multi-turn tool cases

def _run(context: dict):
    md = ((context.get("providerResponse") or {}).get("metadata")) or context.get("metadata") or {}
    return md.get("toolloop")


def tool_sequence(output, context: dict) -> dict:
    run = _run(context)
    if not run:
        return _result(False, "no tool-loop transcript in provider metadata (provider error?)")
    ok, note = toolloop.sequence_verdict(run, (context.get("vars") or {}).get("case") or {})
    return _result(ok, note)


def tool_hygiene(output, context: dict) -> dict:
    run = _run(context)
    if not run:
        return _result(False, "no tool-loop transcript in provider metadata (provider error?)")
    return _result(*toolloop.hygiene_verdict(run))


def tool_final_answer(output, context: dict) -> dict:
    run = _run(context)
    if not run:
        return _result(False, "no tool-loop transcript in provider metadata (provider error?)")
    return _result(*toolloop.final_answer_verdict(run))
