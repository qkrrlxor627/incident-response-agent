"""v2 Supervisor — 실제 langgraph.StateGraph (Wave 4·5·6·7·8·10b·15 통합).

route → (chat 직행 | incident 파이프라인)
incident: plan(MCP Prompt 절차 반영) → gate(권위 게이트) → research(가드+병렬+재시도)
          → replan_check(부족 시 gap task 후 재조사) → analysis(needs_analysis=True일 때만
          실제 실행) → write → validate(반려 시 재작성) → finalize

모든 노드는 SupervisorDeps를 functools.partial로 주입받는 순수 함수다(Wave 13).
각 노드는 @traceable로 LangSmith에 계층 트리로 기록된다.
"""
import asyncio
import json
import logging
import os
import time
from functools import partial
from pathlib import Path
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from langsmith import traceable

from .deps import SupervisorDeps
from .errors import classify
from .retry import with_retry


# ── [#14 BEFORE] ollama_llm.py·openai_llm.py와 똑같은 복사본 ──
# def _load_known_systems() -> set[str]:
#     path = Path(__file__).resolve().parent.parent / "data" / "monitoring.json"
#     try:
#         return set(json.loads(path.read_text()).keys())
#     except (OSError, json.JSONDecodeError):
#         return {"auth-service", "web-01"}
#
#
# KNOWN_SYSTEMS = _load_known_systems()
#
#
# ── [P1 BEFORE] 여러 시스템이 나와도 '첫 번째 1개'만 MCP Prompt에 넘김 ──
#    → plan 입력의 표준 절차에 "- 시스템: web-01" 한 줄만 들어가 모델이 1개만 계획했다 (S3 증거)
# def _extract_system_name(query: str) -> str:
#     matches = [(query.index(s), s) for s in KNOWN_SYSTEMS if s in query]
#     return min(matches)[1] if matches else "auth-service"
# ── [P1·#14 AFTER] 공통 모듈에서 가져온다 (agent/systems.py) ──
from .systems import (DEFAULT_SYSTEM, KNOWN_SYSTEMS, looks_like_incident,  # noqa: E402,F401
                      mentioned_systems, unmonitored_systems)


def _extract_system_name(query: str) -> str:
    """[P1 AFTER] MCP Prompt의 system_name에 질문에 나온 시스템 '전부'를 쉼표로 넘긴다.

    예: "web-01 CPU 급증, auth-service 커넥션 풀" → "web-01, auth-service"
    MCP 서버(mcp_server.py)의 Prompt 시그니처(system_name: str)는 그대로 두고 값만 바꿨다.
    → 다른 MCP 클라이언트와의 호환성을 깨지 않는다 (트레이드오프: 타입이 list가 아니라 문자열).
    """
    return ", ".join(mentioned_systems(query)) or DEFAULT_SYSTEM


RESEARCH_CONCURRENCY = 4   # [P6 AFTER] research 동시 실행 상한
log = logging.getLogger("agent.graph")   # [P9 AFTER] JSON 한 줄 로그 (server.py가 INFO로 출력)


class AgentState(TypedDict, total=False):
    query: str
    thread_id: str
    history: list[dict]
    route: str
    needs_analysis: bool
    tasks: list[dict]
    gate_removed: int
    collected: list[dict]
    replan_rounds: int
    retry_count: int
    parallel_elapsed: float
    draft: str
    validation_attempts: int
    validation_feedback: str
    final: str
    last_prompt: str
    cost_usd: float
    events: list[dict]
    timings: dict   # [P9 AFTER] 노드별 소요 시간(ms) — 병목 위치를 응답 metadata에서 바로 본다


def _cost(state: AgentState, usage: dict) -> float:
    return round(state.get("cost_usd", 0.0) + usage["usd"], 6)


