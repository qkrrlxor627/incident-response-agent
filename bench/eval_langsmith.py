"""LangSmith Dataset + evaluate()로 정확도·답변 품질을 채점한다 (교안 15단원 방식).

- Dataset: bench/queries.json(입력) + bench/eval_set.json(정답) → LangSmith Dataset 1개
- target : 떠 있는 에이전트(:8100)의 /chat을 실제로 호출 (다턴은 같은 thread로 순서대로)
- evaluator: heuristic(eval_metrics.score) + LLM-judge(Ollama qwen3:8b, 무료, 4기준 1~5점)

실행 (백엔드 :8100, Ollama가 떠 있어야 함. .env의 LangSmith 키 사용):
    set -a; source .env; set +a
    ./.venv/bin/python3 bench/eval_langsmith.py --prefix baseline
"""
import argparse
import json
import time
import uuid
from pathlib import Path

import httpx
from langsmith import Client

from eval_metrics import load_expected, score
from run_baseline import extract

ROOT = Path(__file__).resolve().parent
BASE = "http://localhost:8100"
OLLAMA = "http://127.0.0.1:11434/api/chat"
DATASET = "incident-agent-eval-v1"
JUDGE_MODEL = "qwen3:8b"

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {"type": "integer"}, "completeness": {"type": "integer"},
        "clarity": {"type": "integer"}, "domain": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["relevance", "completeness", "clarity", "domain", "reasoning"],
}


def ensure_dataset(client: Client) -> str:
    if client.has_dataset(dataset_name=DATASET):
        return DATASET
    queries = {q["id"]: q for q in json.loads((ROOT / "queries.json").read_text())}
    exp = load_expected()
    ds = client.create_dataset(dataset_name=DATASET,
                               description="incident agent 회귀 질의 10건 + 정답(eval_set.json)")
    client.create_examples(
        dataset_id=ds.id,
        examples=[{"inputs": {"id": qid, "turns": queries[qid]["turns"]},
                   "outputs": {k: v for k, v in exp[qid].items() if k != "id"},
                   "metadata": {"query_id": qid}} for qid in sorted(exp)])
    return DATASET


def target(inputs: dict) -> dict:
    thread = f"eval-{inputs['id']}-{uuid.uuid4().hex[:6]}"
    started = time.perf_counter()
    body, err = None, None
    with httpx.Client(timeout=300.0) as c:
        for msg in inputs["turns"]:
            try:
                r = c.post(f"{BASE}/chat", json={"message": msg, "thread_id": thread})
                body = r.json()
            except Exception as e:  # noqa: BLE001 — 타임아웃도 결과로 남긴다
                body, err = None, f"{type(e).__name__}: {e}"
                break
    info = extract(body) if body else {}
    return {"reply": (body or {}).get("reply"), "route": info.get("route"),
            "runbook": info.get("runbook"), "monitored_systems": info.get("monitored_systems"),
            "error": err, "ms": round((time.perf_counter() - started) * 1000),
            "cost_usd": info.get("cost_usd_virtual"), "retry_count": info.get("retry_count")}


def heuristic(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    s = score(reference_outputs, outputs.get("route"), outputs.get("runbook"),
              outputs.get("monitored_systems"), outputs.get("reply"))
    to_num = lambda v: None if v is None else float(v)
    return {"results": [{"key": k, "score": to_num(v)} for k, v in s.items() if v is not None]}


def llm_judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if not outputs.get("reply"):
        return {"key": "judge_quality", "score": 0.0, "comment": "응답 없음"}
    system = ("당신은 ICT 운영 장애 대응 답변을 채점하는 심사위원이다. 아래 4개 기준을 각각 1~5점 정수로 채점하라. "
              "relevance=질문에 답했는가, completeness=질문에 나온 시스템·증상을 빠짐없이 다뤘는가, "
              "clarity=조치가 명확한가, domain=운영 대응으로 적절하고 근거 없는 수치를 지어내지 않았는가. "
              "정답 정보(기대 조사 시스템, 기대 장애 유형, 근거)를 기준으로 판단하라.")
    user = (f"## 질문\n{inputs['turns'][-1]}\n\n## 정답 정보\n"
            f"- 기대 조사 시스템: {reference_outputs['expected_systems']}\n"
            f"- 기대 장애 유형: {reference_outputs['expected_incident_type']}\n"
            f"- 근거: {reference_outputs['rationale']}\n\n## 채점할 답변\n{outputs['reply']}")
    r = httpx.post(OLLAMA, timeout=300.0, json={
        "model": JUDGE_MODEL, "stream": False, "think": False, "format": JUDGE_SCHEMA,
        "options": {"temperature": 0.0},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    j = json.loads(r.json()["message"]["content"])
    crit = {k: max(1, min(5, int(j[k]))) for k in ("relevance", "completeness", "clarity", "domain")}
    return {"results": [{"key": f"judge_{k}", "score": v / 5} for k, v in crit.items()]
            + [{"key": "judge_quality", "score": round(sum(crit.values()) / 20, 3),
                "comment": j.get("reasoning", "")[:500]}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="실험 이름 접두어 (예: baseline, after)")
    a = ap.parse_args()
    client = Client()
    data = ensure_dataset(client)
    health = httpx.get(f"{BASE}/health", timeout=10).json()
    res = client.evaluate(target, data=data, evaluators=[heuristic, llm_judge],
                          experiment_prefix=a.prefix, max_concurrency=1,
                          metadata={"health": health, "judge_model": JUDGE_MODEL})
    rows = []
    for r in res:
        ex, run = r["example"], r["run"]
        scores = {e.key: e.score for e in r["evaluation_results"]["results"]}
        rows.append({"id": ex.inputs["id"], "ms": (run.outputs or {}).get("ms"),
                     "error": (run.outputs or {}).get("error"), **scores})
    rows.sort(key=lambda x: x["id"])
    out = ROOT / "results" / f"{a.prefix}_langsmith_eval.json"
    out.write_text(json.dumps({"experiment": res.experiment_name, "health": health, "rows": rows},
                              ensure_ascii=False, indent=1))
    keys = ["route_ok", "type_ok", "system_recall", "system_precision", "topic_coverage", "judge_quality"]
    print(f"experiment: {res.experiment_name}")
    for x in rows:
        print(x["id"], x["ms"], " ".join(f"{k}={x.get(k)}" for k in keys), x["error"] or "")
    for k in keys:
        vals = [x[k] for x in rows if x.get(k) is not None]
        print(f"평균 {k}: {round(sum(vals) / len(vals), 3) if vals else None}")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
