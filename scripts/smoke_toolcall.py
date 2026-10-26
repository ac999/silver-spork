"""Smoke test: does a router preset return a structured OpenAI-style tool call, then a final answer?
Usage: <python_cmd> -I scripts/smoke_toolcall.py <Tier> [<Tier> ...] [--base-url http://127.0.0.1:8080]
Tier names are the section names of your llamacpp/model.ini.
Server URL defaults to config/local-ai.json -> server_url.
Pass = response has message.tool_calls with function 'get_weather' and JSON args containing 'city'.
"""
import json, sys, time, urllib.request

import os, pathlib
def _default_base():
    cfg = pathlib.Path(__file__).resolve().parent.parent / "config" / "local-ai.json"
    try:
        return json.loads(cfg.read_text(encoding="utf-8"))["server_url"]
    except Exception:
        return "http://127.0.0.1:8080"
BASE = _default_base()
TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["C", "F"]}},
                       "required": ["city"]},
    },
}]

def call(model, messages, tools=None, max_tokens=512):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.6}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.load(r)
    return data, time.time() - t0

def main():
    global BASE
    argv = sys.argv[1:]
    if "--base-url" in argv:
        i = argv.index("--base-url"); BASE = argv[i + 1]; del argv[i:i + 2]
    models = argv
    if not models:
        print(__doc__); sys.exit(2)
    ok_all = True
    for m in models:
        print(f"\n=== {m} ===")
        msgs = [{"role": "user", "content": "What's the weather in Cluj-Napoca right now, in Celsius? Use the tool."}]
        data, dt = call(m, msgs, TOOLS)
        msg = data["choices"][0]["message"]
        tcs = msg.get("tool_calls") or []
        timings = data.get("timings", {})
        print(f"  load+gen {dt:.1f}s  gen {timings.get('predicted_per_second', 0):.1f} t/s  prompt {timings.get('prompt_per_second', 0):.0f} t/s")
        print(f"  content: {str(msg.get('content'))[:160]!r}")
        print(f"  reasoning_content: {str(msg.get('reasoning_content'))[:120]!r}")
        print(f"  tool_calls: {json.dumps(tcs)[:300]}")
        ok = False
        for tc in tcs:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = None
            if fn.get("name") == "get_weather" and isinstance(args, dict) and "city" in args:
                ok = True
        if ok:
            # second turn: feed the tool result back, expect a final text answer
            msgs.append(msg)
            msgs.append({"role": "tool", "tool_call_id": tcs[0].get("id", "call_0"),
                         "content": json.dumps({"city": "Cluj-Napoca", "temp_c": 14, "sky": "overcast"})})
            data2, _ = call(m, msgs, TOOLS)
            final = data2["choices"][0]["message"]
            has_text = bool((final.get("content") or "").strip()) and not final.get("tool_calls")
            print(f"  final answer: {str(final.get('content'))[:160]!r}")
            print(f"  RESULT: {'PASS' if has_text else 'PARTIAL (tool call ok, no final text)'}")
            ok_all &= has_text
        else:
            print("  RESULT: FAIL (no structured tool call)")
            ok_all = False
    sys.exit(0 if ok_all else 1)

if __name__ == "__main__":
    main()
