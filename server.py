"""all_total 통합 실습 — FastAPI 백엔드 (Wave 1·3·12·14 축 + 전체 조립).

- Wave 1  : lifespan에서 Agent 번들(MCP 연결·LLM·그래프)을 프로세스당 정확히 1회 생성,
            app.state로 모든 요청이 공유 (creation_count/instance_id로 증명)
- Wave 2  : mcp_server.py를 subprocess(stdio)로 기동해 연결 유지
- Wave 3  : GET /chat/stream — 그래프 실행 과정을 SSE 이벤트로 스트리밍
- Wave 12 : 대화 이력을 SQLite(session.db)에 저장 — 재시작해도 유지
- Wave 14 : SUPERVISOR_VERSION(v1/v2) 환경변수로 legacy/신형 파이프라인 즉시 전환
- LangSmith: 요청당 chat_request 루트 run 아래로 노드·LLM·MCP 호출이 계층 기록됨
"""
import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()   # LANGCHAIN_TRACING_V2 / API_KEY / PROJECT — import보다 먼저

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from pydantic import BaseModel, Field, ValidationError, field_validator

from agent.deps import SupervisorDeps
from agent.errors import classify
from agent.fake_llm import FastLLM, QualityLLM
from agent.graph import build_graph
from agent.mcp_client import MCPClient
from agent.session_store import create_session_store
from agent.supervisor_v1 import run_v1

# [P9 AFTER] agent.* 로거의 JSON 한 줄 로그(노드별 elapsed_ms)를 서버 터미널에 출력한다
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
logging.getLogger("agent").setLevel(logging.INFO)
log = logging.getLogger("agent.server")

CREATION_COUNT = 0   # Wave 1 — 프로세스 내 Agent 번들 생성 횟수 (항상 1이어야 정상)


# ── [P7 BEFORE] 길이·공백 검사가 없음 → 빈 메시지("")도 200 OK로 받아 LLM까지 호출했다 (S7) ──
# class ChatRequest(BaseModel):   # Wave 1 — Pydantic 요청 검증
#     message: str
#     thread_id: str = "default"
# ── [P7 AFTER] 입력 계약을 모델에 명시한다 (K2 Pydantic 검증) — 위반하면 FastAPI가 422를 돌려준다 ──
MAX_MESSAGE_LEN = 2000                         # 장애 설명 한 건으로 충분한 길이. 초과 입력은 LLM 비용·지연만 키운다
THREAD_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"   # 세션 키로 DB에 저장되므로 형식을 제한한다


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LEN)
    thread_id: str = Field(default="default", pattern=THREAD_ID_PATTERN)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():   # "   "처럼 공백뿐인 메시지도 빈 입력으로 본다
            raise ValueError("message must not be blank")
        return v.strip()


def _build_llms():
    """LLM_BACKEND=fake(기본, 결정론) | ollama(로컬 실모델) | openai(실제 OpenAI API)."""
    backend = os.environ.get("LLM_BACKEND", "fake")
    if backend == "ollama":
        from agent.ollama_llm import OllamaFastLLM, OllamaQualityLLM
        fast = OllamaFastLLM(os.environ.get("OLLAMA_FAST_MODEL", "qwen3:0.6b"),
                             usd_per_1k_tokens=0.00015)
        quality = OllamaQualityLLM(os.environ.get("OLLAMA_QUALITY_MODEL", "qwen3:8b"),
                                   usd_per_1k_tokens=0.005)
        return backend, fast, quality
    if backend == "openai":
        from agent.openai_llm import OpenAIFastLLM, OpenAIQualityLLM
        fast = OpenAIFastLLM(os.environ.get("OPENAI_FAST_MODEL", "gpt-4o-mini"),
                             usd_per_1k_tokens=0.00015)
        quality = OpenAIQualityLLM(os.environ.get("OPENAI_QUALITY_MODEL", "gpt-4o"),
                                   usd_per_1k_tokens=0.005)
        return backend, fast, quality
    fast = FastLLM("fast-model-stub", usd_per_1k_tokens=0.00015)
    quality = QualityLLM("quality-model-stub", usd_per_1k_tokens=0.005)
    return backend, fast, quality


