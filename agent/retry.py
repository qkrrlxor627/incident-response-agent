"""Wave 9 — Transient 에러만 exponential backoff로 재시도.

[P5 BEFORE] asyncio.TimeoutError(일시적)만 재시도하고, 그 외(ValueError 등 영구적)는 즉시 전파한다.
  → MCP SDK의 시간 초과는 MCPError로 와서 재시도 대상이 아니었다 (Before retry 합계 0).
[P5 AFTER] 재시도 대상 = TimeoutError + recoverable=True인 ToolError.
  mcp_client.py가 SDK 예외를 이 두 종류로 바꿔서 던진다 (agent/mcp_client.py의 _call).
"""
import asyncio

from langsmith import traceable

from .errors import ToolError


def _is_transient(exc: BaseException) -> bool:
    # Python 3.11부터 asyncio.TimeoutError는 내장 TimeoutError와 같은 클래스다
    return isinstance(exc, TimeoutError) or (isinstance(exc, ToolError) and exc.recoverable)


@traceable(name="with_retry")
# [P5 BEFORE] async def with_retry(fn, *args, retries: int = 3, base_delay: float = 0.3, **kwargs):
async def with_retry(fn, *args, retries: int = 3, base_delay: float = 0.5, **kwargs):
    """fn을 최대 retries번 시도한다. 대기: 0.5초 → 1.0초 (지수 백오프)."""
    attempt = 0
    while True:
        attempt += 1
        try:
            result = await fn(*args, **kwargs)
            return result, attempt - 1   # (결과, 재시도 횟수)
        # [P5 BEFORE] except asyncio.TimeoutError:
        except Exception as exc:   # [P5 AFTER] 일시적인 에러인지는 _is_transient가 판단
            if not _is_transient(exc) or attempt >= retries:
                raise
            # [P5 BEFORE] delay = base_delay * (3 ** (attempt - 1))
            delay = base_delay * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