@traceable(name="route_node")
async def route_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 5 — 모든 쿼리가 무거운 파이프라인을 탈 필요는 없다."""
    # [P4 BEFORE] result, usage = deps.fast_llm.route(state["query"])   ← 동기 호출: 이벤트 루프 정지
    result, usage = await deps.fast_llm.route(state["query"])   # [P4 AFTER] await
    # ── [P9 후속 AFTER] route 권위 보정 — After 측정에서 발견한 회귀 ──
    #    think를 끈 0.6b 라우터가 q10 "제 이름은 민수입니다"를 incident로 분류 → 장애 파이프라인 14초 (3/3)
    #    증상 단어도 시스템 이름도 없는 질문은 코드가 chat으로 바로잡는다 (K6: 확인 가능한 판단은 코드가 내린다)
    corrected = result["route"] == "incident" and not looks_like_incident(state["query"])
    if corrected:
        result = {**result, "route": "chat"}
    event = {"type": "RouteDecided", "route": result["route"],
             **({"corrected_from": "incident"} if corrected else {})}
    return {"route": result["route"], "needs_analysis": result["needs_analysis"],
            "cost_usd": _cost(state, usage),
            "events": state.get("events", []) + [event]}


@traceable(name="chat_answer_node")
async def chat_answer_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 5 direct 경로 — 히스토리 기반 응답 (Wave 12 세션 증명 지점).

    토큰 단위 스트리밍 — get_stream_writer()는 /chat/stream처럼 custom 모드로 소비될
    때만 실제로 전송되고, /chat(ainvoke)처럼 스트리밍하지 않는 호출에서는 자동으로
    no-op이 된다."""
    writer = get_stream_writer()
    reply, usage = await deps.fast_llm.chat(
        state["query"], state.get("history", []),
        on_token=lambda piece: writer({"type": "AnswerToken", "delta": piece}))
    return {"final": reply, "last_prompt": usage.get("prompt"),
            "cost_usd": _cost(state, usage),
            "events": state["events"] + [{"type": "Finalize", "pipeline": "chat-direct"}]}


@traceable(name="plan_node")
async def plan_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 4 — Plan/Task 분해. Wave 2의 MCP Prompt가 표준 절차를 깔아준다.

    resource와 마찬가지로 이름을 어느 서버가 들고 있는지 미리 가정하지 않고,
    find_prompt()로 연결된 서버들을 먼저 조회해 찾은 뒤에만 get_prompt를 보낸다."""
    prompt_server = await deps.mcp.find_prompt("incident_analysis_prompt")
    procedure = await deps.mcp.get_prompt(
        "incident_analysis_prompt",
        {"system_name": _extract_system_name(state["query"]), "symptom": state["query"]},
        server=prompt_server,
    )
    # [P4 BEFORE] result, usage = deps.fast_llm.plan(state["query"], procedure)
    result, usage = await deps.fast_llm.plan(state["query"], procedure)   # [P4 AFTER]
    targets = [t["target"] for t in result["tasks"]
               if t["agent"] == "research" and t.get("target")]
    event = {"type": "PlanCreated", "task_count": len(result["tasks"]),
             "targets": targets}
    return {"tasks": result["tasks"], "needs_analysis": result["needs_analysis"],
            "cost_usd": _cost(state, usage), "events": state["events"] + [event]}


@traceable(name="gate_node")
async def gate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 — 권위 게이트. needs_analysis=False인데 섞여 들어온 analysis task를
    프롬프트가 아니라 코드로 강제 제거한다."""
    tasks = state["tasks"]
    # ── [P3 BEFORE] 모델의 needs_analysis 판단만 믿음 → 0.6b 모델은 거의 항상 true (incident 8종 중 7종에서 분석 실행) ──
    # if not state.get("needs_analysis", False):
    #     kept = [t for t in tasks if t["agent"] != "analysis"]
    #     removed = len(tasks) - len(kept)
    # else:
    #     kept, removed = tasks, 0
    # ── [P3 AFTER] 이중 게이트 (K7 권위 게이트) ──
    #    1차: 모델이 needs_analysis=true라고 했는가 (LLM 판단)
    #    2차: 비교할 시스템이 실제로 2개 이상인가 (코드 판단) — 1개를 '비교 분석'할 수는 없다
    #    둘 다 통과해야 analysis task를 남긴다. 예: q01(payments 1개)은 모델이 true라고 해도 제거
    research_count = sum(1 for t in tasks if t["agent"] == "research")
    allow = bool(state.get("needs_analysis", False)) and research_count >= 2
    kept = tasks if allow else [t for t in tasks if t["agent"] != "analysis"]
    removed = len(tasks) - len(kept)
    event = {"type": "GateApplied", "removed_analysis_tasks": removed,
             "reason": "allowed" if allow else
             ("needs_analysis=false" if not state.get("needs_analysis") else f"research {research_count}개 < 2")}
    return {"tasks": kept, "gate_removed": removed,
            "events": state["events"] + [event]}


