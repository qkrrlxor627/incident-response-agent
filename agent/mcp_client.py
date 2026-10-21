"""Wave 2 — MCP 서버 여러 개를 subprocess(stdio)로 1회씩 기동해 재사용하는 클라이언트.

Wave 1의 교훈대로 서버(lifespan)에서 한 번만 연결을 만들고 모든 요청이 공유한다.
Wave 9 데모용으로, 프로세스 최초의 get_monitoring_status 호출 1회는 일부러
asyncio.TimeoutError를 던진다(transient) — with_retry가 backoff 후 복구해야 한다.

연결 대상은 "ops"(mcp_server.py — monitoring tool + runbook resource + prompt, 실제
사용)와 "docs"(mcp_server_docs.py — API 문서 resource만 제공, agent는 사용하지 않는
decoy) 두 서버다. resource/prompt를 요청할 때는 어느 서버가 그걸 들고 있는지 미리
알고 있지 않다고 가정하고, find_resource_template()/find_prompt()로 연결된 서버들을
순서대로 조회(list)해 이름이 맞는 걸 찾은 뒤에야 그 서버로 read_resource/get_prompt를
보낸다.
"""
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from langsmith import traceable
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .errors import ToolError

try:   # mcp SDK 2.x는 MCPError, 1.x는 McpError — 설치된 버전과 무관하게 잡는다
    from mcp.shared.exceptions import MCPError
except ImportError:   # pragma: no cover
    from mcp.shared.exceptions import McpError as MCPError

# ── [P5 AFTER] MCP 호출 1건의 시간 제한 ──
#    Before: 시간 제한이 없었다 → MCP 서버가 멈추면 요청도 같이 멈췄다.
#    로컬 stdio 서버의 정상 응답은 수 ms라 10초면 충분하다 (환경변수 MCP_TIMEOUT으로 조정).
MCP_TIMEOUT = float(os.environ.get("MCP_TIMEOUT", "10"))

SERVER_DIR = Path(__file__).parent.parent
DEFAULT_SERVER_SCRIPTS = {
    "ops": SERVER_DIR / "mcp_server.py",
    "docs": SERVER_DIR / "mcp_server_docs.py",
}


