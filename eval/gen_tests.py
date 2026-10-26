"""promptfoo test generator: turns eval/tests/*.json into promptfoo test cases for ONE tier.

Referenced from promptfooconfig.yaml as

    tests:
      path: file://gen_tests.py:generate_tests
      config: { tier: "<Tier>", grader: "" }

The tier (a key of models.json `models`, i.e. a llama-server router preset) comes from PF_TIER;
its `roles` select the suites (tests/*.json `applies_to`) and models.json `languages` enables
the opt-in `lang` cases.

The JSON suites stay the single source of truth (prompts, checks, rubrics, tool scripts); this
module only maps them onto promptfoo vars / assertions / metadata. Standard library only.

Check mapping
  contains_all                  -> icontains-all (built-in; same case-insensitive semantics)
  every other deterministic type-> python: lib/pf_asserts.py:check with the original spec in
                                   `config.spec`, so lib/checks.py runs exactly the harness code
                                   (Python regex syntax and IGNORECASE|MULTILINE are preserved;
                                   promptfoo's regex/not-regex use JS RegExp semantics)
  judge                         -> llm-rubric when a grader is configured (GRADER env var / config
                                   `grader`); otherwise the rubric goes to metadata.rubric with
                                   metadata.needs_judge = true and no assertion is emitted
  multi-turn tool cases         -> provider lib/pf_toolloop_provider.py + python assertions
                                   tool_sequence / tool_hygiene / tool_final_answer (+ final_check)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import checks  # noqa: E402
import toolloop  # noqa: E402

TOOLLOOP_PROVIDER = "file://lib/pf_toolloop_provider.py"
ASSERTS = "file://lib/pf_asserts.py"
TOOLLOOP_TIMEOUT_MS = 30 * 60 * 1000  # whole multi-turn scenario, up to 8 server round trips


def _grader_provider(grader: str, cfg: dict):
    """GRADER value -> assertion-level provider.

    - a tier name from models.json: that preset on the local llama-server (swaps the resident model!)
    - "default": no assertion-level provider; promptfoo's --grader / defaultTest / default applies
    - anything else: used verbatim as a promptfoo provider id (e.g. anthropic:messages:<model>)
    """
    if grader in cfg["models"]:
        m = cfg["models"][grader]
        passthrough = {k: v for k, v in m.get("sampling", {}).items() if k not in ("temperature", "top_p")}
        if m.get("chat_template_kwargs"):
            passthrough["chat_template_kwargs"] = m["chat_template_kwargs"]
        config = {"apiBaseUrl": cfg["base_url"] + "/v1", "apiKeyRequired": False, "useDefaultApiKey": False,
                  "omitDefaults": True, "showThinking": False, "max_tokens": m.get("max_tokens") or 2048}
        config.update({k: v for k, v in m.get("sampling", {}).items() if k in ("temperature", "top_p")})
        if passthrough:
            config["passthrough"] = passthrough
        return {"id": f"openai:chat:{grader}", "label": f"{grader} (grader)", "config": config}
    if grader.lower() == "default":
        return None
    return grader


def _deterministic_assert(spec: dict) -> dict:
    if spec["type"] == "contains_all":
        return {"type": "icontains-all", "value": list(spec["values"]), "metric": "contains_all"}
    return {"type": "python", "value": f"{ASSERTS}:check", "config": {"spec": spec}, "metric": spec["type"]}


def _slim_case(case: dict) -> dict:
    """The case without its prompt text (already in vars.messages) to keep vars small."""
    return {k: v for k, v in case.items() if k not in ("prompt", "messages")}


def _slim_suite(suite: dict) -> dict:
    keys = ("suite", "kpi", "threshold", "system", "prompt_suffix", "tools", "tool_results", "max_turns")
    return {k: suite[k] for k in keys if k in suite}


def make_test(tier: str, cfg: dict, suite: dict, case: dict, grader: str) -> dict:
    mcfg = cfg["models"][tier]
    messages = checks.build_messages(suite, case)
    is_tool_case = case.get("expected_calls") is not None
    tools = case.get("tools") or (suite.get("tools") if is_tool_case else None) or []
    max_tokens = toolloop.effective_max_tokens(cfg, mcfg, case.get("max_tokens"))
    specs = checks.as_specs(case.get("final_check")) if is_tool_case and case.get("final_check") else []
    if not is_tool_case:
        specs = checks.as_specs(case.get("check"))

    asserts, needs_judge = [], False
    if is_tool_case:
        asserts += [{"type": "python", "value": f"{ASSERTS}:tool_sequence", "metric": "tool_sequence"},
                    {"type": "python", "value": f"{ASSERTS}:tool_hygiene", "metric": "tool_hygiene"},
                    {"type": "python", "value": f"{ASSERTS}:tool_final_answer", "metric": "tool_final_answer"}]
    for spec in specs:
        if spec["type"] != "judge":
            asserts.append(_deterministic_assert(spec))
        elif grader:
            a = {"type": "llm-rubric", "value": case.get("rubric") or "(no rubric given)", "metric": "judge"}
            provider = _grader_provider(grader, cfg)
            if provider is not None:
                a["provider"] = provider
            asserts.append(a)
        else:
            needs_judge = True

    test = {
        "description": f"{suite['suite']}/{case['id']}" + (" [needs-judge]" if needs_judge else ""),
        "vars": {
            "tier": tier, "case_id": case["id"], "suite_name": suite["suite"], "messages": messages,
            "max_tokens": max_tokens, "tools": tools, "case": _slim_case(case), "suite": _slim_suite(suite),
        },
        "assert": asserts,
        "metadata": {
            "tier": tier, "suite": suite["suite"], "kpi": suite.get("kpi", suite["suite"]),
            "threshold": suite.get("threshold"), "case_id": case["id"],
            "check_types": sorted({s["type"] for s in specs} | ({"tool_loop"} if is_tool_case else set())),
            "needs_judge": needs_judge, "rubric": case.get("rubric"), "meta": case.get("meta"),
        },
    }
    if is_tool_case:
        test["provider"] = {"id": TOOLLOOP_PROVIDER, "label": f"{tier} (tool loop)",
                            "config": {"tier": tier, "timeout": TOOLLOOP_TIMEOUT_MS}}
    return test


def generate_tests(config: dict | None = None) -> list[dict]:
    config = config or {}
    tier = (config.get("tier") or os.environ.get("PF_TIER") or "").strip()
    grader = (config.get("grader") or os.environ.get("GRADER") or "").strip()
    cfg = toolloop.load_models()
    if tier not in cfg["models"]:
        raise ValueError(f"unknown tier {tier!r}; set PF_TIER (promptfoo --env-file eval/tiers/<Tier>.env) "
                         f"to one of {sorted(cfg['models'])} (the keys of models.json \"models\")")
    return [make_test(tier, cfg, suite, case, grader) for suite, case in checks.plan(cfg, tier)]


def main(argv: list[str]) -> int:
    """List the promptfoo tests for one tier without calling the server (npm run eval:list -- <Tier>)."""
    import json
    try:
        cfg = toolloop.load_models()
    except toolloop.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    tier = (argv[1] if len(argv) > 1 else os.environ.get("PF_TIER") or "").strip()
    if tier not in cfg["models"]:
        print("usage: gen_tests.py <Tier>   (or set PF_TIER)\n\ntiers in models.json:", file=sys.stderr)
        for name, m in cfg["models"].items():
            print(f"  {name:16s} roles={m.get('roles')}", file=sys.stderr)
        return 2
    tests = generate_tests({"tier": tier, "grader": os.environ.get("GRADER", "")})
    print(f"tier={tier} roles={toolloop.tier_roles(cfg, tier)} languages={cfg.get('languages')} server={cfg['base_url']}")
    for t in tests:
        print(f"{t['description']:45s} asserts={[a['type'] + ':' + a.get('metric', '') for a in t['assert']]}")
    print(f"{len(tests)} tests, {len(json.dumps(tests)) // 1024} KB of vars")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
