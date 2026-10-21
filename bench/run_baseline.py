"""Before 기준선 측정 — 에이전트 코드는 건드리지 않고 /chat 응답만 기록한다.

실행 (백엔드가 :8100에 떠 있어야 함):
    ./.venv/bin/python3 bench/run_baseline.py [--repeat 3] [--tag baseline]

/chat 응답에는 incident_type·runbook 필드가 따로 없으므로 events에서 꺼낸다:
  - incident_type: ReplanCheck(is_sufficient=False).target  (graph._classify_incident_type 결과)
  - runbook:       TaskCompleted(source=runbook).target
  - MCP 호출:      TaskCompleted.source (monitoring=Tool, runbook=Resource).
                   Prompt(incident_analysis_prompt)는 incident 경로에서 항상 호출되지만 events에 없다.
"""
import argparse
import csv
import json
import statistics
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent # 이 경로를 기준으로 질문 목록을 읽고 결과를 bench/results/<tag>_raw.jsonl, bench/results/<tag>_summary.csv에 쓴다
BASE = "http://localhost:8100" # 측정 대상인 백엔드 서버 주소
TIMEOUT = 300.0 # 서버 호출 타임아웃. q01 1회차에서 300초 넘어가면 실패(ok=False)로 기록하고 다음 질문으로 넘어간다


def extract(body: dict) -> dict:
    events = body.get("events", [])
    meta = body.get("metadata", {})
    incident_type = next((e.get("target") for e in events
                          if e.get("type") == "ReplanCheck" and not e.get("is_sufficient")), None)
    runbooks = [e.get("target") for e in events
                if e.get("type") == "TaskCompleted" and e.get("source") == "runbook"]
    monitored = [e.get("target") for e in events
                 if e.get("type") == "TaskCompleted" and e.get("source") == "monitoring"]
    mcp_calls = []
    if meta.get("route") == "incident":
        mcp_calls.append("prompt:incident_analysis_prompt(코드상 항상)")
    mcp_calls += [f"tool:get_monitoring_status({t})" for t in monitored]
    mcp_calls += [f"resource:runbook://incident-response/{t}" for t in runbooks]
    plan = next((e for e in events if e.get("type") == "PlanCreated"), {})
    return {
        "route": meta.get("route"),
        "incident_type": incident_type,
        "runbook": runbooks[0] if runbooks else None,
        "monitored_systems": monitored,
        "plan_targets": plan.get("targets"),
        "mcp_calls": mcp_calls,
        "retry_count": meta.get("retry_count"),
        "replan_rounds": meta.get("replan_rounds"),
        "gate_removed": meta.get("gate_removed"),
        "analysis_ran": any(e.get("type") == "AnalysisCompleted" for e in events),
        "validation_attempts": meta.get("validation_attempts"),
        "cost_usd_virtual": meta.get("cost_usd"),
        "langsmith_run_id": meta.get("langsmith_run_id"),
        "reply_len": len(body.get("reply") or ""),
    }


def post(client: httpx.Client, message: str, thread_id: str) -> tuple[int | None, float, dict | None, str | None]:
    started = time.perf_counter()
    try:
        r = client.post(f"{BASE}/chat", json={"message": message, "thread_id": thread_id})
        ms = (time.perf_counter() - started) * 1000
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        return r.status_code, ms, body, None if r.status_code == 200 else r.text[:300]
    except Exception as e:   # 타임아웃·연결 실패도 결과로 남긴다
        return None, (time.perf_counter() - started) * 1000, None, f"{type(e).__name__}: {e}"


