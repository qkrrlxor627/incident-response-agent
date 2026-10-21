"""[P5·P6 AFTER] 에러 분류 공통 모듈.

Before에는 에러 종류를 나누는 곳이 없었다.
  - retry.py는 asyncio.TimeoutError만 재시도했다. 그런데 MCP SDK의 시간 초과는 MCPError로 온다
    → 실제 MCP 시간 초과는 한 번도 재시도되지 않았다 (Before retry 합계 0, S8).
  - /chat/stream은 예외가 나면 연결만 끊겼다 → 화면은 조용히 멈췄다 (S6).
여기서 "어떤 에러인가(code)"와 "다시 시도하면 나아질 수 있는가(recoverable)"를 한 번에 정한다.
"""
import httpx


class ToolError(Exception):
    """MCP Tool/Resource 호출 실패. recoverable=True면 with_retry가 다시 시도한다."""

    def __init__(self, code: str, message: str, recoverable: bool):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


def classify(exc: BaseException) -> dict:
    """예외 → 화면과 로그에 보낼 {code, recoverable, message}.

    recoverable=True: 잠시 후 같은 질문을 다시 보내면 성공할 수 있다 (화면에 '다시 시도' 버튼).
    recoverable=False: 입력이나 설정 문제라 다시 보내도 같다.
    """
    if isinstance(exc, ToolError):
        return {"code": exc.code, "recoverable": exc.recoverable, "message": str(exc)}
    if isinstance(exc, httpx.ConnectError):
        return {"code": "LLM_UNAVAILABLE", "recoverable": True,
                "message": "LLM 서버(Ollama)에 연결할 수 없습니다. 실행 중인지 확인해 주세요."}
    if isinstance(exc, httpx.TimeoutException) or isinstance(exc, TimeoutError):
        return {"code": "TIMEOUT", "recoverable": True,
                "message": "응답 시간이 제한을 넘었습니다. 잠시 후 다시 시도해 주세요."}
    if isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError)):
        return {"code": "LLM_STREAM_BROKEN", "recoverable": True,
                "message": "답변을 받는 도중 LLM 연결이 끊겼습니다."}
    if isinstance(exc, httpx.HTTPStatusError):
        return {"code": f"LLM_HTTP_{exc.response.status_code}", "recoverable": exc.response.status_code >= 500,
                "message": f"LLM 서버가 오류를 돌려줬습니다 ({exc.response.status_code})."}
    return {"code": "INTERNAL", "recoverable": False, "message": f"{type(exc).__name__}: {exc}"}
