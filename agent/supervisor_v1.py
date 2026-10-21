"""Wave 14 — v1 (legacy) supervisor.

라우팅도, 게이트도, 재계획도, 검증도 없는 초기 선형 버전. SUPERVISOR_VERSION=v1로
기동하면 이 구현이 실행된다 — 문제가 생기면 환경변수 하나로 v2에서 즉시 롤백해
돌아오는 지점이다.

[P10 BEFORE] 장애 여부를 'fake LLM의 응답 문구'("도와드릴까요")로 판단했다.
  → 실모델(Ollama/OpenAI)은 이 문구를 거의 쓰지 않아서, 장애 질문에도 모니터링을 조회하지 않았다 (S9).
  → 조회 대상도 auth-service로 하드코딩돼 있었다.
[P10 AFTER] (기준 외 제안) 장애 판단은 v2 route의 코드 fallback과 같은 키워드 규칙으로,
  조회 대상은 공통 모듈(agent/systems.py)의 research_targets로 질문에서 뽑는다.
  v1의 목적(단순한 선형 경로, 즉시 롤백)은 유지하고 LLM 호출 수는 늘리지 않는다.
"""
import re

from langsmith import traceable

from .deps import SupervisorDeps
from .retry import with_retry
from .systems import mentioned_systems, research_targets

# v2 route_node의 형식 붕괴 fallback(agent/ollama_llm.py route)과 같은 규칙 + 증상 단어
INCIDENT_PATTERN = re.compile(r"장애|진단|다운|지연|급증|저하|느려|느리|타임아웃|부족|오류|에러|원인|incident|티켓")


@traceable(name="supervisor_v1_legacy")
async def run_v1(deps: SupervisorDeps, query: str, thread_id: str,
                 history: list[dict]) -> dict:
    events = [{"type": "Legacy", "note": "v1: 라우팅/게이트/재계획/검증 없음"}]
    # [P10 BEFORE]
    # reply, usage = await deps.fast_llm.chat(query, history)
    # if "도와드릴까요" in reply and ("장애" in query or "진단" in query):
    #     data, retries = await with_retry(
    #         deps.mcp.call_tool, "get_monitoring_status", {"system_name": "auth-service"})
    #     reply = (f"{data['system_name']} 상태={data['status']}, "
    #              f"CPU {data['cpu_percent']}% 입니다. 자세한 절차는 담당자에게 문의하세요.")
    #     events.append({"type": "TaskCompleted", "source": "monitoring", "retries": retries})
    # [P10 AFTER] 질문 자체로 장애 여부를 판단한다 (LLM 응답 문구에 의존하지 않음)
    # 증상 단어가 있거나, 모니터링하는 시스템 이름이 나오면 장애 질문으로 본다
    if INCIDENT_PATTERN.search(query) or mentioned_systems(query):
        lines, retries_total = [], 0
        for system in research_targets(query):   # 질문에 나온 시스템 전부 (없으면 기본 auth-service)
            data, retries = await with_retry(
                deps.mcp.call_tool, "get_monitoring_status", {"system_name": system})
            retries_total += retries
            lines.append(f"{data['system_name']} 상태={data['status']}, CPU {data['cpu_percent']}%")
            events.append({"type": "TaskCompleted", "source": "monitoring", "target": system,
                           "retries": retries})
        reply = ((" / ".join(lines) + " 입니다. ") if lines else
                 "질문한 시스템은 모니터링 대상이 아닙니다. ") + "자세한 절차는 담당자에게 문의하세요."
        usage = {"usd": 0.0}
    else:   # 일반 대화는 Before와 같다
        reply, usage = await deps.fast_llm.chat(query, history)
        retries_total = 0
    events.append({"type": "Finalize", "pipeline": "legacy-v1"})
    return {"final": reply, "route": "legacy", "events": events,
            "cost_usd": usage["usd"], "validation_attempts": 0,
            "replan_rounds": 0, "gate_removed": 0,
            # [P10 BEFORE] "retry_count": next((e.get("retries", 0) for e in events if e["type"] == "TaskCompleted"), 0)}
            "retry_count": retries_total}
