"""서버(:8199 기본)에 질문을 보내고 route·조사 시스템·runbook·검증 결과·노드별 시간을 한눈에 출력한다.
사용: python ask.py "<질문1>" "<질문2>" ... [--base http://127.0.0.1:8100]"""
import json
import sys
import time

import httpx

args = sys.argv[1:]
base = "http://127.0.0.1:8199"
if "--base" in args:
    i = args.index("--base"); base = args[i + 1]; args = args[:i] + args[i + 2:]
for q in args:
    t = time.perf_counter()
    r = httpx.post(f"{base}/chat", json={"message": q, "thread_id": f"ask-{int(time.time()*1000)}"}, timeout=600)
    d = r.json()
    if r.status_code != 200:
        print(f"[{r.status_code}] {q}\n  {d}\n"); continue
    ev = d["events"]
    mon = [e["target"] for e in ev if e["type"] == "TaskCompleted" and e["source"] == "monitoring"]
    rb = [e["target"] for e in ev if e["type"] == "TaskCompleted" and e["source"] == "runbook"]
    val = [(e["attempt"], e["verdict"], e.get("problems"), (e.get("judge") or {}).get("grounded")) for e in ev if e["type"] == "Validation"]
    print(f"질문: {q}\n  {time.perf_counter()-t:.1f}초 | 조사: {mon} | runbook: {rb or None} | "
          f"분석: {any(e['type']=='AnalysisCompleted' for e in ev)}")
    for a, v, p, g in val:
        print(f"  검증 {a}회차: {v} | judge grounded={g} | 문제={p}")
    print(f"  노드 ms: {json.dumps(d['metadata'].get('timings_ms'))}")
    print(f"  답변: {d['reply'][:160]!r}\n")