def p95(values: list[float]) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, round(0.95 * (len(s) - 1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--tag", default="baseline")
    args = ap.parse_args()

    # [97% 흐름 ①] 질문 10개를 읽는다 — bench/queries.json (원본: doc/regression_test_queries.md)
    #   ▶ 다음: bench/run_baseline.py:115 질문마다 반복
    queries = json.loads((ROOT / "queries.json").read_text())
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)

    with httpx.Client(timeout=TIMEOUT) as client:
        health = client.get(f"{BASE}/health").json()
        run_meta = {
            "tag": args.tag,
            "started_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "llm_backend": health.get("llm_backend"),
            "fast_llm": health.get("fast_llm"),
            "quality_llm": health.get("quality_llm"),
            "supervisor_version": health.get("supervisor_version"),
            "instance_id": health.get("instance_id"),
            "repeat": args.repeat,
        }
        print("run_meta:", json.dumps(run_meta, ensure_ascii=False))

        # 워밍업 — mcp_client.py의 의도적 flaky(프로세스당 첫 Tool 호출 1회)를 소진하고 모델을 로드한다.
        status, ms, body, err = post(client, "web-01 CPU 급증 원인 진단해줘", f"bench-warmup-{uuid.uuid4().hex[:6]}")
        warmup = {"status": status, "ms": round(ms), "error": err,
                  "retry_count": (body or {}).get("metadata", {}).get("retry_count")}
        run_meta["warmup"] = warmup
        print("warmup:", warmup)

        rows = []
        raw_path = out_dir / f"{args.tag}_raw.jsonl"
        with raw_path.open("w") as raw:
            raw.write(json.dumps({"run_meta": run_meta}, ensure_ascii=False) + "\n")
            # [97% 흐름 ②] 질문 10개 × --repeat(3)회 × 턴 수만큼 보낸다. 다턴(q10)은 같은 thread_id로 이어 보낸다
            #   ▶ 다음: bench/run_baseline.py:121 서버 호출
            for q in queries:
                for rep in range(1, args.repeat + 1):
                    thread_id = f"bench-{q['id']}-r{rep}-{uuid.uuid4().hex[:6]}"
                    for turn_idx, message in enumerate(q["turns"], 1):
                        # [97% 흐름 ③] 실제 서버(:8100) /chat 호출 — 함수 본체: bench/run_baseline.py:62
                        #   ▶ 다음: bench/run_baseline.py:124 응답에서 조사 시스템·runbook 추출
                        status, ms, body, err = post(client, message, thread_id)
                        # [97% 흐름 ④] 응답 events에서 route·조사한 시스템·runbook을 꺼낸다 — 함수 본체: bench/run_baseline.py:29
                        #   (이 값이 raw 파일에 저장되고, 나중에 74% 재채점의 입력이 된다)
                        #   ▶ 다음: bench/run_baseline.py:129 성공 판정
                        info = extract(body) if body else {}
                        is_last = turn_idx == len(q["turns"])
                        # [97% 흐름 ⑤] ★ 성공 판정 = HTTP 200이고 에러가 없으면 성공. 답변 내용(매뉴얼이 맞는지)은 보지 않는다
                        #   → q05처럼 틀린 db-down 매뉴얼을 줘도 ok=True (Before 문제 P8)
                        #   그 아래 if는 q10만 해당: 마지막 답변에 '민수'가 있어야 성공 (queries.json의 expect_in_last_reply)
                        #   ▶ 다음: bench/run_baseline.py:136 기록 저장
                        ok = status == 200 and err is None
                        if ok and is_last and q.get("expect_in_last_reply"):
                            ok = q["expect_in_last_reply"] in (body.get("reply") or "")
                        # [97% 흐름 ⑥] 한 건 기록 → bench/results/<tag>_raw.jsonl에 한 줄씩 저장
                        #   counted = 마지막 턴인가. 다턴은 마지막 턴만 성공률에 센다 → 33건 중 30건
                        #   ▶ 다음: bench/run_baseline.py:164 질문별 성공률, bench/run_baseline.py:176 전체 성공률
                        row = {"query_id": q["id"], "rep": rep, "turn": turn_idx, "thread_id": thread_id,
                               "message": message, "http_status": status, "ms": round(ms),
                               "error": err, "ok": ok, "counted": is_last, **info}
                        rows.append(row)
                        raw.write(json.dumps({**row, "run_meta": {k: run_meta[k] for k in
                                              ("tag", "llm_backend", "fast_llm", "quality_llm")},
                                              "response": body}, ensure_ascii=False) + "\n")
                        raw.flush()
                        print(f"{q['id']} r{rep} t{turn_idx}: {status} {round(ms)}ms "
                              f"route={info.get('route')} type={info.get('incident_type')} "
                              f"runbook={info.get('runbook')} ok={ok}")

    # 쿼리 단위 요약 — 다턴 케이스는 마지막 턴만 성공률·분류에 반영하고, 응답시간은 전 턴 합산
    summary_path = out_dir / f"{args.tag}_summary.csv"
    with summary_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "runs", "success_rate", "ms_median", "ms_p95",
                    "route", "incident_type", "runbook", "monitored_systems", "retry_total",
                    "validation_attempts_median", "expected_route", "expected_incident_type",
                    "llm_backend", "fast_llm", "quality_llm", "started_at"])
        for q in queries:
            qr = [r for r in rows if r["query_id"] == q["id"]]
            per_rep_ms = [sum(r["ms"] for r in qr if r["rep"] == rep) for rep in range(1, args.repeat + 1)]
            last = [r for r in qr if r["counted"]]
            mode = lambda key: Counter(str(r.get(key)) for r in last).most_common()
            # [97% 흐름 ⑦] 질문별 성공률 = ok 건수 / 3 → <tag>_summary.csv의 success_rate 열 (q01만 0.67)
            w.writerow([
                q["id"], len(last), round(sum(r["ok"] for r in last) / len(last), 2),
                round(statistics.median(per_rep_ms)), round(p95(per_rep_ms)),
                mode("route"), mode("incident_type"), mode("runbook"),
                Counter(",".join(r.get("monitored_systems") or []) for r in last).most_common(),
                sum(r.get("retry_count") or 0 for r in last),
                statistics.median([r.get("validation_attempts") or 0 for r in last]),
                q["expected_route"], q["expected_incident_type"],
                run_meta["llm_backend"], run_meta["fast_llm"], run_meta["quality_llm"], run_meta["started_at"],
            ])

    # [97% 흐름 ⑧] ★ 전체 성공률 = counted 30건 중 ok 29건 = 0.97 (실패 1건: q01 1회차 300초 타임아웃)
    #   터미널에 '성공률 0.97'로 출력되고, bench/results/before.md 21번째 줄에 기록했다
    #   ▶ 이어서 74%: bench/rescore.py:21 — 같은 raw 파일을 정답 세트로 다시 채점
    all_ms = [r["ms"] for r in rows]
    counted = [r for r in rows if r["counted"]]
    print(f"\n완료: 호출 {len(rows)}건, 평균 {statistics.mean(all_ms):.0f}ms, "
          f"중앙값 {statistics.median(all_ms):.0f}ms, 성공률 {sum(r['ok'] for r in counted) / len(counted):.2f}")
    print(f"저장: {raw_path}\n      {summary_path}")


if __name__ == "__main__":
    main()