@traceable(name="research_node")
async def research_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 15 가드 + Wave 10b 병렬 + Wave 9 재시도 + Wave 2 Tool/Resource 실호출."""
    tasks = state["tasks"]
    research_indices = [i for i, t in enumerate(tasks)
                        if t["agent"] == "research" and t["status"] == "pending"]
    # Wave 15 — 객체가 아니라 '실행할 목록'을 검사한다 (not research_agent 버그의 수정판)
    if not research_indices:
        return {"events": state["events"] +
                [{"type": "ResearchSkipped", "reason": "pending research task 0개"}]}

    retry_total = state.get("retry_count", 0)

    # URI를 코드에 하드코딩하지 않는다. 여러 MCP 서버가 연결돼 있고 그중 어느 서버가
    # "get_incident_runbook" resource를 제공하는지 모른다고 가정하고, 먼저 연결된
    # 서버들을 조회(list)해 유효한 서버를 찾은 뒤에만 그 서버로 요청한다.
    needs_runbook = any(tasks[i]["kind"] != "monitoring" for i in research_indices)
    runbook_server = runbook_uri_template = None
    if needs_runbook:
        runbook_server, runbook_uri_template = await deps.mcp.find_resource_template(
            "get_incident_runbook")

    # ── [P6 BEFORE] 예외 격리 없이 gather → task 하나가 실패하면 gather 전체가 예외 → 요청 전체 실패 ──
    # async def run_one(idx: int) -> dict:
    #     ...
    #     data = await deps.mcp.read_resource(uri, server=runbook_server)   ← [P5 BEFORE] runbook은 재시도 없음
    #     return {"idx": idx, "source": "runbook", "data": data, "retries": 0}
    # results = await asyncio.gather(*(run_one(i) for i in research_indices))
    # ── [P6 AFTER] 코루틴마다 try/except로 격리 → 성공한 것만 모아 '부분 응답'을 만든다 (K10·K12) ──
    sem = asyncio.Semaphore(RESEARCH_CONCURRENCY)   # 동시 실행 상한 (MCP 서버 과부하 방지)

    async def run_one(idx: int) -> dict:
        task = tasks[idx]
        async with sem:
            await asyncio.sleep(0.35)   # 태스크당 고정 지연 — 병렬 효과를 실측하기 위함
            try:
                if task["kind"] == "monitoring":
                    data, retries = await with_retry(
                        deps.mcp.call_tool, "get_monitoring_status",
                        {"system_name": task["target"]})
                    return {"idx": idx, "source": "monitoring", "data": data, "retries": retries}
                uri = runbook_uri_template.format(incident_type=task["target"])
                # [P5 AFTER] runbook(Resource) 읽기도 재시도한다
                data, retries = await with_retry(deps.mcp.read_resource, uri, server=runbook_server)
                return {"idx": idx, "source": "runbook", "data": data, "retries": retries}
            except Exception as exc:   # 재시도까지 실패한 경우 — 이 task만 실패로 표시하고 나머지는 계속
                err = classify(exc)
                log.warning(json.dumps({"event": "task_failed", "task": task["id"],
                                        "target": task.get("target"), **err}, ensure_ascii=False))
                return {"idx": idx, "source": task["kind"], "error": err, "retries": 0}

    started = time.perf_counter()
    results = await asyncio.gather(*(run_one(i) for i in research_indices))
    elapsed = round(time.perf_counter() - started, 2)

    new_tasks = [dict(t) for t in tasks]
    collected = list(state.get("collected", []))
    events = list(state["events"])
    for r in results:
        if "error" in r:   # [P6 AFTER] 실패한 task: 상태 failed + TaskFailed 이벤트, 수집 결과에는 넣지 않는다
            new_tasks[r["idx"]]["status"] = "failed"
            collected.append({"source": "note", "data":
                              f"{new_tasks[r['idx']]['target']} 조회 실패({r['error']['code']}) — "
                              "이 시스템의 수치는 없으므로 추정하지 말고 조회 실패 사실을 알려라."})
            events.append({"type": "TaskFailed", "id": new_tasks[r["idx"]]["id"],
                           "source": r["source"], "target": new_tasks[r["idx"]]["target"],
                           "code": r["error"]["code"], "recoverable": r["error"]["recoverable"]})
            continue
        new_tasks[r["idx"]]["status"] = "done"
        collected.append({"source": r["source"], "data": r["data"]})
        retry_total += r["retries"]
        events.append({"type": "TaskCompleted", "id": new_tasks[r["idx"]]["id"],
                       "source": r["source"], "target": new_tasks[r["idx"]]["target"],
                       "retries": r["retries"]})
    return {"tasks": new_tasks, "collected": collected, "retry_count": retry_total,
            "parallel_elapsed": elapsed, "events": events}


# 수집된 모니터링 결과(상태·알림 문구)를 보고 어떤 runbook이 맞는지 고른다. LLM에게
# 다시 묻는 대신 코드 레벨 규칙으로 판단한다 — gate(Wave 6)·replan(Wave 7)과 같은 설계
# 원칙: 모델의 판단을 그대로 믿지 않고, 실측 데이터로 검증 가능한 결정은 코드가 내린다.
_INCIDENT_TYPE_RULES = [
    ("latency", "high-latency"),
    ("pool", "high-latency"),
    ("cpu", "cpu-spike"),
    ("memory", "memory-leak"),
    ("heap", "memory-leak"),
    ("timeout", "network-timeout"),
    ("network", "network-timeout"),
    ("disk", "disk-full"),
    ("down", "db-down"),
]


# ── [P2 BEFORE] 모든 시스템의 알림을 한 문자열로 합친 뒤 규칙을 위에서부터 검사 ──
#    → 정상인 web-01의 빈 알림과 auth-service 알림이 섞이고, 아무 규칙도 안 걸리면 무조건 db-down
#    (q05 3/3건 db-down 오분류, q08 감시 대상이 아닌데도 runbook을 붙임)
# def _classify_incident_type(collected: list[dict]) -> str:
#     text = " ".join(
#         f"{c['data'].get('status', '')} " + " ".join(c["data"].get("alerts", []))
#         for c in collected if c.get("source") == "monitoring"
#     ).lower()
#     for keyword, incident_type in _INCIDENT_TYPE_RULES:
#         if keyword in text:
#             return incident_type
#     return "db-down"   # 매칭되는 증상이 없으면 가장 일반적인 장애 대응 절차로 폴백
# ── [P2 AFTER] 시스템을 '하나씩', 질문에 나온 순서대로 본다 (K8 근거 기반 분류) ──
HEALTHY_STATUSES = ("healthy", "unknown")   # unknown = 모니터링 목록에 없는 시스템 (mcp_server.py:38)


def _classify_incident_type(collected: list[dict]) -> str | None:
    """이상이 있는 시스템 중 '먼저 나온' 시스템의 증상으로 runbook을 고른다.

    - collected의 monitoring 순서 = plan의 research 순서 = 질문 언급 순서 (P1에서 보장)
    - 정상(healthy) 시스템은 건너뛴다 → q05: web-01(정상) 건너뜀 → auth-service 'latency' → high-latency
    - 이상 있는 시스템이 하나도 없으면 None = "runbook을 붙이지 않는다" (Before: 무조건 db-down)
    """
    for c in collected:
        if c.get("source") != "monitoring":
            continue
        status = str(c["data"].get("status", "")).lower()
        if status in HEALTHY_STATUSES:
            continue   # 정상 시스템의 (빈) 알림은 분류 근거가 아니다
        text = (status + " " + " ".join(c["data"].get("alerts", []))).lower()
        for keyword, incident_type in _INCIDENT_TYPE_RULES:
            if keyword in text:
                return incident_type
    return None   # 근거가 없으면 추측하지 않는다 (db-down 폴백 제거)


def _no_runbook_note(query: str, collected: list[dict]) -> str:
    """runbook을 붙이지 않을 때 write 단계에 넘길 '사실' 한 줄 (모델이 지어내지 않게 이유를 명시)."""
    missing = unmonitored_systems(query)
    names = [c["data"].get("system_name") for c in collected if c.get("source") == "monitoring"]
    if not names and any(c.get("source") == "note" and "조회 실패" in c["data"] for c in collected):
        # [P6 AFTER] 조회가 실패해서 데이터가 없는 것을 '정상'으로 착각하지 않는다
        return "모니터링 조회가 실패해 장애 유형을 판단할 수 없다. 원인을 단정하지 말고 재시도를 안내하라."
    if missing:
        return (f"{', '.join(missing)}는 모니터링 대상(data/monitoring.json)에 없는 시스템이다. "
                "상태를 조회할 수 없으므로 수치를 추정하지 말고, 모니터링 등록이 필요하다고 안내하라.")
    return (f"조사한 시스템({', '.join(n for n in names if n)})은 모두 정상이고 활성 알림이 없다. "
            "장애 유형을 단정하지 말고 '현재 이상 징후 없음'과 추가 확인 방법을 안내하라.")


@traceable(name="replan_check_node")
async def replan_check_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 7 — 1차 수집 결과 평가. runbook이 없으면 gap task만 추가해 재조사."""
    has_runbook = any(c["source"] == "runbook" for c in state.get("collected", []))
    rounds = state.get("replan_rounds", 0)
    if has_runbook or rounds >= 1:
        verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": True}
        return {"events": state["events"] + [verdict]}
    incident_type = _classify_incident_type(state.get("collected", []))
    # ── [P2 AFTER] 분류 근거가 없으면(None) runbook gap task를 만들지 않고 그대로 진행 ──
    #    대신 "이상 없음 / 감시 대상 아님"이라는 사실을 collected에 남겨 write가 이를 답하게 한다
    if incident_type is None:
        note = {"source": "note", "data": _no_runbook_note(state["query"], state.get("collected", []))}
        verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": True,
                   "runbook": None, "reason": "이상 징후 없음 또는 모니터링 대상 아님"}
        return {"collected": state.get("collected", []) + [note],
                "events": state["events"] + [verdict]}
    gap_task ={"id": "task-gap-runbook", "agent": "research", "kind": "runbook",
                "target": incident_type, "status": "pending"}
    verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": False,
               "gap_task": gap_task["id"], "target": incident_type}
    return {"tasks": state["tasks"] + [gap_task], "replan_rounds": rounds + 1,
            "events": state["events"] + [verdict]}


