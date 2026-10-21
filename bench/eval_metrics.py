"""정답 세트(bench/eval_set.json) 기준 heuristic 채점 — rescore.py와 eval_langsmith.py가 같이 쓴다.

지표 (미션 C4 "검색 정확도" = runbook을 고르는 단계의 정확도로 정의):
  - route_ok        : route가 기대값과 같은가
  - type_ok         : incident_type(=runbook)이 기대값과 같은가. 기대값 null이면 runbook이 없어야 정답
  - system_recall   : 기대 시스템 중 실제로 조사한 비율 (기대 0개면 None)
  - system_precision: 조사한 시스템 중 기대 시스템 비율 (기대 0개인데 조사했으면 0.0)
  - topic_coverage  : 기대 토픽이 답변에 들어간 비율 (토픽 0개면 None)
"""
import json
from pathlib import Path

EVAL_SET = Path(__file__).resolve().parent / "eval_set.json"


# [74% 흐름 ①-1] eval_set.json의 items를 id별 dict로 만든다. 호출하는 곳: bench/rescore.py:21
def load_expected() -> dict[str, dict]:
    return {it["id"]: it for it in json.loads(EVAL_SET.read_text())["items"]}


# [74% 흐름 ④-1] 한 건 채점. 호출하는 곳: bench/rescore.py:35
def score(exp: dict, route: str | None, runbook: str | None,
          monitored: list[str] | None, reply: str | None) -> dict:
    monitored = list(dict.fromkeys(monitored or []))
    want = exp["expected_systems"]
    hit = [s for s in monitored if s in want]
    reply = reply or ""
    topics = exp["expected_topics"]
    return {
        "route_ok": route == exp["expected_route"],
        # ★ 매뉴얼 정답 = 에이전트가 고른 runbook == 정답 expected_incident_type
        #   예: q05 db-down ≠ high-latency → False. 이 값의 평균이 74%(0.739)다
        "type_ok": (runbook == exp["expected_incident_type"]) if exp["expected_route"] == "incident" else None,
        # 조사 범위 = 정답 시스템 중 실제로 조사한 비율 (q05: 2개 중 web-01만 → 0.5)
        "system_recall": round(len(hit) / len(want), 2) if want else None,
        "system_precision": (round(len(hit) / len(monitored), 2) if monitored else None) if want
                            else (0.0 if monitored else None),
        "topic_coverage": round(sum(t.lower() in reply.lower() for t in topics) / len(topics), 2) if topics else None,
    }


# [74% 흐름 ⑤-1] None(채점 대상 아님)은 빼고 평균. 호출하는 곳: bench/rescore.py:49
def mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None
