"""llama-server client and the multi-turn tool-calling driver with scripted tool results.

Shared by eval/run_eval.py and the promptfoo provider eval/lib/pf_toolloop_provider.py.
Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import checks

EVAL_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = EVAL_DIR.parent
MODELS_PATH = Path(os.environ.get("EVAL_MODELS_JSON") or EVAL_DIR / "models.json")
MODELS_EXAMPLE = EVAL_DIR / "models.example.json"
LOCAL_CONFIG = REPO_DIR / "config" / "local-ai.json"
DEFAULT_SERVER_URL = "http://127.0.0.1:8080"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_THINKING_ALLOWANCE = 6144
DEFAULT_TIMEOUT_S = 600
DEFAULT_MAX_TURNS = 8

# Fixed role vocabulary: suites declare `applies_to` in these terms, tiers declare `roles`.
ROLES = ("reasoning", "coding", "tools", "everyday", "creative", "security")
TIER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # becomes tiers/<Tier>.env and the router preset name


class ServerUnavailable(Exception):
    pass


class ConfigError(Exception):
    """models.json missing or malformed; the message tells the user what to fix."""


# --------------------------------------------------------------------------- configuration

def local_config() -> dict:
    """config/local-ai.json (repo-level, gitignored) or {} when absent/unreadable."""
    if LOCAL_CONFIG.is_file():
        try:
            data = checks.load_json(LOCAL_CONFIG)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            pass
    return {}


def server_url(models_cfg: dict | None = None) -> str:
    """Server URL: models.json `base_url` > config/local-ai.json `server_url` > localhost:8080."""
    if models_cfg and models_cfg.get("base_url"):
        return str(models_cfg["base_url"]).rstrip("/")
    url = local_config().get("server_url")
    return str(url).rstrip("/") if url else DEFAULT_SERVER_URL


def python_cmd() -> list[str]:
    """Interpreter used for promptfoo's Python and the generated tier env files:
    PROMPTFOO_PYTHON env var > config/local-ai.json `python_cmd` > "python" (split on whitespace)."""
    raw = os.environ.get("PROMPTFOO_PYTHON") or local_config().get("python_cmd") or "python"
    return str(raw).split()


def _validate(cfg: dict, path: Path) -> dict:
    hint = f"see {MODELS_EXAMPLE.name} for the annotated schema"
    if not isinstance(cfg, dict) or not isinstance(cfg.get("models"), dict) or not cfg["models"]:
        raise ConfigError(f"{path}: expected a top-level \"models\" object with at least one tier; {hint}")
    langs = cfg.get("languages", [])
    if not isinstance(langs, list) or not all(isinstance(x, str) for x in langs):
        raise ConfigError(f"{path}: \"languages\" must be a list of language codes such as [\"ro\"]; {hint}")
    cfg["languages"] = [x.lower() for x in langs]
    cfg["models"] = {k: v for k, v in cfg["models"].items() if not k.startswith("_")}  # "_comment" keys
    if not cfg["models"]:
        raise ConfigError(f"{path}: \"models\" holds no tiers; {hint}")
    for name, m in cfg["models"].items():
        if not TIER_NAME_RE.match(name):
            raise ConfigError(f"{path}: tier name {name!r} is a placeholder or contains unusable characters; "
                              f"rename it to the llama-server preset name (letters, digits, . _ -); {hint}")
        if not isinstance(m, dict):
            raise ConfigError(f"{path}: tier {name!r} must be an object; {hint}")
        roles = m.get("roles")
        if not isinstance(roles, list) or not roles:
            raise ConfigError(f"{path}: tier {name!r} needs a non-empty \"roles\" list from {list(ROLES)}; {hint}")
        bad = [r for r in roles if r not in ROLES]
        if bad:
            raise ConfigError(f"{path}: tier {name!r} has unknown role(s) {bad}; allowed: {list(ROLES)}")
        m.setdefault("sampling", {})
        m.setdefault("chat_template_kwargs", {})
    return cfg


def load_models(path: Path | str | None = None) -> dict:
    """models.json (validated) with `base_url` resolved (see server_url).

    Path precedence: argument > EVAL_MODELS_JSON env var > eval/models.json. A missing file is a
    ConfigError that points at the template, because models.json is a gitignored local file."""
    path = Path(path) if path else MODELS_PATH
    if not path.is_file():
        raise ConfigError(
            f"{path} not found. It is a local, gitignored file: run `npm run eval:setup` (or copy "
            f"{MODELS_EXAMPLE.name} to {path.name}) and describe your tiers in it; {MODELS_EXAMPLE.name} explains every field.")
    try:
        cfg = checks.load_json(path)
    except ValueError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from None
    cfg = _validate(cfg, path)
    cfg["base_url"] = server_url(cfg)
    return cfg


def tier_roles(cfg: dict, tier: str) -> list[str]:
    return list(cfg["models"][tier].get("roles") or [])


def effective_max_tokens(cfg: dict, mcfg: dict, max_tokens=None) -> int:
    """Answer budget (case > model > default) plus a thinking allowance for tiers that reason.
    Reasoning tokens count toward max_tokens on llama-server, so a 32-token "one word" case would
    otherwise be exhausted by the chain of thought and return an empty answer."""
    base = max_tokens or mcfg.get("max_tokens") or cfg.get("default_max_tokens", DEFAULT_MAX_TOKENS)
    if (mcfg.get("chat_template_kwargs") or {}).get("enable_thinking"):
        base += int(mcfg.get("thinking_allowance", cfg.get("default_thinking_allowance", DEFAULT_THINKING_ALLOWANCE)))
    return base


def request_body(cfg: dict, mcfg: dict, model: str, messages: list, tools=None, max_tokens=None) -> dict:
    body = {
        "model": model, "messages": messages, "stream": False,
        "max_tokens": effective_max_tokens(cfg, mcfg, max_tokens),
    }
    body.update(mcfg.get("sampling", {}))
    if mcfg.get("chat_template_kwargs"):
        body["chat_template_kwargs"] = mcfg["chat_template_kwargs"]
    if tools:
        body["tools"] = tools
    return body


# --------------------------------------------------------------------------- server I/O

def chat(cfg: dict, mcfg: dict, model: str, messages: list, tools=None, max_tokens=None):
    body = request_body(cfg, mcfg, model, messages, tools, max_tokens)
    req = urllib.request.Request(
        cfg["base_url"].rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout_s", DEFAULT_TIMEOUT_S)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from None
    except urllib.error.URLError as e:
        raise ServerUnavailable(f"cannot reach {cfg['base_url']}: {e.reason}") from None
    except TimeoutError:
        raise RuntimeError(f"request timed out after {cfg.get('timeout_s', DEFAULT_TIMEOUT_S)} s") from None
    return data, time.perf_counter() - t0


def unpack(resp: dict):
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return {
        "content": msg.get("content") or "",
        "reasoning_content": msg.get("reasoning_content") or msg.get("reasoning") or "",
        "tool_calls": msg.get("tool_calls") or [],
        "finish_reason": choice.get("finish_reason"),
        "timings": resp.get("timings") or {},
        "usage": resp.get("usage") or {},
    }


# --------------------------------------------------------------------------- multi-turn tool cases

def scripted_result(results: dict, cursors: dict, name: str) -> str:
    val = results.get(name)
    if val is None:
        return f"(tool {name} returned no output)"
    if isinstance(val, list):
        idx = min(cursors.get(name, 0), len(val) - 1)
        cursors[name] = cursors.get(name, 0) + 1
        return str(val[idx])
    return str(val)


def call_matches(call: dict, exp) -> bool:
    exp = {"name": exp} if isinstance(exp, str) else exp
    if call["name"] not in exp["name"].split("|"):
        return False
    args = call.get("args") or {}
    return all(re.search(pat, str(args.get(k, "")), re.I | re.S) for k, pat in (exp.get("args_regex") or {}).items())


def match_sequence(calls: list[dict], expected: list, allow_extra: bool) -> tuple[bool, str]:
    if allow_extra:
        i = 0
        for call in calls:
            if i < len(expected) and call_matches(call, expected[i]):
                i += 1
        return i == len(expected), f"matched {i}/{len(expected)} expected calls in order"
    if len(calls) != len(expected):
        return False, f"expected exactly {len(expected)} calls, got {len(calls)}: {[c['name'] for c in calls]}"
    for call, exp in zip(calls, expected):
        if not call_matches(call, exp):
            return False, f"{call['name']}({call.get('args')}) did not match expected {exp}"
    return True, f"{len(calls)} calls matched exactly"


def drive(cfg, mcfg, model, suite, case, messages) -> dict:
    """Run the conversation until the model answers in text or max_turns is hit.

    Returns the transcript: `calls` (name/args/result per tool call), `turns` (unpacked responses),
    `content` (final text), `problems` found while driving (unknown tool, repeated identical call,
    malformed arguments, max_turns reached), plus timings/usage/wall_s.
    """
    tools = case.get("tools") or suite.get("tools") or []
    valid = {t["function"]["name"] for t in tools}
    scripted = {**suite.get("tool_results", {}), **case.get("tool_results", {})}
    cursors, seen, calls, turns, problems = {}, set(), [], [], []
    final_text, wall, tps = "", 0.0, []
    for _ in range(case.get("max_turns", suite.get("max_turns", DEFAULT_MAX_TURNS))):
        resp, dt = chat(cfg, mcfg, model, messages, tools=tools, max_tokens=case.get("max_tokens"))
        wall += dt
        r = unpack(resp)
        turns.append(r)
        if r["timings"].get("predicted_per_second"):
            tps.append(r["timings"]["predicted_per_second"])
        if not r["tool_calls"]:
            final_text = r["content"]
            break
        assistant = {"role": "assistant", "content": r["content"] or None, "tool_calls": r["tool_calls"]}
        if r["reasoning_content"]:
            assistant["reasoning_content"] = r["reasoning_content"]
        messages.append(assistant)
        for tc in r["tool_calls"]:
            fn = tc.get("function") or {}
            name, raw = fn.get("name"), fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                args, problems = None, problems + [f"malformed JSON arguments for {name}"]
            key = (name, json.dumps(args, sort_keys=True) if args is not None else str(raw))
            if name not in valid:
                problems.append(f"unknown tool {name!r}")
                result = f"ERROR: unknown tool '{name}'. Available tools: {sorted(valid)}"
            else:
                if key in seen:
                    problems.append(f"repeated identical call {name}({args})")
                result = scripted_result(scripted, cursors, name)
            seen.add(key)
            calls.append({"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "name": name, "content": result})
    else:
        problems.append("max_turns reached without a final answer")
    last = turns[-1] if turns else {}
    return {
        "content": final_text, "reasoning_content": last.get("reasoning_content", ""), "calls": calls, "turns": turns,
        "problems": list(dict.fromkeys(problems)),  # drop duplicate notes, keep order
        "timings": {**last.get("timings", {}), "mean_predicted_per_second": sum(tps) / len(tps) if tps else None},
        "usage": last.get("usage", {}), "finish_reason": last.get("finish_reason"), "wall_s": wall,
    }


def sequence_verdict(run: dict, case: dict) -> tuple[bool, str]:
    """Expected call order (and forbidden tools) for a driven transcript."""
    ok, note = match_sequence(run["calls"], case.get("expected_calls", []), case.get("allow_extra", False))
    forbidden = [c["name"] for c in run["calls"] if c["name"] in case.get("forbidden_calls", [])]
    notes = [f"forbidden tool(s) used: {forbidden}"] if forbidden else []
    if not ok:
        notes.append(note)
    return not notes, "; ".join(notes) if notes else note


def final_answer_verdict(run: dict) -> tuple[bool, str]:
    if "max_turns reached without a final answer" in run["problems"]:
        return False, "max_turns reached without a final answer"
    if not run["content"].strip():
        return False, "no final text answer"
    return True, f"final answer of {len(run['content'].split())} words"


def hygiene_verdict(run: dict) -> tuple[bool, str]:
    """No unknown tools, no repeated identical calls, no malformed arguments."""
    bad = [p for p in run["problems"] if not p.startswith("max_turns")]
    return (True, f"{len(run['calls'])} call(s), all valid") if not bad else (False, "; ".join(bad))


def judge(run: dict, case: dict) -> tuple[str, str]:
    """Combine the verdicts into the harness's pass/fail status and note (same rules as before)."""
    problems = list(run["problems"])
    ok_seq, seq_note = sequence_verdict(run, case)
    if not ok_seq:
        problems.append(seq_note)
    ok_final, final_note = final_answer_verdict(run)
    if not ok_final and final_note not in problems:
        problems.append(final_note)
    problems = list(dict.fromkeys(problems))
    status, note = ("fail", "; ".join(problems)) if problems else ("pass", seq_note)
    if status == "pass" and case.get("final_check"):
        status, fnote = checks.evaluate(case["final_check"], run["content"], {"case": case})
        note = f"{seq_note}; final answer -> {fnote}"
    return status, note


def run_tool_case(cfg, mcfg, model, suite, case, messages) -> dict:
    """Drive + judge: the record fields the harness stores for a multi-turn case."""
    run = drive(cfg, mcfg, model, suite, case, messages)
    status, note = judge(run, case)
    return {
        "content": run["content"], "reasoning_content": run["reasoning_content"], "tool_calls": run["calls"],
        "turns": run["turns"], "timings": run["timings"], "usage": run["usage"], "finish_reason": run["finish_reason"],
        "status": status, "note": note, "wall_s": run["wall_s"],
    }