@traceable(name="analysis_node")
async def analysis_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 보완 — needs_analysis=True가 정당한 경우(모델의 자기모순이 아니라
    실제로 패턴 비교가 필요하다고 판단한 경우)를 위한 실행 경로. gate가 살려둔
    agent=='analysis' task가 있을 때만 수집된 monitoring 결과들을 비교 분석한다."""
    tasks = state["tasks"]
    pending = [t for t in tasks if t["agent"] == "analysis" and t["status"] == "pending"]
    if not pending:
        return {"events": state["events"] +
                [{"type": "AnalysisSkipped", "reason": "analysis task 0개"}]}
    # [P4 BEFORE] summary, usage = deps.fast_llm.analyze(state.get("collected", []))
    #    ← q01 Before: 이 동기 호출 하나가 300.07초 동안 서버를 멈춘 뒤 ReadTimeout (S11)
    summary, usage = await deps.fast_llm.analyze(state.get("collected", []))   # [P4 AFTER]
    new_tasks = [dict(t) for t in tasks]
    for t in new_tasks:
        if t["agent"] == "analysis" and t["status"] == "pending":
            t["status"] = "done"
    collected = state.get("collected", []) + [{"source": "analysis", "data": summary}]
    event = {"type": "AnalysisCompleted", "length": len(summary)}
    return {"tasks": new_tasks, "collected": collected,
            "cost_usd": _cost(state, usage), "events": state["events"] + [event]}


@traceable(name="write_node")
async def write_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 8/10a — 고품질 모델로 초안 작성 (1차는 의도적 저품질).

    토큰마다 attempt 번호를 같이 실어 보낸다 — validate가 반려해 재작성(attempt 증가)
    될 때 프론트가 새 말풍선으로 끊어서 보여줄 수 있게 하기 위함(Wave 8 재작성 루프를
    그대로 노출)."""
    attempt = state.get("validation_attempts", 0) + 1
    writer = get_stream_writer()
    draft, usage = await deps.quality_llm.write(
        state["query"], state.get("collected", []),
        attempt, state.get("validation_feedback"),
        on_token=lambda piece: writer(
            {"type": "AnswerToken", "attempt": attempt, "delta": piece}))
    return {"draft": draft, "last_prompt": usage.get("prompt"),
            "cost_usd": _cost(state, usage),
            "events": state["events"] + [{"type": "DraftWritten", "attempt": attempt,
                                          "length": len(draft)}]}


