"""실모델 서버(:8199)에 장애 질문 1건을 보내는 동안 /health 응답 시간을 0.5초 간격으로 잰다 (P4 After 증거).
Before 증거와 같은 방식: outputs/before/evidence/S5 (최대 1.73초)."""
import json, sys, threading, time
import httpx
BASE = "http://127.0.0.1:8199"
q = sys.argv[1]
rows, stop = [], threading.Event()
def probe():
    with httpx.Client(timeout=30) as c:
        while not stop.is_set():
            t = time.perf_counter(); c.get(f"{BASE}/health"); rows.append(round((time.perf_counter() - t) * 1000, 1)); time.sleep(0.5)
th = threading.Thread(target=probe); th.start()
t = time.perf_counter()
r = httpx.post(f"{BASE}/chat", json={"message": q, "thread_id": f"probe-{time.time()}"}, timeout=600).json()
total = time.perf_counter() - t
stop.set(); th.join()
ev = [e["type"] + (f"({e.get('target')})" if e.get("target") else "") + (f"[{e.get('reason')}]" if e.get("reason") else "") for e in r["events"]]
print(f"질문: {q}\n총 응답 시간: {total:.1f}초\n노드별 ms: {json.dumps(r['metadata'].get('timings_ms'), ensure_ascii=False)}")
print(f"이벤트: {' → '.join(ev)}")
print(f"/health 측정 {len(rows)}회: 최대 {max(rows)}ms, 중앙값 {sorted(rows)[len(rows)//2]}ms (Before S5: 최대 1730ms)")
print(f"답변 앞부분: {r['reply'][:150]!r}")
