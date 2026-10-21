"""Before 측정(baseline)의 LangSmith trace에서 증거를 꺼내 텍스트로 저장한다.

실행 (프로젝트 루트에서, .env의 LangSmith 키 사용):
    set -a; source .env; set +a
    ./.venv/bin/python3 -W ignore outputs/before/scripts/fetch_langsmith_evidence.py outputs/before/evidence

run id는 bench/results/baseline_raw.jsonl의 langsmith_run_id 값이다.
q01 1회차(타임아웃)는 응답이 없어 raw에 id가 없으므로, LangSmith에서 시각으로 찾은 id를 쓴다.
"""
import json
import sys
from pathlib import Path

from langsmith import Client

E = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/before/evidence")
E.mkdir(parents=True, exist_ok=True)
Q05_REP1 = "01a157ca-f8a7-7d78-a726-c6920931db05"
Q01_REP1_TIMEOUT = "01a157bc-3f4f-7602-92d7-f1e949e3c114"
Q03_REPS = ["01a157c3-83b3-7b2d-bdea-313838f56360", "01a157c4-977b-77c1-b701-3836ea0843b2",
            "01a157c6-e9e8-7486-a6da-a7a79e39f920"]
NODES = ("route", "plan", "gate", "research", "replan_check", "analysis", "write", "validate", "finalize")

c = Client()


def tree(rid):
    root = c.read_run(rid)
    return root, sorted(c.list_runs(trace_id=root.trace_id), key=lambda r: r.start_time)


def dur(r):
    return round((r.end_time - r.start_time).total_seconds(), 2) if r.end_time else None


# S3: q05 plan 입출력 — 표준 절차 프롬프트에 시스템이 몇 개 들어갔는가
root, runs = tree(Q05_REP1)
plan = next(r for r in runs if r.name == "ollama_fast.plan")
with open(E / "S3_q05_plan_trace.txt", "w") as f:
    f.write("# Before 측정(baseline) q05 1회차 — LangSmith ollama_fast.plan 실행 기록\n")
    f.write(f"# trace: {c.get_run_url(run=root)}\n\n")
    f.write("## 입력 procedure_prompt (MCP Prompt 결과)\n" + plan.inputs["procedure_prompt"] + "\n")
    f.write("## 입력 query\n" + plan.inputs["query"] + "\n\n")
    f.write("## 출력 (코드 정규화 후)\n" + json.dumps(plan.outputs["output"][0], ensure_ascii=False, indent=1) + "\n")

# S4: q05 단계별 소요 시간
with open(E / "S4_q05_node_timing.txt", "w") as f:
    f.write(f"# Before q05 1회차 단계별 소요 시간 (LangSmith trace, 전체 {dur(root)}s)\n")
    for r in runs:
        if r.name in NODES:
            f.write(f"{r.name:14s} {dur(r):7.2f}s  {'#' * int(dur(r))}\n")

# S11: q01 300초 타임아웃 — 어느 LLM 호출에서 멈췄는가
root, runs = tree(Q01_REP1_TIMEOUT)
with open(E / "S11_q01_timeout_trace.txt", "w") as f:
    f.write("# Before q01 1회차 (300초 타임아웃) — LangSmith trace\n")
    f.write(f"# trace: {c.get_run_url(run=root)}\n\n")
    for r in runs:
        if r.run_type == "llm" or r.name == "chat_request":
            err = r.error.splitlines()[0] if r.error else ""
            f.write(f"{r.name:22s} {r.status:8s} {dur(r):8.2f}s  {err}\n")

# S12: q03 응답시간 편차 — write 토큰 수 vs 답변 길이
with open(E / "S12_q03_write_tokens.txt", "w") as f:
    f.write("# Before q03 3회 — write 단계 소요 시간·토큰 vs 답변 길이\n")
    for rep, rid in enumerate(Q03_REPS, 1):
        root, runs = tree(rid)
        w = next(r for r in runs if r.name == "ollama_quality.write")
        out = w.outputs["output"]
        f.write(f"rep{rep}: 전체 {dur(root):6.1f}s | write {dur(w):6.1f}s | "
                f"tokens(prompt+eval) {out[1]['tokens']:5d} | 답변 {len(out[0])}자\n")

print("saved:", *sorted(p.name for p in E.glob("S*_*.txt") if p.stem[:3] in ("S3_", "S4_", "S11", "S12")))