# ── [P11 BEFORE] 형식만 검사: 30자 이상 + "1)" 포함이면 합격, 3번째는 무조건 통과 ──
#    → incident 23건 모두 첫 시도 합격(반려 0건). q05 judge 0.6, q08 0.25인 답변도 통과 (S13)
# @traceable(name="validate_node")
# async def validate_node(state: AgentState, deps: SupervisorDeps) -> dict:
#     draft = state["draft"]
#     attempts = state.get("validation_attempts", 0) + 1
#     ok = len(draft) >= 30 and "1)" in draft
#     verdict = "합격" if ok else "불합격"
#     if not ok and attempts >= 3:   # 실모델 무한 재작성 방지 — 최대 3회 후 통과 처리
#         ok, verdict = True, "합격(최대 시도 도달 — 통과 처리)"
#     feedback = None if ok else (f"응답이 너무 짧습니다(...). 절차를 1) 2) 3) 번호로 ...")
#     ...
# ── [P11 AFTER] 규칙 검사(코드) + LLM-as-a-Judge(모델) 혼합, 재작성은 1회까지 (K9) ──
MAX_WRITE_ATTEMPTS = 2   # 최초 1회 + 재작성 1회. Before는 3회 (재작성 1번에 8b 모델 약 8초가 든다)
# judge를 맡을 모델: "fast_llm"(0.6b, 빠름) 또는 "quality_llm"(8b, 정확). 비교 근거: outputs/after/evidence/P11_judge_model_compare.txt
JUDGE_LLM = os.environ.get("JUDGE_LLM", "quality_llm")   # 기본 8b: 0.6b는 근거 있는 답을 잘못 반려(4건 중 1건)