def _attr(obj, *names):
    """mcp SDK 버전에 따라 pydantic 필드명이 camelCase(예: resourceTemplates,
    uriTemplate, 구버전 1.x)와 snake_case(예: resource_templates, uri_template,
    신버전 2.x)로 갈린다 — 이 프로젝트 안에도 시스템 python3(mcp 1.28.1, camelCase)와
    .venv(mcp 2.2.0, snake_case)가 섞여 있어 실행 환경마다 바뀐다. 둘 다 시도해서
    설치된 버전과 무관하게 동작하게 한다."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(f"{type(obj).__name__!r} has none of {names!r}")


class MCPClient:
    def __init__(self, flaky_first_tool_call: bool = True,
                 server_scripts: dict[str, Path] | None = None):
        self._server_scripts = server_scripts or DEFAULT_SERVER_SCRIPTS
        self._stack: AsyncExitStack | None = None
        self.sessions: dict[str, ClientSession] = {}
        self._lock = asyncio.Lock()
        self._flaky_pending = flaky_first_tool_call   # Wave 9 시뮬레이션

    async def start(self) -> None:
        self._stack = AsyncExitStack()
        for server_name, script in self._server_scripts.items():
            params = StdioServerParameters(
                command=sys.executable, args=[str(script)],
                env={**os.environ, "FASTMCP_LOG_LEVEL": "ERROR"})
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[server_name] = session

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self.sessions = {}

    async def _call(self, what: str, coro_fn):
        """[P5 AFTER] 모든 MCP 요청이 지나가는 관문: 시간 제한 + 예외를 '재시도 가능 여부'로 번역.

        - 시간 초과(asyncio.wait_for)        → TimeoutError        → with_retry가 재시도
        - SDK의 시간 초과(MCPError, "timed out") → TimeoutError        → 재시도 (Before: 재시도 안 됨)
        - 그 밖의 MCPError(잘못된 인자 등)     → ToolError(recoverable=False) → 즉시 실패
        - 연결이 끊김(서버 프로세스 종료)       → ToolError(recoverable=True)
        """
        try:
            async with self._lock:   # stdio 세션 하나를 공유하므로 한 번에 한 요청씩 (Before와 같음)
                return await asyncio.wait_for(coro_fn(), timeout=MCP_TIMEOUT)
        except asyncio.TimeoutError:
            raise TimeoutError(f"MCP {what}: {MCP_TIMEOUT}s 안에 응답 없음") from None
        except MCPError as e:
            if "timed out" in str(e).lower():
                raise TimeoutError(f"MCP {what}: {e}") from e
            raise ToolError("MCP_ERROR", f"MCP {what}: {e}", recoverable=False) from e
        except (ConnectionError, EOFError, BrokenPipeError) as e:
            raise ToolError("MCP_DISCONNECTED", f"MCP {what}: 연결 끊김 ({e})", recoverable=True) from e

    @traceable(run_type="tool", name="mcp.call_tool")
    async def call_tool(self, name: str, arguments: dict, server: str = "ops") -> dict:
        if self._flaky_pending and name == "get_monitoring_status":
            self._flaky_pending = False
            raise asyncio.TimeoutError("simulated transient timeout (Wave 9 demo)")
        # [P5 BEFORE] async with self._lock:
        # [P5 BEFORE]     result = await self.sessions[server].call_tool(name, arguments)   ← 시간 제한 없음
        result = await self._call(f"call_tool({name})",
                                  lambda: self.sessions[server].call_tool(name, arguments))
        return json.loads(result.content[0].text)

    @traceable(run_type="tool", name="mcp.list_resource_templates")
    async def list_resource_templates(self, server: str) -> list:
        result = await self._call("list_resource_templates",   # [P5 AFTER] 시간 제한
                                  lambda: self.sessions[server].list_resource_templates())
        return _attr(result, "resourceTemplates", "resource_templates")

    @traceable(run_type="tool", name="mcp.find_resource_template")
    async def find_resource_template(self, template_name: str) -> tuple[str, str]:
        """연결된 서버들을 순서대로 조회해 template_name을 제공하는 서버를 찾는다."""
        for server_name in self.sessions:
            templates = await self.list_resource_templates(server_name)
            matched = next((t for t in templates if t.name == template_name), None)
            if matched is not None:
                return server_name, _attr(matched, "uriTemplate", "uri_template")
        raise ValueError(
            f"MCP resource template not found on any connected server: {template_name}")

    @traceable(run_type="tool", name="mcp.read_resource")
    async def read_resource(self, uri: str, server: str) -> str:
        # [P5 BEFORE] async with self._lock:
        # [P5 BEFORE]     result = await self.sessions[server].read_resource(uri)
        result = await self._call(f"read_resource({uri})",
                                  lambda: self.sessions[server].read_resource(uri))
        return result.contents[0].text

    @traceable(run_type="tool", name="mcp.list_prompts")
    async def list_prompts(self, server: str) -> list:
        result = await self._call("list_prompts", lambda: self.sessions[server].list_prompts())   # [P5 AFTER]
        return result.prompts

    @traceable(run_type="tool", name="mcp.find_prompt")
    async def find_prompt(self, prompt_name: str) -> str:
        """연결된 서버들을 순서대로 조회해 prompt_name을 제공하는 서버를 찾는다."""
        for server_name in self.sessions:
            prompts = await self.list_prompts(server_name)
            if any(p.name == prompt_name for p in prompts):
                return server_name
        raise ValueError(
            f"MCP prompt not found on any connected server: {prompt_name}")

    @traceable(run_type="tool", name="mcp.get_prompt")
    async def get_prompt(self, name: str, arguments: dict, server: str = "ops") -> str:
        result = await self._call(f"get_prompt({name})",   # [P5 AFTER]
                                  lambda: self.sessions[server].get_prompt(name, arguments))
        return result.messages[0].content.text
