#!/usr/bin/env python3
"""KPI evaluation harness for local LLMs served by llama.cpp's llama-server (router mode).

Dependency-free fallback runner. The primary runner is promptfoo (see README.md and
promptfooconfig.yaml); both share the code in lib/ (checks, tool loop, scorecard).

Usage (any Python 3.10+; -I keeps the current directory off sys.path):
    python -I run_eval.py --model <Tier> [--suite coding] [--only CASE_ID] [--out results]
    python -I run_eval.py --model <Tier> --list
    python -I run_eval.py --list              # show the tiers defined in models.json

<Tier> is a key of eval/models.json "models" (a llama-server router preset). Its `roles` pick the
suites. One tier per invocation: the router loads a single model at a time, so run the tiers one
after another and never interleave them. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))  # -I does not add the script directory

import checks  # noqa: E402
import scorecard  # noqa: E402
import toolloop  # noqa: E402
from toolloop import ServerUnavailable  # noqa: E402


def run_case(cfg, mcfg, model, suite, case) -> dict:
    messages = checks.build_messages(suite, case)
    rec = {"id": case["id"], "suite": suite["suite"], "kpi": suite.get("kpi", suite["suite"]), "model": model,
           "timestamp": datetime.now().isoformat(timespec="seconds"), "prompt": messages if "messages" in case else messages[-1]["content"],
           "check": case.get("check"), "rubric": case.get("rubric"), "meta": case.get("meta"), "error": None}
    try:
        if case.get("expected_calls") is not None:
            rec.update(toolloop.run_tool_case(cfg, mcfg, model, suite, case, messages))
        else:
            resp, dt = toolloop.chat(cfg, mcfg, model, messages, tools=case.get("tools"), max_tokens=case.get("max_tokens"))
            r = toolloop.unpack(resp)
            status, note = checks.evaluate(case.get("check"), r["content"],
                                           {"case": case, "tools": case.get("tools"), "tool_calls": r["tool_calls"]})
            rec.update(r, status=status, note=note, wall_s=dt)
    except ServerUnavailable:
        raise
    except Exception as e:  # noqa: BLE001 - one bad case must not kill the run
        rec.update(content="", reasoning_content="", tool_calls=[], timings={}, usage={}, status="fail",
                   note=f"error: {e}", error=str(e), wall_s=None)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="tier to run: a key of models.json \"models\" (= llama-server router preset)")
    ap.add_argument("--suite", help="run only this suite (the `suite` field inside tests/*.json)")
    ap.add_argument("--only", help="run only the case whose id equals or starts with this value")
    ap.add_argument("--out", default="results", help="output folder, relative to this script (default: results)")
    ap.add_argument("--base-url", help="override the server URL (config/local-ai.json server_url, else localhost:8080)")
    ap.add_argument("--timeout", type=float, help="override per-request timeout in seconds")
    ap.add_argument("--list", action="store_true", help="list the cases that would run, then exit")
    args = ap.parse_args()

    try:
        cfg = toolloop.load_models()
    except toolloop.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.base_url:
        cfg["base_url"] = args.base_url
    if args.timeout:
        cfg["timeout_s"] = args.timeout
    if not args.model or args.model not in cfg["models"]:
        if args.model:
            print(f"unknown tier {args.model!r}", file=sys.stderr)
        print("tiers in models.json (--model <Tier>):", file=sys.stderr)
        for name, m in cfg["models"].items():
            print(f"  {name:16s} roles={m.get('roles')}", file=sys.stderr)
        return 0 if args.list and not args.model else 2
    mcfg = cfg["models"][args.model]
    suites = checks.load_suites(toolloop.tier_roles(cfg, args.model), args.suite)
    plan = checks.plan(cfg, args.model, args.suite, args.only)
    if not plan:
        print("nothing to run (check --model/--suite/--only)", file=sys.stderr)
        return 2
    if args.list:
        print(f"tier={args.model} roles={toolloop.tier_roles(cfg, args.model)} languages={cfg.get('languages')} "
              f"server={cfg['base_url']} cases={len(plan)}")
        for s, c in plan:
            print(f"{s['suite']:12s} {c['id']}")
        return 0

    out_dir = (HERE / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path, md_path = out_dir / f"{args.model}_{stamp}.jsonl", out_dir / f"{args.model}_{stamp}.md"
    records: list[dict] = []
    print(f"model={args.model} cases={len(plan)} server={cfg['base_url']} -> {jsonl_path.name}")
    try:
        with open(jsonl_path, "a", encoding="utf-8") as jf:
            for i, (suite, case) in enumerate(plan, 1):
                print(f"[{i}/{len(plan)}] {suite['suite']}/{case['id']} ...", end=" ", flush=True)
                rec = run_case(cfg, mcfg, args.model, suite, case)
                records.append(rec)
                jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                jf.flush()
                print(f"{rec['status'].upper():11s} {scorecard.tps_of(rec):>6s} tok/s  {rec['note'][:110]}")
    except ServerUnavailable as e:
        print(f"\nABORT: {e}\nStart llama-server first (router mode on {cfg['base_url']}).", file=sys.stderr)
    except KeyboardInterrupt:
        print("\ninterrupted; writing partial scorecard", file=sys.stderr)
    finally:
        if records:
            scorecard.write_scorecard(md_path, args.model, cfg, mcfg, suites, records)
            print(f"\nwrote {jsonl_path}\nwrote {md_path}")
    passed = sum(r["status"] == "pass" for r in records)
    judge = sum(r["status"] == "needs-judge" for r in records)
    print(f"done: {passed} pass, {len(records) - passed - judge} fail, {judge} needs-judge of {len(plan)} planned")
    return 0 if records and len(records) == len(plan) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
