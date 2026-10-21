"""에이전트 코드 규칙 단위 테스트 — LLM·MCP·서버 없이 순수 함수만 검증한다.

실행: ./.venv/bin/python3 -m pytest tests -q
근거: bench/results/before.md (Before 측정에서 발견한 문제 3-1, 3-2, 3-6)
"""
import asyncio
import json

import pytest

from agent.graph import (_classify_incident_type, _extract_system_name,
                         gate_node, replan_check_node, validate_node)
from agent.ollama_llm import OllamaFastLLM
from agent.systems import mentioned_systems


def fake_chat(content):
    """[P4 AFTER] _chat이 async def가 됐으므로 가짜 함수도 코루틴이어야 한다 (Ollama 호출 없음)."""
    async def _chat(*a, **k):
        return content, {"usd": 0.0}
    return _chat


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


def test_classify_returns_none_when_every_system_is_healthy():
    # [P2 AFTER] Before는 정상(web-01)만 조사하면 규칙에 안 걸려 db-down으로 빠졌다
    assert _classify_incident_type([mon(status="healthy")]) is None
    assert _classify_incident_type([mon("System 'billing-service' not found", status="unknown")]) is None


def test_classify_uses_first_abnormal_system_in_mention_order():
    # [P2 AFTER] Before는 alerts를 합친 뒤 규칙 목록 앞쪽(latency)이 이겼다 → 이제는 먼저 나온 이상 시스템 기준
    collected = [mon("CPU 91% (threshold 80%)"), mon("p95 latency 2.4s")]
    assert _classify_incident_type(collected) == "cpu-spike"


def test_classify_q05_skips_healthy_primary_system():
    # q05: web-01(정상, 알림 없음) → auth-service(latency, connection pool) → high-latency (Before: db-down 3/3)
    collected = [mon(status="healthy"), mon("p95 latency 2.4s (threshold 1.0s)", "connection pool 92% used")]
    assert _classify_incident_type(collected) == "high-latency"


def test_replan_check_adds_no_runbook_when_nothing_is_wrong():
    state = {"query": "billing-service 응답이 느려요", "events": [], "replan_rounds": 0, "collected": []}
    out = asyncio.run(replan_check_node(state, None))
    assert out["events"][-1]["is_sufficient"] is True and "tasks" not in out
    assert "billing-service" in out["collected"][-1]["data"]


def test_plan_skips_unmonitored_system(monkeypatch):
    # q08: 모델이 auth-service를 골라도 감시 대상이 아닌 billing-service만 나온 질문이면 조사하지 않는다
    llm = OllamaFastLLM("test-model", 0.0)
    out = json.dumps({"needs_analysis": False, "tasks": [{"agent": "research", "target": "auth-service"}]})
    monkeypatch.setattr(llm, "_chat", fake_chat(out))
    result, _ = asyncio.run(llm.plan("billing-service 응답이 느려요", "절차"))
    assert [t for t in result["tasks"] if t["agent"] == "research"] == []


# ── gate (교안 7단원 권위 게이트) ────────────────────────────────────────
TASKS = [{"id": "t0", "agent": "research"}, {"id": "ta", "agent": "analysis"}]
TASKS_2 = [{"id": "t0", "agent": "research"}, {"id": "t1", "agent": "research"}, {"id": "ta", "agent": "analysis"}]


def test_gate_removes_analysis_when_not_needed():
    out = asyncio.run(gate_node({"tasks": TASKS, "needs_analysis": False, "events": []}, None))
    assert [t["agent"] for t in out["tasks"]] == ["research"]
    assert out["gate_removed"] == 1


def test_gate_keeps_analysis_when_needed_and_two_systems():
    out = asyncio.run(gate_node({"tasks": TASKS_2, "needs_analysis": True, "events": []}, None))
    assert len(out["tasks"]) == 3 and out["gate_removed"] == 0