@asynccontextmanager
async def lifespan(app: FastAPI):
    global CREATION_COUNT
    CREATION_COUNT += 1
    mcp = MCPClient()
    await mcp.start()   # Wave 2 — MCP subprocess는 서버 수명 동안 딱 1개
    backend, fast_llm, quality_llm = _build_llms()
    app.state.llm_backend = backend
    deps = SupervisorDeps(
        fast_llm=fast_llm,
        quality_llm=quality_llm,
        mcp=mcp,
        # [E15 BEFORE] session_store=SqliteSessionStore(),   ← 동기 저장소
        session_store=create_session_store(),   # [E15 AFTER] 비동기 저장소를 팩토리로 주입
        version=os.environ.get("SUPERVISOR_VERSION", "v2"),
    )
    app.state.deps = deps
    app.state.graph = build_graph(deps) if deps.version == "v2" else None
    app.state.instance_id = id(deps)
    yield
    await mcp.stop()
    deps.session_store.close()
    try:   # 종료 전 LangSmith 배치 전송 플러시 — kill 시 run이 pending으로 남는 것 방지
        from langchain_core.tracers.langchain import wait_for_all_tracers
        wait_for_all_tracers()
    except Exception:
        pass


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "instance_id": app.state.instance_id,
            "creation_count": CREATION_COUNT,
            "supervisor_version": app.state.deps.version,
            "llm_backend": app.state.llm_backend,
            "fast_llm": app.state.deps.fast_llm.name,
            "quality_llm": app.state.deps.quality_llm.name}


@app.get("/version")
async def version():
    return {"supervisor_version": app.state.deps.version}


def _metadata(result: dict, run_id: str | None) -> dict:
    return {
        "route": result.get("route"),
        "task_count": len(result.get("tasks", [])),
        "gate_removed": result.get("gate_removed", 0),
        "replan_rounds": result.get("replan_rounds", 0),
        "retry_count": result.get("retry_count", 0),
        "parallel_elapsed": result.get("parallel_elapsed"),
        "validation_attempts": result.get("validation_attempts", 0),
        "cost_usd": result.get("cost_usd", 0.0),
        "llm_backend": app.state.llm_backend,
        "supervisor_version": app.state.deps.version,
        "instance_id": app.state.instance_id,
        "langsmith_run_id": run_id,
        "timings_ms": result.get("timings", {}),   # [P9 AFTER] 노드별 소요 시간 — 어디가 느린지 응답에서 바로 본다
    }


@traceable(name="chat_request")
async def _handle_chat(message: str, thread_id: str) -> tuple[dict, str | None]:
    deps = app.state.deps
    history = await deps.session_store.load(thread_id)   # Wave 12
    # [P7 AFTER] 사용자 메시지를 '먼저' 저장한다 — 처리 도중 실패해도 질문은 이력에 남는다
    #   (Before: 성공한 뒤에만 user·assistant를 같이 저장 → 실패한 턴은 질문까지 사라졌다)
    await deps.session_store.append(thread_id, "user", message)   # [E15 AFTER] await
    if deps.version == "v2":
        result = await app.state.graph.ainvoke(
            {"query": message, "thread_id": thread_id, "history": history,
             "events": [], "cost_usd": 0.0})
    else:
        result = await run_v1(deps, message, thread_id, history)   # Wave 14
    # [P7 BEFORE] deps.session_store.append(thread_id, "user", message)
    await deps.session_store.append(thread_id, "assistant", result["final"])   # [E15 AFTER] await
    rt = get_current_run_tree()
    return result, (str(rt.id) if rt else None)


@app.post("/chat")
async def chat(req: ChatRequest):
    # [P6 BEFORE] 예외가 나면 FastAPI 기본 500 "Internal Server Error" (원인·재시도 가능 여부 없음)
    # result, run_id = await _handle_chat(req.message, req.thread_id)
    # [P6 AFTER] 에러를 분류해 503 + {code, recoverable, message}로 돌려준다
    try:
        result, run_id = await _handle_chat(req.message, req.thread_id)
    except Exception as exc:
        err = classify(exc)
        log.warning(json.dumps({"event": "chat_failed", "thread_id": req.thread_id, **err}, ensure_ascii=False))
        return JSONResponse({"error": err}, status_code=503)
    return {"reply": result["final"], "events": result.get("events", []),
            "metadata": _metadata(result, run_id)}