def _facts_text(collected: list[dict]) -> str:
    """judge에게 보여줄 '수집된 사실' 요약 — write 단계가 받은 것과 같은 정보."""
    lines = []
    for c in collected:
        d = c["data"]
        if c["source"] == "monitoring":
            lines.append(f"- 모니터링 {d.get('system_name')}: 상태={d.get('status')}, CPU {d.get('cpu_percent')}%, "
                         f"메모리 {d.get('memory_percent')}%, 알림 {d.get('alerts')}")
        elif c["source"] == "runbook":
            lines.append(f"- runbook: {d.strip().splitlines()[0] if d.strip() else ''}")
        elif c["source"] in ("note", "analysis"):
            lines.append(f"- {c['source']}: {d}")
    return "\n".join(lines) or "(수집된 사실 없음)"


def _rule_problems(query: str, draft: str, collected: list[dict]) -> list[str]:
    """코드로 확실히 판단할 수 있는 문제만 찾는다. 하나라도 있으면 LLM judge 없이 반려."""
    problems = []
    if len(draft) < 30 or "1)" not in draft:   # Before의 형식 검사는 그대로 유지
        problems.append(f"형식: {len(draft)}자 — 30자 이상, 1) 2) 3) 번호 절차로 작성하세요.")
    researched = [c["data"].get("system_name") for c in collected if c["source"] == "monitoring"]
    missing = [s for s in researched if s and s not in draft]
    if missing:   # 조사한 시스템을 답변에서 빠뜨림 (P1에서 2개 조사해도 답이 1개만 다루면 소용없다)
        problems.append(f"근거 누락: 조사한 시스템 {', '.join(missing)}의 결과를 답변에 포함하세요.")
    invented = [s for s in KNOWN_SYSTEMS if s in draft and s not in researched and s not in query]
    if invented:  # 조사하지도, 질문에 나오지도 않은 시스템을 단정 (Before q08: auth-service 진단)
        problems.append(f"근거 없음: 조사하지 않은 시스템 {', '.join(sorted(invented))}의 상태를 단정하지 마세요.")
    return problems