def test_gate_removes_analysis_for_single_system_even_if_model_wants_it():
    # [P3 AFTER] Before는 모델이 true라고 하면 시스템 1개여도 분석을 돌렸다 (q01 300초 정지의 시작점)
    out = asyncio.run(gate_node({"tasks": TASKS, "needs_analysis": True, "events": []}, None))
    assert out["gate_removed"] == 1 and out["events"][-1]["reason"] == "research 1개 < 2"


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
    monkeypatch.setattr(llm, "_chat", fake_chat(one_task))
    result, _ = asyncio.run(llm.plan("web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘", "절차"))
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
    monkeypatch.setattr(llm, "_chat", fake_chat(out))
    result, _ = asyncio.run(llm.plan("web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘", "절차"))
    assert [t["target"] for t in result["tasks"] if t["agent"] == "research"] == ["web-01", "auth-service"]


def test_plan_keeps_default_system_when_nothing_mentioned(monkeypatch):
    llm = OllamaFastLLM("test-model", 0.0)
    monkeypatch.setattr(llm, "_chat", fake_chat('{"needs_analysis": false, "tasks": []}'))
    result, _ = asyncio.run(llm.plan("로그인 응답이 느려요", "절차"))
    assert [t["target"] for t in result["tasks"]] == ["auth-service"]


# ── P4·P9: 비동기 호출과 노드 시간 기록 ─────────────────────────────────
def test_fast_llm_methods_are_coroutines():
    # [P4 AFTER] route/plan/analyze가 async여야 그래프 노드가 await할 수 있다 (Before: 동기 → 이벤트 루프 정지)
    import inspect
    from agent.fake_llm import FastLLM
    from agent.openai_llm import OpenAIFastLLM
    for cls in (OllamaFastLLM, OpenAIFastLLM, FastLLM):
        for name in ("route", "plan", "analyze"):
            assert inspect.iscoroutinefunction(getattr(cls, name)), f"{cls.__name__}.{name}"


def test_ollama_payload_disables_thinking_and_uses_stage_timeout(monkeypatch):
    # [P9 AFTER] think=false와 단계별 timeout이 실제 요청에 들어가는지 (Ollama 없이 httpx를 가짜로 바꿔 확인)
    import agent.ollama_llm as mod
    seen = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": "{}"}, "eval_count": 1}

    class FakeClient:
        def __init__(self, timeout): seen["timeout"] = timeout
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json): seen["payload"] = json; return FakeResp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    asyncio.run(OllamaFastLLM("m", 0.0)._chat("s", "u"))
    assert seen["payload"]["think"] is False and seen["timeout"] == mod.FAST_TIMEOUT


def test_timed_wrapper_records_elapsed_ms():
    from agent.graph import _timed

    async def node(state):
        return {"events": []}
    out = asyncio.run(_timed("demo", node)({"timings": {"demo": 5}}))
    assert out["timings"]["demo"] >= 5   # 같은 노드가 다시 돌면 누적된다


# ── P5: MCP 시간 제한·재시도 ─────────────────────────────────────────────
def test_with_retry_retries_timeout_and_recoverable_tool_error():
    from agent.errors import ToolError
    from agent.retry import with_retry
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("1st")
        if len(calls) == 2:
            raise ToolError("MCP_DISCONNECTED", "2nd", recoverable=True)
        return "ok"
    assert asyncio.run(with_retry(flaky, base_delay=0)) == ("ok", 2)


def test_with_retry_does_not_retry_permanent_error():
    from agent.errors import ToolError
    from agent.retry import with_retry
    calls = []

    async def bad():
        calls.append(1)
        raise ToolError("MCP_ERROR", "invalid", recoverable=False)
    with pytest.raises(ToolError):
        asyncio.run(with_retry(bad, base_delay=0))
    assert len(calls) == 1


def test_mcp_sdk_timeout_becomes_retryable_timeout_error():
    # [P5 AFTER] Before: SDK 시간 초과(MCPError)는 retry.py가 잡지 않아 재시도 0회였다 (S8)
    from agent.mcp_client import MCPClient, MCPError

    async def sdk_timeout():
        raise MCPError(code=-32001, message="Request 'tools/call' timed out")
    with pytest.raises(TimeoutError):
        asyncio.run(MCPClient()._call("call_tool(x)", sdk_timeout))