# [P7 BEFORE] async def chat_stream(message: str, thread_id: str = "default"):   ← 검증 없음
@app.get("/chat/stream")
async def chat_stream(message: str = Query(min_length=1, max_length=MAX_MESSAGE_LEN),
                      thread_id: str = Query("default", pattern=THREAD_ID_PATTERN)):
    """Wave 3 — 그래프의 노드별 진행 상황을 SSE로 스트리밍.

    이벤트마다 'data: {json}\\n\\n' 형태로 내려보내고 마지막에 data: [DONE] 센티널을
    보낸다 — 프론트엔드는 \\n\\n 경계로 이벤트를 분리해 파싱해야 한다(Wave 3b).
    """
    # [P7 AFTER] /chat과 같은 규칙으로 검증한다 (EventSource는 GET만 쓸 수 있어 Query로 받는다)
    try:
        message = ChatRequest(message=message, thread_id=thread_id).message
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_url=False, include_context=False))
    deps = app.state.deps

    # [P6 BEFORE] gen() 안에서 예외가 나면 스트림이 그냥 끊겼다 → 브라우저는 onerror만 받고 조용히 멈춤 (S6)
    # [P6 AFTER] 실제 작업은 _events()에 두고, gen()이 감싸서 예외를 Error 이벤트로 바꾼 뒤 [DONE]까지 보낸다
    async def gen():
        try:
            async for chunk in _events():
                yield chunk
        except Exception as exc:
            err = classify(exc)   # {code, recoverable, message} — agent/errors.py
            log.warning(json.dumps({"event": "stream_failed", "thread_id": thread_id, **err}, ensure_ascii=False))
            yield f"data: {json.dumps({'type': 'Error', **err}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"   # 성공이든 실패든 항상 끝 신호를 보낸다 → 화면이 '전송 중'에 갇히지 않는다

    @traceable(name="chat_stream_request")   # [P7 AFTER] 스트림 요청도 LangSmith 루트 run으로 남긴다 (Before: /chat만 chat_request로 기록)
    async def _events():
        history = await deps.session_store.load(thread_id)   # [E15 AFTER] await
        await deps.session_store.append(thread_id, "user", message)   # [P7 AFTER] 질문을 먼저 저장 (중간에 끊겨도 남는다)
        if deps.version != "v2":
            result = await run_v1(deps, message, thread_id, history)
            for ev in result["events"]:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'FinalAnswer', 'reply': result['final']}, ensure_ascii=False)}\n\n"
            # [P7 AFTER] v1 스트림도 답변을 저장한다 (Before: v1 분기는 이력을 전혀 저장하지 않았다)
            await deps.session_store.append(thread_id, "assistant", result["final"])   # [E15 AFTER] await
        else:
            seen = 0
            final = ""
            last_prompt = None   # finalize까지 살아남은 최종 write/chat 호출의 실제 프롬프트
            # stream_mode를 리스트로 주면 (mode, payload) 튜플이 나온다 — "updates"는
            # 노드가 끝날 때마다의 상태 델타, "custom"은 write_node/chat_answer_node가
            # get_stream_writer()로 실행 중에 즉시 흘려보내는 토큰(AnswerToken) 이벤트다.
            async for mode, payload in app.state.graph.astream(
                    {"query": message, "thread_id": thread_id, "history": history,
                     "events": [], "cost_usd": 0.0}, stream_mode=["updates", "custom"]):
                if mode == "custom":
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    continue
                for node_name, delta in payload.items():
                    for ev in (delta.get("events") or [])[seen:]:
                        # [P9 BEFORE] ev = {**ev, "node": node_name}
                        ev = {**ev, "node": node_name,   # [P9 AFTER] 이 노드가 걸린 시간(누적 ms)도 같이 보낸다
                              "elapsed_ms": (delta.get("timings") or {}).get(node_name)}
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    if delta.get("events"):
                        seen = len(delta["events"])
                    if delta.get("final"):
                        final = delta["final"]
                    if delta.get("last_prompt"):
                        last_prompt = delta["last_prompt"]
            yield f"data: {json.dumps({'type': 'FinalAnswer', 'reply': final, 'prompt': last_prompt}, ensure_ascii=False)}\n\n"
            # [P7 BEFORE] deps.session_store.append(thread_id, "user", message)   ← 끝까지 간 경우에만 저장
            await deps.session_store.append(thread_id, "assistant", final)   # [E15 AFTER] await

    # [P7 BEFORE] return StreamingResponse(gen(), media_type="text/event-stream")
    # [P7 AFTER] SSE 헤더: 프록시(nginx 등)·브라우저가 버퍼링/캐시하지 않고 이벤트를 즉시 흘려보내게 한다
    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",       # 캐시된 스트림을 다시 보여주지 않게
        "X-Accel-Buffering": "no",         # nginx가 모아서 보내지 않게 (토큰이 한꺼번에 뜨는 현상 방지)
        "Connection": "keep-alive",
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="warning")
