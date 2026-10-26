"""promptfoo extension hook: after a run, write the harness-style JSONL + markdown scorecard.

    extensions:
      - file://lib/pf_hooks.py:extension_hook

Output: eval/results/<Tier>_<timestamp>.jsonl and .md (same shape as run_eval.py produces), built
from promptfoo's results so the KPI threshold table and the "Needs-judge details" section exist
for every run, whichever runner made it.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402
import scorecard  # noqa: E402
import toolloop  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def _text(output) -> str:
    if output is None:
        return ""
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def to_record(r: dict) -> dict:
    """One promptfoo EvaluateResult -> one harness record (see lib/scorecard.py)."""
    test = r.get("testCase") or {}
    meta = test.get("metadata") or r.get("metadata") or {}
    vars_ = r.get("vars") or test.get("vars") or {}
    resp = r.get("response") or {}
    rmeta = resp.get("metadata") or {}
    tl = rmeta.get("toolloop") or {}
    grading = r.get("gradingResult") or {}
    comps = grading.get("componentResults") or []
    notes = [c.get("reason", "") for c in comps if c.get("reason")]
    if not comps and grading.get("reason"):
        notes.append(grading["reason"])
    judge_score = next((c.get("score") for c in comps if (c.get("assertion") or {}).get("type") == "llm-rubric"), None)
    # failureReason: 0 = none, 1 = assertion failed (r.error then repeats the reason), 2 = provider/runtime error
    error = resp.get("error") or (r.get("error") if r.get("failureReason") == 2 else None)
    if error:
        status = "fail"
        notes.insert(0, f"error: {error}")
    elif not r.get("success"):
        status = "fail"
    elif meta.get("needs_judge"):
        status = "needs-judge"
    else:
        status = "pass"
    usage = resp.get("tokenUsage") or {}
    latency = r.get("latencyMs") or resp.get("latencyMs")
    if tl:
        timings = tl.get("timings") or {}
    else:
        timings = {}
        if usage.get("completion") and latency:
            timings = {"effective_predicted_per_second": usage["completion"] / (latency / 1000.0),
                       "completion_tokens": usage["completion"], "latency_ms": latency}
    messages = vars_.get("messages") or []
    case = vars_.get("case") or {}
    return {
        "id": meta.get("case_id") or vars_.get("case_id"), "suite": meta.get("suite") or vars_.get("suite_name"),
        "kpi": meta.get("kpi"), "model": meta.get("tier") or vars_.get("tier"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "prompt": messages if "messages" in case or len(messages) > 2 else (messages[-1]["content"] if messages else r.get("prompt", {}).get("raw")),
        "content": tl.get("content") if tl else _text(resp.get("output")),
        "reasoning_content": tl.get("reasoning_content", ""),
        "tool_calls": tl.get("calls") if tl else (resp.get("output") if isinstance(resp.get("output"), list) else []),
        "turns": tl.get("turns") if tl else None,
        "timings": timings,
        "usage": {"prompt_tokens": usage.get("prompt"), "completion_tokens": usage.get("completion"), "total_tokens": usage.get("total")},
        "finish_reason": resp.get("finishReason") or tl.get("finish_reason"),
        "check": case.get("check") if case.get("expected_calls") is None else {"type": "tool_loop", "final_check": case.get("final_check")},
        "rubric": meta.get("rubric"), "meta": meta.get("meta"),
        "status": status, "note": "; ".join(notes), "wall_s": (tl.get("wall_s") if tl else (latency / 1000.0 if latency else None)),
        "error": error, "judge_score": judge_score, "promptfoo_score": r.get("score"),
    }


# promptfoo calls afterAll more than once per run (the first call can carry partially graded results)
# and each call may land in a fresh Python process, so a per-process timestamp produced two files per run.
# Use stable names per tier: the last call wins and the files are safe to commit as 'latest'.


def write_outputs(results: list[dict], out_dir: Path = RESULTS_DIR) -> tuple[Path, Path] | None:
    records = [to_record(r) for r in results]
    records = [r for r in records if r["id"]]
    if not records:
        return None
    tier = next((r["model"] for r in records if r.get("model")), "unknown")
    cfg = toolloop.load_models()
    mcfg = cfg["models"].get(tier, {})
    suites = checks.load_suites(mcfg.get("roles") or [])
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path, md_path = out_dir / f"{tier}_records.jsonl", out_dir / f"{tier}_scorecard.md"
    # A filtered run (e.g. --filter-pattern "^tools/") only re-runs some cases: merge them into the
    # previous records by case id so the scorecard always covers the whole tier.
    if jsonl_path.exists():
        previous = {}
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                previous[rec.get("id")] = rec
        for rec in records:
            previous[rec["id"]] = rec
        records = list(previous.values())
    scorecard.write_jsonl(jsonl_path, records)
    scorecard.write_scorecard(md_path, tier, cfg, mcfg, suites, records, runner="promptfoo")
    return jsonl_path, md_path


def extension_hook(hook_name: str, context: dict):
    if hook_name != "afterAll":
        return None
    written = write_outputs(context.get("results") or [])
    if written:
        print(f"[pf_hooks] wrote {written[0]}\n[pf_hooks] wrote {written[1]}", file=sys.stderr, flush=True)
    return None