def test_mcp_call_has_time_limit(monkeypatch):
    import agent.mcp_client as mod
    monkeypatch.setattr(mod, "MCP_TIMEOUT", 0.05)

    async def hang():
        await asyncio.sleep(5)
    with pytest.raises(TimeoutError):
        asyncio.run(mod.MCPClient()._call("call_tool(x)", hang))


# ── P6: 부분 실패 격리 ────────────────────────────────────────────────────
class _StubMCP:
    """auth-service 조회만 항상 실패하는 가짜 MCP (재시도해도 실패)."""
    async def call_tool(self, name, args):
        if args["system_name"] == "auth-service":
            raise TimeoutError("MCP down")
        return {"system_name": args["system_name"], "status": "healthy", "alerts": []}


def test_research_isolates_one_failed_task(monkeypatch):
    from types import SimpleNamespace

    from agent import graph
    monkeypatch.setattr(graph.asyncio, "sleep", _no_sleep)
    tasks = [{"id": "task-0", "agent": "research", "kind": "monitoring", "target": "web-01", "status": "pending"},
             {"id": "task-1", "agent": "research", "kind": "monitoring", "target": "auth-service", "status": "pending"}]
    out = asyncio.run(graph.research_node({"tasks": tasks, "events": []}, SimpleNamespace(mcp=_StubMCP())))
    kinds = [(e["type"], e["target"]) for e in out["events"]]
    assert ("TaskCompleted", "web-01") in kinds and ("TaskFailed", "auth-service") in kinds   # Before: 전체 예외
    assert [t["status"] for t in out["tasks"]] == ["done", "failed"]


async def _no_sleep(*_):
    return None


def test_stream_sends_error_event_then_done():
    # [P6 AFTER] Before: 예외가 나면 스트림이 그냥 끊겼다 → 화면이 조용히 멈춤 (S6)
    from types import SimpleNamespace

    import httpx as _httpx
    from fastapi.testclient import TestClient

    import server

    class BrokenGraph:
        async def astream(self, *a, **k):
            raise _httpx.ConnectError("ollama down")
            yield  # pragma: no cover

    server.app.state.deps = SimpleNamespace(version="v2", session_store=SimpleNamespace(
        load=lambda t: [], append=lambda *a: None))
    server.app.state.graph = BrokenGraph()
    body = TestClient(server.app).get("/chat/stream", params={"message": "web-01 장애"}).text
    assert '"type": "Error"' in body and '"code": "LLM_UNAVAILABLE"' in body
    assert body.rstrip().endswith("data: [DONE]")


# ── P7: 입력 검증·헤더·이력 ───────────────────────────────────────────────
class _MemStore:
    def __init__(self):
        self.rows = []

    def load(self, thread_id):
        return [r for r in self.rows if r[0] == thread_id]

    def append(self, thread_id, role, content):
        self.rows.append((thread_id, role, content))


def _client_with(graph, store=None):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    import server
    server.app.state.deps = SimpleNamespace(version="v2", session_store=store or _MemStore())
    server.app.state.graph = graph
    return TestClient(server.app)


@pytest.mark.parametrize("message", ["", "   ", "x" * 2001])
def test_chat_rejects_invalid_message(message):
    # [P7 AFTER] Before: 빈 메시지도 200 OK (S7)
    c = _client_with(graph=None)
    assert c.post("/chat", json={"message": message}).status_code == 422
    assert c.get("/chat/stream", params={"message": message}).status_code == 422


def test_chat_rejects_bad_thread_id():
    assert _client_with(graph=None).post("/chat", json={"message": "hi", "thread_id": "a b;drop"}).status_code == 422


def test_stream_has_sse_headers_and_keeps_question_when_it_fails():
    import httpx as _httpx

    class BrokenGraph:
        async def astream(self, *a, **k):
            raise _httpx.ConnectError("down")
            yield  # pragma: no cover
    store = _MemStore()
    r = _client_with(BrokenGraph(), store).get("/chat/stream", params={"message": "web-01 장애", "thread_id": "t1"})
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
    assert store.rows == [("t1", "user", "web-01 장애")]   # Before: 실패한 턴은 질문까지 사라졌다
