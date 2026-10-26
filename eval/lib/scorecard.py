"""Markdown scorecard + JSONL writers shared by run_eval.py and the promptfoo afterAll hook.

A record is one dict per case: id, suite, kpi, model, timestamp, prompt, content, reasoning_content,
tool_calls, timings, usage, finish_reason, check, rubric, meta, status (pass / fail / needs-judge),
note, wall_s, error and optionally judge_score.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def tps_value(rec: dict) -> tuple[float | None, bool]:
    """(tokens/s, approximate?) - exact llama-server timings when present, else the effective rate
    (completion tokens / request wall time) that the promptfoo runner can measure."""
    t = rec.get("timings") or {}
    v = t.get("mean_predicted_per_second") or t.get("predicted_per_second")
    if v:
        return float(v), False
    v = t.get("effective_predicted_per_second")
    return (float(v), True) if v else (None, False)


def tps_of(rec: dict) -> str:
    v, approx = tps_value(rec)
    return f"{'~' if approx else ''}{v:.1f}" if v else "-"


def md_cell(s) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def threshold_status(threshold: str, passed: int, judge: int, total: int) -> str:
    if judge:
        return "PENDING JUDGE"
    m = re.match(r"\s*>=\s*(\d+)\s*/\s*(\d+)", threshold or "")
    if not m or not total:
        return "n/a"
    return "MET" if passed / total >= int(m.group(1)) / int(m.group(2)) else "NOT MET"


def write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_scorecard(path: Path, model: str, cfg: dict, mcfg: dict, suites: list[dict], records: list[dict],
                    runner: str = "run_eval.py", tps_label: str = "Mean tok/s") -> None:
    lines = [f"# Scorecard: {model}", "", f"- Run: {datetime.now():%Y-%m-%d %H:%M:%S}", f"- Runner: {runner}",
             f"- Tier roles: {', '.join(mcfg.get('roles') or []) or 'n/a'}; languages: {', '.join(cfg.get('languages') or []) or 'none'}",
             f"- Server: {cfg['base_url']}",
             f"- Sampling: `{json.dumps(mcfg.get('sampling', {}))}`  chat_template_kwargs: `{json.dumps(mcfg.get('chat_template_kwargs', {}))}`",
             "", "## Summary", "", f"| KPI | Suite | Pass | Fail | Needs judge | Score | {tps_label} | Threshold | Status |",
             "|---|---|---|---|---|---|---|---|---|"]
    for suite in suites:
        recs = [r for r in records if r["suite"] == suite["suite"]]
        if not recs:
            continue
        p = sum(r["status"] == "pass" for r in recs)
        f = sum(r["status"] == "fail" for r in recs)
        j = sum(r["status"] == "needs-judge" for r in recs)
        speeds = [tps_value(r) for r in recs]
        speeds = [v for v, _ in speeds if v]
        approx = any(a for v, a in map(tps_value, recs) if v)
        mean = f"{'~' if approx else ''}{sum(speeds) / len(speeds):.1f}" if speeds else "-"
        lines.append(f"| {md_cell(suite.get('kpi'))} | {suite['suite']} | {p} | {f} | {j} | {p}/{len(recs)} | {mean} | "
                     f"{md_cell(suite.get('threshold'))} | {threshold_status(suite.get('threshold', ''), p, j, len(recs))} |")
    if any(tps_value(r)[1] for r in records):
        lines += ["", "`~` marks an effective rate (completion tokens / request wall time, prompt processing included); "
                      "exact llama-server `predicted_per_second` is shown where the response carried timings."]
    judge_rows = []
    for suite in suites:
        recs = [r for r in records if r["suite"] == suite["suite"]]
        if not recs:
            continue
        lines += ["", f"## {suite.get('kpi', suite['suite'])} ({suite['suite']})", "",
                  f"Threshold: {suite.get('threshold', 'n/a')}", "", "| Case | Result | tok/s | Wall s | Note |", "|---|---|---|---|---|"]
        for r in recs:
            wall = f"{r['wall_s']:.1f}" if r.get("wall_s") is not None else "-"
            lines.append(f"| {r['id']} | {r['status']} | {tps_of(r)} | {wall} | {md_cell(r.get('note'))[:400]} |")
            if r["status"] == "needs-judge":
                judge_rows.append(r)
    if judge_rows:
        lines += ["", "## Needs-judge details", "",
                  "Grade each item 1-5 against its rubric (5 = fully meets every point). Record the score in the JSONL "
                  "under `judge_score` or in a copy of this file; a case passes when its score is >= 4.", ""]
        for r in judge_rows:
            prompt = r["prompt"] if isinstance(r["prompt"], str) else json.dumps(r["prompt"], ensure_ascii=False, indent=1)
            content = r.get("content") or "(empty)"
            lines += [f"### {r['suite']} / {r['id']}", "", "**Rubric**", "", r.get("rubric") or "(no rubric given)", "",
                      "**Prompt**", "", "~~~~text", prompt[:3000] + ("\n[... truncated]" if len(prompt) > 3000 else ""), "~~~~", "",
                      "**Model output**", "", "~~~~text", content[:8000] + ("\n[... truncated]" if len(content) > 8000 else ""), "~~~~", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
