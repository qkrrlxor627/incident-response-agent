"""에이전트 코드 규칙 단위 테스트 — LLM·MCP·서버 없이 순수 함수만 검증한다.

실행: ./.venv/bin/python3 -m pytest tests -q
근거: bench/results/before.md (Before 측정에서 발견한 문제 3-1, 3-2, 3-6)
"""
import asyncio
import json

import pytest

from agent.graph import (_classify_incident_type, _extract_system_name,
                         gate_node, validate_node)
from agent.ollama_llm import OllamaFastLLM
from agent.systems import mentioned_systems


def mon(*alerts, status="degraded"):
    """research_node가 collected에 넣는 모니터링 결과 모양."""
    return {"source": "monitoring", "data": {"status": status, "alerts": list(alerts)}}


# ── 시스템명 추출 ────────────────────────────────────────────────────────
def test_extract_system_name_passes_every_mentioned_system():
    # [P1 AFTER] Before는 첫 시스템 1개("gateway-service")만 MCP Prompt에 넘겼다
    assert _extract_system_name("gateway-service에서 payments-service로 타임아웃") == "gateway-service, payments-service"


def test_extract_system_name_falls_back_to_auth_service():
    assert _extract_system_name("로그인 응답이 느려요") == "auth-service"
    assert _extract_system_name("billing-service 응답이 느려요") == "auth-service"


def test_mentioned_systems_keeps_mention_order():
    # [#14 AFTER] Before의 _guess_targets는 알파벳 정렬(['auth-service', 'web-01'])이라 '먼저 말한 시스템'을 잃었다
    assert mentioned_systems("web-01 CPU 급증, auth-service 커넥션 풀") == ["web-01", "auth-service"]
    assert mentioned_systems("시스템 이름 없음") == []


# ── incident_type 분류 규칙 (graph._INCIDENT_TYPE_RULES) ─────────────────
@pytest.mark.parametrize("alerts, expected", [
    (["p95 latency 2.4s (threshold 1.0s)"], "high-latency"),
    (["CPU 91% (threshold 80%)"], "cpu-spike"),
    (["heap near limit"], "memory-leak"),
    (["upstream timeout to payments-service (504)"], "network-timeout"),
    (["disk usage 95% on /var/log"], "disk-full"),
])
def test_classify_by_alert_keyword(alerts, expected):
    assert _classify_incident_type([mon(*alerts)]) == expected


def test_classify_falls_back_to_db_down_when_nothing_matches():
    # before.md 3-2: 정상(web-01)만 조사하면 규칙에 안 걸려 db-down으로 빠진다
    assert _classify_incident_type([mon(status="healthy")]) == "db-down"


def test_classify_rule_order_wins_when_alerts_are_combined():
    # before.md 3-2 참고: 여러 시스템 alerts가 합쳐지면 규칙 목록 앞쪽(latency)이 이긴다
    collected = [mon("CPU 91% (threshold 80%)"), mon("p95 latency 2.4s")]
    assert _classify_incident_type(collected) == "high-latency"


# ── gate (교안 7단원 권위 게이트) ────────────────────────────────────────
TASKS = [{"id": "t0", "agent": "research"}, {"id": "ta", "agent": "analysis"}]


def test_gate_removes_analysis_when_not_needed():
    out = asyncio.run(gate_node({"tasks": TASKS, "needs_analysis": False, "events": []}, None))
    assert [t["agent"] for t in out["tasks"]] == ["research"]
    assert out["gate_removed"] == 1


def test_gate_keeps_analysis_when_needed():
    out = asyncio.run(gate_node({"tasks": TASKS, "needs_analysis": True, "events": []}, None))
    assert len(out["tasks"]) == 2 and out["gate_removed"] == 0


# ── validate (교안 9단원) ───────────────────────────────────────────────
def run_validate(draft, attempts=0):
    return asyncio.run(validate_node({"draft": draft, "validation_attempts": attempts, "events": []}, None))


def test_validate_rejects_short_or_unnumbered_draft():
    assert run_validate("너무 짧음")["validation_feedback"] is not None


def test_validate_accepts_numbered_draft():
    assert run_validate("1) 모니터링 확인 2) 커넥션 풀 점검 3) 재발 방지 문서화")["validation_feedback"] is None


def test_validate_forces_pass_on_third_attempt():
    # 실모델 무한 재작성 방지 — 3번째 시도는 내용과 상관없이 통과
    assert run_validate("짧음", attempts=2)["validation_feedback"] is None


# ── P1 버그 고정: 여러 시스템을 말해도 1개만 조사 (before.md 3-1) ─────────
# [P1 AFTER] 고쳐서 XPASS가 났으므로 xfail 마커를 지웠다 → 이제 정식 회귀 테스트다
def test_plan_researches_every_mentioned_system(monkeypatch):
    """모델이 research task를 1개만 내도, 쿼리에 나온 시스템은 모두 조사돼야 한다."""
    llm = OllamaFastLLM("test-model", 0.0)
    one_task = json.dumps({"needs_analysis": False,
                           "tasks": [{"agent": "research", "target": "web-01"}]})
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: (one_task, {"usd": 0.0}))
    result, _ = llm.plan("web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘", "절차")
    targets = sorted(t["target"] for t in result["tasks"] if t["agent"] == "research")
    assert targets == ["auth-service", "web-01"]


@pytest.mark.parametrize("model_tasks", [
    [],                                                  # B: research 0개 (Before에도 복구됨)
    [{"agent": "research", "target": "web-01"}],         # A: 1개만 냄 (Before 누락)
    [{"agent": "research", "target": "auth_service"}],   # C: 오타 (Before는 web-01로 바뀌어 누락)
    [{"agent": "research", "target": "auth-service"}, {"agent": "research", "target": "web-01"}],  # D
])
def test_plan_recovers_every_system_in_mention_order(monkeypatch, model_tasks):
    """P1 원인 분석의 stub 실험 A~D를 그대로 고정한다. 4경우 모두 언급 순서대로 2개."""
    llm = OllamaFastLLM("test-model", 0.0)
    out = json.dumps({"needs_analysis": False, "tasks": model_tasks})
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: (out, {"usd": 0.0}))
    result, _ = llm.plan("web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘", "절차")
    assert [t["target"] for t in result["tasks"] if t["agent"] == "research"] == ["web-01", "auth-service"]


def test_plan_keeps_default_system_when_nothing_mentioned(monkeypatch):
    llm = OllamaFastLLM("test-model", 0.0)
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: ('{"needs_analysis": false, "tasks": []}', {"usd": 0.0}))
    result, _ = llm.plan("로그인 응답이 느려요", "절차")
    assert [t["target"] for t in result["tasks"]] == ["auth-service"]
