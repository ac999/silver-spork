"""Deterministic checks, suite loading and the needle-in-haystack generator.

Shared by the dependency-free harness (eval/run_eval.py) and the promptfoo runner
(eval/gen_tests.py, eval/lib/pf_asserts.py). Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = EVAL_DIR / "tests"
CHARS_PER_TOKEN = 4
CODE_TEST_TIMEOUT_S = 60
HAYSTACK_DEPTHS = (0.2, 0.5, 0.8)
RE_FLAGS = re.I | re.M

REFUSAL_PHRASES = [
    "i can't help with that", "i cannot help with that", "i can't assist with", "i cannot assist with",
    "i'm unable to help", "i am unable to help", "i'm not able to help", "i won't be able to help",
    "i cannot provide", "i can't provide", "i'm not able to provide", "i must decline", "i cannot comply",
    "i can't comply", "against my guidelines", "violates my guidelines", "i'm sorry, but i can't",
    "i am sorry, but i cannot", "as an ai language model, i cannot", "i cannot fulfill", "i can't fulfill",
]
TEMPLATE_TOKENS = [
    "<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>", "<|eot_id|>", "<|start_header_id|>",
    "<|end_header_id|>", "<|begin_of_text|>", "<|endoftext|>", "<|assistant|>", "<|user|>", "<|system|>",
    "[INST]", "[/INST]", "<|end|>", "<|turn|>",
]
CVE_RE = r"CVE-\d{4}-\d{4,}"

HAYSTACK_PARAGRAPHS = [
    "The municipal archive opens its reading room at nine in the morning and closes at five, except on Wednesdays when it stays open until eight for researchers who work during the day. Visitors must leave bags in the lockers near the entrance and may bring only pencils, laptops and loose paper inside. Requests for boxes stored off-site take two working days to fulfil, so regular users plan their visits around that delay.",
    "Compost heaps work best when green material such as grass clippings and vegetable peelings is layered with brown material such as dry leaves, cardboard and straw. The heap should stay about as damp as a wrung-out sponge; if it smells sour it is too wet and needs turning, and if it stops heating it is probably too dry. A well-managed heap yields usable compost in roughly six months.",
    "Bicycle chains stretch slowly as the pins and rollers wear, and a chain that has stretched beyond one percent will start to wear the cassette teeth as well. A simple gauge pressed into the links shows when replacement is due. Cleaning the chain with a rag and re-oiling it every couple of hundred kilometres, more often in wet weather, extends its life considerably and keeps shifting crisp.",
    "The village grew around a stone bridge built in the eighteenth century to carry salt carts across the river. For two hundred years the toll collected at the bridge paid for the school and the small infirmary. When the railway arrived the carts disappeared, the toll house became a bakery, and the bridge itself was widened once in the 1930s and repaired again after the floods of 1970.",
    "Weather forecasts for mountain regions are notoriously difficult because valleys trap cold air overnight while ridges remain exposed to the wind. Hikers are advised to check the forecast for the summit elevation rather than for the nearest town, to start early, and to turn back if clouds build quickly after midday. Afternoon thunderstorms are common in July and August even when the morning is clear.",
    "A good stock begins with bones roasted until deeply browned, then simmered gently with onion, carrot and celery for at least four hours. The pot should never boil hard, since agitation makes the liquid cloudy. Skimming the surface in the first hour removes most of the fat and foam. The finished stock is strained, cooled quickly and either used within three days or frozen in small portions.",
    "Library members may borrow up to ten items at a time for three weeks, with two renewals allowed unless another member has reserved the item. Overdue notices are sent by email on the day after the due date and again a week later. Lost items are charged at replacement cost plus a small processing fee, and members with outstanding charges above a modest limit cannot borrow until the balance is cleared.",
    "Regional trains on the branch line run every two hours on weekdays and every three hours at weekends, with the last departure well before midnight. The single-track section between the junction and the terminus means that any delay on one service propagates to the opposite direction. Tickets bought on board carry a surcharge unless the station of departure has no working ticket machine.",
    "Sourdough starters are maintained by discarding most of the culture and feeding the remainder with equal weights of flour and water. A starter kept at room temperature needs feeding once or twice a day, while one stored in the refrigerator can go a week between feedings. A healthy starter roughly doubles in volume within six hours of feeding and smells pleasantly sour rather than like acetone.",
    "The community garden allocates plots by lottery each February, with priority given to households that have waited more than a year. Each plot comes with access to the shared tool shed, a water tap and a compost bay. Plot holders agree to keep paths clear, to avoid persistent herbicides and to leave the plot tidy at the end of the season so that it can be reassigned without extra work.",
    "Old photographs fade fastest when exposed to daylight and humidity, so collections are best kept in acid-free sleeves inside closed boxes in a cool, dry room. Handling prints with clean dry hands or cotton gloves prevents fingerprints that become visible years later. Writing on the back with a soft pencil is acceptable; ballpoint ink and adhesive labels should be avoided.",
    "Bread flour differs from plain flour mainly in protein content, which determines how much gluten develops during kneading. Higher protein gives a chewier crumb and a loaf that holds its shape, while lower protein gives a softer, more tender result suited to cakes and pastries. Blending the two allows bakers to tune texture without buying many specialised flours.",
]
HAYSTACK_PROMPT = (
    "Below is a long internal document. Read it carefully.\n\n=== DOCUMENT START ===\n{doc}\n=== DOCUMENT END ===\n\n"
    "Using only the document above, answer this question: {question}\nReply with the answer only."
)


# --------------------------------------------------------------------------- suites

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_suites(roles: list[str], suite_filter: str | None = None, tests_dir: Path = TESTS_DIR) -> list[dict]:
    """Suites from tests/*.json whose `applies_to` (roles, or ["all"]) intersects the tier's `roles`.

    Sorted by file name. `applies_to` uses the role vocabulary from models.example.json
    (reasoning, coding, tools, everyday, creative, security), never tier names."""
    suites = []
    for path in sorted(tests_dir.glob("*.json")):
        suite = load_json(path)
        applies = suite.get("applies_to", ["all"])
        if "all" not in applies and not set(applies) & set(roles):
            continue
        if suite_filter and suite.get("suite") != suite_filter:
            continue
        suite["_file"] = path.name
        suites.append(suite)
    return suites


def case_enabled(case: dict, suite: dict, languages: list[str]) -> bool:
    """Opt-in gates: `lang` (natural language other than English, enabled via models.json
    `languages`) and `requires` (executables that must be on PATH, e.g. ["pwsh"])."""
    lang = case.get("lang", suite.get("lang"))
    if lang and lang.lower() not in [x.lower() for x in languages]:
        return False
    return all(shutil.which(exe) for exe in case.get("requires", suite.get("requires", [])))


def build_haystack(n_tokens: int, facts: list[dict]) -> str:
    """Filler of ~n_tokens (4 chars/token) with each fact planted at 20%/50%/80% depth."""
    target, parts, i, total = n_tokens * CHARS_PER_TOKEN, [], 0, 0
    while total < target:
        parts.append(f"[Section {i + 1}] {HAYSTACK_PARAGRAPHS[i % len(HAYSTACK_PARAGRAPHS)]}")
        total += len(parts[-1]) + 2
        i += 1
    # insert deepest first so earlier indices stay valid
    for depth, fact in sorted(zip(HAYSTACK_DEPTHS, facts), key=lambda p: -p[0]):
        parts.insert(int(len(parts) * depth), fact["fact"])
    return "\n\n".join(parts)


def expand_cases(suite: dict, languages: list[str] | None = None) -> list[dict]:
    """Enabled cases (see case_enabled); haystack cases become one sub-case per planted fact."""
    out = []
    for case in suite["cases"]:
        if not case_enabled(case, suite, languages or []):
            continue
        hs = case.get("haystack")
        if not hs:
            out.append(case)
            continue
        doc = build_haystack(hs["tokens"], hs["facts"])
        for i, fact in enumerate(hs["facts"], 1):
            answer = fact["answer"] if isinstance(fact["answer"], list) else [fact["answer"]]
            out.append({
                "id": f'{case["id"]}_f{i}',
                "prompt": HAYSTACK_PROMPT.format(doc=doc, question=fact["question"]),
                "max_tokens": case.get("max_tokens", 256),
                "check": {"type": "contains_all", "values": answer},
                "meta": {"haystack_tokens": hs["tokens"], "depth": HAYSTACK_DEPTHS[(i - 1) % len(HAYSTACK_DEPTHS)],
                         "approx_chars": len(doc)},
            })
    return out


def build_messages(suite: dict, case: dict) -> list[dict]:
    if "messages" in case:
        return [dict(m) for m in case["messages"]]
    msgs = []
    system = case.get("system", suite.get("system"))
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": case["prompt"] + suite.get("prompt_suffix", "")})
    return msgs


def plan(cfg: dict, tier: str, suite_filter: str | None = None, only: str | None = None) -> list[tuple[dict, dict]]:
    """(suite, expanded case) pairs that run for `tier` (by its roles and the enabled languages), in order."""
    roles = cfg["models"][tier].get("roles") or []
    suites = load_suites(roles, suite_filter)
    languages = cfg.get("languages") or []
    return [(s, c) for s in suites for c in expand_cases(s, languages)
            if not only or c["id"] == only or c["id"].startswith(only)]


# --------------------------------------------------------------------------- deterministic checks

def extract_json(text: str):
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S | re.I)
    for cand in ([m.group(1)] if m else []) + [text.strip()]:
        try:
            return json.loads(cand)
        except Exception:
            pass
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            pass
    return None


def extract_code(text: str, langs: str):
    m = re.search(r"```(?:%s)[^\n]*\n(.*?)```" % langs, text, re.S | re.I)
    if m is None:
        m = re.search(r"```[^\n]*\n(.*?)```", text, re.S)  # fall back to the first fenced block
    return m.group(1) if m else None


def is_garbage_char(ch: str) -> bool:
    o = ord(ch)
    if o < 0x20:
        return ch not in "\n\r\t"
    if o < 0x7F:
        return False
    ok_ranges = ((0xA0, 0x24F), (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2190, 0x21FF), (0x2200, 0x22FF),
                 (0x2500, 0x25FF), (0x2600, 0x26FF), (0x2700, 0x27BF))
    return not any(lo <= o <= hi for lo, hi in ok_ranges)


def chk_integrity(text: str, spec: dict) -> tuple[str, str]:
    if not text.strip():
        return "fail", "empty output"
    for tok in TEMPLATE_TOKENS:
        if tok in text:
            return "fail", f"chat-template token {tok!r} in output"
    win, max_rep = spec.get("window", 40), spec.get("max_repeats", 4)
    norm = re.sub(r"\s+", " ", text)
    counts: dict[str, int] = {}
    for i in range(max(0, len(norm) - win + 1)):
        s = norm[i:i + win]
        counts[s] = counts.get(s, 0) + 1
    if counts:
        worst, n = max(counts.items(), key=lambda kv: kv[1])
        if n >= max_rep:
            return "fail", f"{win}-char substring repeated {n}x: {worst[:30]!r}..."
    visible = [c for c in text if not c.isspace()]
    ratio = sum(map(is_garbage_char, visible)) / max(1, len(visible))
    if ratio > spec.get("max_garbage_ratio", 0.20):
        return "fail", f"non-ASCII garbage ratio {ratio:.0%}"
    return "pass", f"clean ({len(text.split())} words, garbage {ratio:.1%})"


def chk_tool_call(ctx: dict, spec: dict) -> tuple[str, str]:
    valid = {t["function"]["name"] for t in ctx.get("tools") or []}
    calls = ctx.get("tool_calls") or []
    names = [c.get("function", {}).get("name") for c in calls]
    bad = [n for n in names if n not in valid]
    if bad:
        return "fail", f"hallucinated tool name(s): {bad}"
    for c in calls:
        if c.get("function", {}).get("name") != spec["name"]:
            continue
        try:
            args = json.loads(c["function"].get("arguments") or "{}")
        except Exception:
            return "fail", "arguments are not valid JSON"
        missing = [k for k in spec.get("required_args", []) if k not in args]
        return ("pass", f"called {spec['name']} with {sorted(args)}") if not missing else ("fail", f"missing args {missing}")
    return "fail", f"expected a call to {spec['name']}, got {names or 'no tool calls'}"


def run_code_tests(text: str, case: dict, lang: str) -> tuple[str, str]:
    code = extract_code(text, "python|py" if lang == "python" else "powershell|ps1|pwsh|ps")
    if code is None:
        return "fail", "no fenced code block in output"
    ext, enc = (".py", "utf-8") if lang == "python" else (".ps1", "utf-8-sig")
    with tempfile.TemporaryDirectory(prefix="eval_") as td:
        path = Path(td) / f"solution{ext}"
        path.write_text(code.rstrip() + "\n\n" + case.get("test_code", "") + "\n", encoding=enc)
        # The model's code runs under the interpreter that runs the harness (isolated mode); PowerShell
        # cases need pwsh (PowerShell 7) on PATH and declare `"requires": ["pwsh"]` so they are skipped otherwise.
        cmd = ([sys.executable, "-I", str(path)] if lang == "python"
               else ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(path)])
        env = {**os.environ, "NO_COLOR": "1", "TERM": "dumb"}  # keep ANSI colour codes out of the notes
        try:
            p = subprocess.run(cmd, cwd=td, capture_output=True, text=True, timeout=CODE_TEST_TIMEOUT_S,
                               encoding="utf-8", errors="replace", env=env)
        except subprocess.TimeoutExpired:
            return "fail", f"tests timed out after {CODE_TEST_TIMEOUT_S} s"
        except FileNotFoundError as e:
            return "fail", f"interpreter not found: {e}"
    if p.returncode == 0:
        return "pass", "tests passed"
    tail = " | ".join((p.stdout + p.stderr).strip().splitlines()[-3:])
    return "fail", f"exit {p.returncode}: {tail[:300]}"


def run_check(spec: dict, text: str, ctx: dict) -> tuple[str, str]:
    """One check spec against the model text. ctx: {"case", "tools", "tool_calls"} as needed."""
    t, body = spec["type"], text.strip()
    if t == "judge":
        return "needs-judge", "see rubric"
    if t == "contains_all":
        low = body.lower()
        missing = [v for v in spec["values"] if v.lower() not in low]
        return ("pass", "all present") if not missing else ("fail", f"missing {missing}")
    if t == "regex":
        return ("pass", "matched") if re.search(spec["pattern"], body, RE_FLAGS) else ("fail", f"no match for /{spec['pattern']}/")
    if t in ("not_regex", "no_fabricated_cve"):
        pat = spec.get("pattern", CVE_RE)
        m = re.search(pat, body, RE_FLAGS)
        return ("fail", f"forbidden match {m.group(0)!r}") if m else ("pass", "absent")
    if t == "regex_count":
        n = len(re.findall(spec["pattern"], body, RE_FLAGS))
        lo, hi = spec.get("min", 0), spec.get("max", 10 ** 9)
        return ("pass", f"{n} matches") if lo <= n <= hi else ("fail", f"{n} matches, wanted {lo}..{hi}")
    if t == "json_schema_keys":
        obj = extract_json(body)
        if not isinstance(obj, dict):
            return "fail", "output is not a JSON object"
        want, got = set(spec["keys"]), set(obj)
        return ("pass", "exact keys") if want == got else ("fail", f"extra {sorted(got - want)}, missing {sorted(want - got)}")
    if t == "exact_word_count":
        n, want, tol = len(body.split()), spec["count"], spec.get("tolerance", 0)
        return ("pass", f"{n} words") if abs(n - want) <= tol else ("fail", f"{n} words, wanted {want}+-{tol}")
    if t == "regex_matches_samples":
        cand = body.strip("`").strip()
        if not re.fullmatch(r"\S{1,200}", cand):
            return "fail", "output is not a single bare regex"
        try:
            rx = re.compile(cand)
        except re.error as e:
            return "fail", f"not a valid regex: {e}"
        bad = [s for s in spec.get("should_match", []) if not rx.fullmatch(s)]
        bad += [f"!{s}" for s in spec.get("should_not_match", []) if rx.fullmatch(s)]
        return ("pass", "all samples behave") if not bad else ("fail", f"wrong on {bad}")
    if t == "no_refusal":
        low = body.lower()
        hit = next((p for p in REFUSAL_PHRASES if p in low), None)
        return ("fail", f"refusal phrase {hit!r}") if hit else ("pass", "no refusal")
    if t == "integrity":
        return chk_integrity(text, spec)
    if t == "tool_call":
        return chk_tool_call(ctx, spec)
    if t == "python_tests":
        return run_code_tests(text, ctx["case"], "python")
    if t == "powershell_tests":
        return run_code_tests(text, ctx["case"], "powershell")
    return "fail", f"unknown check type {t!r}"


def as_specs(checks) -> list[dict]:
    """Normalise a case's `check` field (object, list or missing) to a list of specs."""
    return checks if isinstance(checks, list) else [checks or {"type": "judge"}]


def evaluate(checks, text: str, ctx: dict) -> tuple[str, str]:
    specs = as_specs(checks)
    results = [run_check(spec, text, ctx) for spec in specs]
    statuses = [s for s, _ in results]
    final = "fail" if "fail" in statuses else "needs-judge" if "needs-judge" in statuses else "pass"
    return final, "; ".join(f"{spec['type']}: {note}" for spec, (_, note) in zip(specs, results))