@traceable(name="validate_node")
async def validate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    draft = state["draft"]
    attempts = state.get("validation_attempts", 0) + 1
    collected = state.get("collected", [])
    cost = state.get("cost_usd", 0.0)
    # 1) 규칙 검사 — 빠르고 결정론적 (LLM 호출 없음)
    problems = _rule_problems(state["query"], draft, collected)
    judge = None
    # 2) 규칙을 통과했을 때만 LLM judge — 규칙이 잡지 못하는 '사실과 다른 진단'을 본다
    judge_llm = getattr(deps, JUDGE_LLM, None) if deps is not None else None
    if not problems and hasattr(judge_llm, "judge"):
        judge, usage = await judge_llm.judge(state["query"], _facts_text(collected), draft)
        cost = _cost(state, usage)
        if not judge["grounded"]:
            problems.append(f"사실 불일치: {judge['reason']}")
    ok = not problems
    verdict = "합격" if ok else "불합격"
    if not ok and attempts >= MAX_WRITE_ATTEMPTS:   # 재작성 1회 상한 — 무한 루프·지연 방지
        ok, verdict = True, "합격(재작성 상한 도달 — 경고와 함께 통과)"
    feedback = None if ok else " / ".join(problems)
    event = {"type": "Validation", "attempt": attempts, "verdict": verdict,
             "problems": problems, "judge": judge}
    return {"validation_attempts": attempts, "validation_feedback": feedback, "cost_usd": cost,
            "events": state["events"] + [event]}


@traceable(name="finalize_node")
async def finalize_node(state: AgentState, deps: SupervisorDeps) -> dict:
    return {"final": state["draft"],
            "events": state["events"] + [{"type": "Finalize", "pipeline": "incident-v2"}]}


def _after_route(state: AgentState) -> str:
    return "chat_answer" if state["route"] == "chat" else "plan"


def _after_replan_check(state: AgentState) -> str:
    last = state["events"][-1]
    return "analysis" if last.get("is_sufficient") else "research"


def _after_validate(state: AgentState) -> str:
    return "finalize" if state.get("validation_feedback") is None else "write"




def _timed(name: str, fn):
    """[P9 AFTER] 노드 실행 시간을 재서 state['timings']에 누적하고, JSON 한 줄로 로그를 남긴다.

    Before에는 노드별 시간이 LangSmith에만 있었다 → 서버 로그와 응답만으로는 병목을 알 수 없었다.
    같은 노드가 여러 번 돌면(research 재조사, write 재작성) 시간을 더한다.
    """
    async def run(state: AgentState) -> dict:
        started = time.perf_counter()
        out = await fn(state)
        ms = round((time.perf_counter() - started) * 1000)
        timings = dict(state.get("timings") or {})
        timings[name] = timings.get(name, 0) + ms
        log.info(json.dumps({"event": "node_done", "node": name, "elapsed_ms": ms,
                             "thread_id": state.get("thread_id")}, ensure_ascii=False))
        return {**out, "timings": timings}
    return run


def build_graph(deps: SupervisorDeps):
    g = StateGraph(AgentState)
    # [P9 BEFORE] node = lambda fn: partial(fn, deps=deps)   # Wave 13 — 명시적 의존성 주입
    # [P9 AFTER] 의존성 주입은 그대로 두고, 바깥에 시간 측정 래퍼(_timed)를 씌운다
    node = lambda fn: _timed(fn.__name__.removesuffix("_node"), partial(fn, deps=deps))
    g.add_node("route", node(route_node))
    g.add_node("chat_answer", node(chat_answer_node))
    g.add_node("plan", node(plan_node))
    g.add_node("gate", node(gate_node))
    g.add_node("research", node(research_node))
    g.add_node("replan_check", node(replan_check_node))
    g.add_node("analysis", node(analysis_node))
    g.add_node("write", node(write_node))
    g.add_node("validate", node(validate_node))
    g.add_node("finalize", node(finalize_node))

    g.set_entry_point("route")
    g.add_conditional_edges("route", _after_route,
                            {"chat_answer": "chat_answer", "plan": "plan"})
    g.add_edge("chat_answer", END)
    g.add_edge("plan", "gate")
    g.add_edge("gate", "research")
    g.add_edge("research", "replan_check")
    g.add_conditional_edges("replan_check", _after_replan_check,
                            {"analysis": "analysis", "research": "research"})
    g.add_edge("analysis", "write")
    g.add_edge("write", "validate")
    g.add_conditional_edges("validate", _after_validate,
                            {"finalize": "finalize", "write": "write"})
    g.add_edge("finalize", END)
    return g.compile()
