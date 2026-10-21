"""핵심 코드 고장 지점 오프라인 재현 (프로젝트 파일 수정 없음, Ollama 불필요)."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from agent import ollama_llm, graph, retry, supervisor_v1  # noqa: E402
from agent.mcp_client import MCPClient  # noqa: E402

Q05 = "web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘"


def hdr(t):
    print(f"\n=== {t} ===")


# [1] plan(): 모델이 task 1개만 주면 복구 안 됨 / target 오타면 첫 시스템 하나로 수렴
hdr("1. plan() 정규화")
llm = ollama_llm.OllamaFastLLM("stub", 0.0)
cases = {
    "모델이 web-01 task 1개만 줌": {"needs_analysis": True, "tasks": [
        {"agent": "research", "target": "web-01"}, {"agent": "analysis"}]},
    "모델이 target 2개를 오타로 줌": {"needs_analysis": False, "tasks": [
        {"agent": "research", "target": "web01"},
        {"agent": "research", "target": "auth_service"}]},
    "모델이 research 0개 (복구 경로)": {"needs_analysis": False, "tasks": [
        {"agent": "analysis"}]},
}
for name, raw in cases.items():
    llm._chat = lambda s, u, schema=None, raw=raw: (json.dumps(raw), {"tokens": 0, "usd": 0})
    res, _ = llm.plan(Q05, "")
    tg = [t["target"] for t in res["tasks"] if t["agent"] == "research"]
    print(f"- {name:28s} → 조사 대상 {tg}  needs_analysis={res['needs_analysis']}")


async def main():
    mcp = MCPClient(flaky_first_tool_call=False)
    await mcp.start()
    try:
        # [2] plan에 들어가는 표준 절차 프롬프트 실제 내용
        hdr("2. q05 plan 입력의 표준 절차(MCP Prompt)")
        sysname = graph._extract_system_name(Q05)
        proc = await mcp.get_prompt("incident_analysis_prompt",
                                    {"system_name": sysname, "symptom": Q05})
        print("\n".join(l for l in proc.splitlines() if "시스템" in l or "증상" in l))

        # [3] 분류: 정상 시스템만 조사 / 없는 시스템 → db-down
        hdr("3. 분류 폴백")
        for target in ["web-01", "no-such-service", "auth-service"]:
            data = await mcp.call_tool("get_monitoring_status", {"system_name": target})
            t = graph._classify_incident_type([{"source": "monitoring", "data": data}])
            print(f"- {target:16s} status={data['status']:9s} → {t}")
    finally:
        await mcp.stop()

    # [4] 동기 _chat이 이벤트 루프를 멈춤
    hdr("4. 동기 LLM 호출 중 이벤트 루프 정지 (#4)")
    import httpx

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"message": {"content": '{"route":"incident","needs_analysis":false}'}}

    orig = httpx.post
    httpx.post = lambda *a, **k: (time.sleep(2.0), R())[1]   # 모델이 2초 생각한다고 가정
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.1)
            ticks += 1

    tk = asyncio.create_task(ticker())
    await asyncio.sleep(0.25)
    before = ticks
    t0 = time.perf_counter()
    await graph.route_node({"query": Q05, "events": [], "cost_usd": 0.0},
                           type("D", (), {"fast_llm": ollama_llm.OllamaFastLLM("stub", 0.0)})())
    print(f"- route_node 2.0초 동안 다른 작업 tick: {ticks - before}회 (정상이면 ~20회)"
          f"  경과 {time.perf_counter() - t0:.1f}s")
    tk.cancel()
    httpx.post = orig

    # [5] MCP timeout 예외 타입과 with_retry
    hdr("5. MCP timeout 예외 vs with_retry (#11)")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from datetime import timedelta
    params = StdioServerParameters(command=sys.executable,
                                   args=[str(Path(__file__).parent / "slow_server.py")],
                                   env={**os.environ, "FASTMCP_LOG_LEVEL": "ERROR"})
    async with stdio_client(params) as (r, w):
        try:
            sess = ClientSession(r, w, read_timeout_seconds=1.0)
        except TypeError:
            sess = ClientSession(r, w, read_timeout_seconds=timedelta(seconds=1))
        async with sess:
            await sess.initialize()
            calls = 0

            async def call():
                nonlocal calls
                calls += 1
                return await sess.call_tool("slow_tool", {})
            t0 = time.perf_counter()
            try:
                await retry.with_retry(call)
            except Exception as e:
                print(f"- 예외 타입: {type(e).__module__}.{type(e).__name__}: {e}")
                print(f"- asyncio.TimeoutError인가? {isinstance(e, asyncio.TimeoutError)}")
                print(f"- with_retry 시도 횟수: {calls}회 (재시도 동작하면 3회)"
                      f"  경과 {time.perf_counter() - t0:.1f}s")

    # [6] v1: 실모델 답변엔 '도와드릴까요'가 없으면 장애 경로를 아예 안 탐
    hdr("6. v1 롤백 경로")

    class FakeChat:
        async def chat(self, q, h, on_token=None):
            return "web-01 CPU 급증 원인을 확인해 보겠습니다.", {"usd": 0}

    class NoMCP:
        async def call_tool(self, *a, **k):
            raise AssertionError("호출됨")
    d = type("D", (), {"fast_llm": FakeChat(), "mcp": NoMCP()})()
    res = await supervisor_v1.run_v1(d, "web-01 장애 진단해줘", "t", [])
    called = any(e["type"] == "TaskCompleted" for e in res["events"])
    print(f"- 실모델풍 답변일 때 모니터링 조회 여부: {called}  → 최종: {res['final']!r}")


asyncio.run(main())
