# 4단계 — P5 MCP 시간 제한·재시도 + P6 부분 실패 격리·오류 표시

| 항목 | 내용 |
|---|---|
| 수준 | L3 |
| 매핑 | P5: C3-b / K10 · P6: C3-a·C3-i / K10·K12·K4·K5 |
| 사용자 문제 목록 | #3 MCP 실제 타임아웃·재시도 미흡, #4 부분 실패 격리 없음, #5 SSE 오류 처리 부족 |
| 커밋 | `git log --oneline -- outputs/final-report/06_step4_P5_P6.md` 맨 위 줄 |

## ② 정의
- **기대**:
  - 일시적인 오류는 재시도한다.
  - 조사 하나가 실패해도 나머지로 답한다.
  - 실패하면 화면에 원인과 재시도 가능 여부를 보여준다.
- **실제**:
  - retry 합계가 **0**이었다. MCP 시간 초과는 `MCPError`로 오는데, 재시도 코드는 `asyncio.TimeoutError`만 잡았다(S8).
  - 답변 중 Ollama를 끄면 백엔드에는 `RemoteProtocolError`가 찍히는데, **화면에는 아무 표시가 없었다**(S6).
- **증거**:
  - `outputs/before/evidence/S8_offline_repro.txt`
  - `outputs/before/captures/S6_ollama_down_silent_failure.png`, `terminal/S6_backend_log_on_ollama_down.png`

## ③ 원인
| 위치 (Before) | 문제 |
|---|---|
| `agent/retry.py:18` | `except asyncio.TimeoutError`만 잡는다. SDK의 `MCPError(timed out)`는 바로 실패한다 |
| `agent/mcp_client.py:75-77` 등 | MCP 호출에 시간 제한이 없다 |
| `agent/graph.py:168` | runbook `read_resource`에는 재시도가 없다 |
| `agent/graph.py:172` | `asyncio.gather`에 예외 격리가 없다. 하나가 실패하면 전체 요청이 실패한다 |
| `server.py:157-190` | 스트림 안에서 예외가 나면 연결만 끊긴다. `Error` 이벤트도 `[DONE]`도 없다 |
| `web_chat.html:203` | `es.onerror`가 창만 닫는다. 사용자에게 알리지 않는다 |

## ④ 대안
| 문제 | 대안 | 선택 | 이유 |
|---|---|---|---|
| P5 | A. retry가 모든 예외를 재시도 / **B. Tool layer에서 예외를 번역(시간 초과 → `TimeoutError`, 그 외 → `ToolError(code, recoverable)`)하고 retry는 그 분류만 본다** | B | K10: 영구 오류(잘못된 인자)까지 재시도하면 지연만 늘어난다 |
| P6 격리 | A. `gather(return_exceptions=True)` / **B. 코루틴마다 try/except + `Semaphore`** | B | 실패 task마다 code와 대상 시스템을 이벤트로 남길 수 있다(K12) |
| P6 표시 | A. HTTP 상태 코드만 / **B. SSE `Error{code, recoverable, message}` 이벤트 후 `[DONE]`, 화면에 빨간 말풍선 + "다시 시도"** | B | K4·K5: 스트림은 이미 200으로 시작해서 상태 코드를 바꿀 수 없다 |

## ⑤ 실행
| 파일:줄 | 변경 |
|---|---|
| `agent/errors.py` (새 파일) | `ToolError`(12), `classify`(21): 예외를 `{code, recoverable, message}`로 바꾼다 |
| `agent/mcp_client.py:35` | `MCP_TIMEOUT=10`초 |
| `agent/mcp_client.py:82` `_call` | 모든 MCP 요청이 거치는 관문. `wait_for`로 시간 제한을 걸고, 예외를 번역한다 |
| `agent/retry.py:15` `_is_transient` | `TimeoutError`와 `recoverable` ToolError만 재시도한다. 대기는 0.5 → 1.0초 |
| `agent/graph.py:185-219` | Before gather를 주석으로 남겼다. `run_one`에 try/except, `Semaphore(4)`, runbook에도 `with_retry` |
| `agent/graph.py:223-231` | 실패한 task는 `failed` 상태와 `TaskFailed` 이벤트를 남기고, "조회 실패" 사실을 write에 넘긴다 |
| `agent/graph.py` `_no_runbook_note` | 조회 실패를 "정상"으로 착각하지 않는다 |
| `server.py:150-160` | `/chat` 예외 → 503 `{error: {code, recoverable, message}}` |
| `server.py:172-183` | 스트림: `_events()`를 감싸서 예외를 `Error` 이벤트로 바꾸고, **항상** `[DONE]`을 보낸다 |
| `web_chat.html:43-47`, `101-107` | 빨간 오류 말풍선, 오류 코드, "다시 시도" 버튼 |
| `web_chat.html:218-224`, `236-244` | `Error` 이벤트 처리. `[DONE]` 전에 끊기면 "연결이 끊겼습니다"를 표시한다 |
| `agent/ollama_llm.py` `OLLAMA_URL` | 환경변수로 바꿀 수 있게 했다(장애 재현용) |

## ⑥ 검증 (`outputs/after/evidence/P5_P6_failure_repro.txt`)
| 상황 | Before | After |
|---|---|---|
| 답변 도중 Ollama 연결 끊김 | 스트림이 끊기고 화면에 아무 표시가 없다 | `Error{code: LLM_STREAM_BROKEN, recoverable: true}` → `[DONE]`. 서버 로그에 `stream_failed` JSON 한 줄 |
| Ollama에 연결 불가 + `/chat` | 500 Internal Server Error | **503** `{"code":"LLM_UNAVAILABLE","recoverable":true}` |
| 첫 MCP 호출의 의도적 타임아웃(Wave 9) | 재시도 0회(측정 전에 소진됨) | `TaskCompleted retries: 1` → 재시도로 복구 |
| SDK 시간 초과 `MCPError` | 재시도 대상 아님 | `TimeoutError`로 번역되어 재시도된다(단위 테스트) |
| 조사 2개 중 1개 실패 | 요청 전체가 예외 | 1개 `TaskCompleted` + 1개 `TaskFailed`, 답변은 계속된다(단위 테스트) |

pytest는 34 passed다.

## ⑦ 재발 방지 (테스트)
- `test_with_retry_retries_timeout_and_recoverable_tool_error`
- `test_with_retry_does_not_retry_permanent_error`
- `test_mcp_sdk_timeout_becomes_retryable_timeout_error`
- `test_mcp_call_has_time_limit`
- `test_research_isolates_one_failed_task`
- `test_stream_sends_error_event_then_done`

## 트레이드오프
- MCP 호출마다 10초 제한이 있다. 아주 느린 Tool은 실패로 처리된다(`MCP_TIMEOUT`으로 조정).
- 재시도하면 최악의 경우 그 task가 0.5 + 1.0초 + 호출 시간 × 3만큼 늦어진다.
- 부분 응답은 일부 시스템 수치가 빠진 답이다. 답변에 "조회 실패"를 명시하게 했지만 사용자가 놓칠 수 있다.
- write(답변 생성) 도중 끊기면 재시도하지 않고 오류를 표시한다. 이미 화면에 일부 토큰이 나갔기 때문이다. 사용자가 "다시 시도"를 누른다.
- stdio 세션이 하나뿐이라 `Semaphore(4)`여도 MCP 호출은 lock 때문에 한 번에 하나씩 처리된다(Before와 같다).

---

## 직접 확인하는 방법 (수동)
```bash
grep -n "P5 \|P6 " agent/*.py server.py web_chat.html | head -50
./.venv/bin/python3 -m pytest tests -q -k "retry or mcp or isolates or stream"
bash outputs/after/scripts/p6_repro.sh     # 사용자가 띄운 Ollama·서버(8100)는 건드리지 않는다 (:8199, :11500 사용)
```
- `p6_repro.sh`는 다음을 차례로 한다.
  1. `cut_proxy.py`(:11500 → :11434)를 띄운다.
  2. 서버를 `OLLAMA_URL=:11500`으로 :8199에 띄운다.
  3. `/chat/stream`을 호출한다.
  4. 4초 뒤 프록시가 연결을 끊는다.
  5. 서버의 `gen()`(`server.py:172`)이 예외를 잡아 `classify()`(`agent/errors.py:21`)로 분류한 뒤, `Error` 이벤트와 `[DONE]`을 보낸다.

**화면** (Before S6과 같은 장면)
1. 터미널 2에서 서버를 이렇게 다시 띄운다:
   ```bash
   python3 outputs/after/scripts/cut_proxy.py --cut-after 8 &
   OLLAMA_URL=http://127.0.0.1:11500/api/chat bash sh/run_agent_ollma.sh
   ```
2. :8600에서 `log-service 디스크 공간이 부족하다는 알림이 왔어요`를 입력한다.
3. 8초 뒤 **빨간 말풍선 "⚠️ 답변을 받는 도중 LLM 연결이 끊겼습니다"**, "오류 코드: LLM_STREAM_BROKEN", **[다시 시도]** 버튼이 나오면 성공이다.
4. 끝나면 서버를 평소처럼 `bash sh/run_agent_ollma.sh`로 다시 띄운다.

## 커밋 보고 7항목
1. **커밋**: 위 표
2. **Before 증거**:
   - `outputs/before/captures/S6_ollama_down_silent_failure.png`, `terminal/S6_backend_log_on_ollama_down.png`, `terminal/S8_offline_repro.png`
   - `code/C06`, `C07`
3. **After 비교**: 8단계에서 같은 질문과 같은 8초 지연으로 `outputs/after/captures/S6_...png`를 찍는다. Before는 빈 화면, After는 빨간 말풍선이다.
4. **선택**: Tool layer에서 예외 번역 + 코루틴별 격리 + SSE Error 이벤트(K10·K12·K4)
5. **트레이드오프**: 위 절
6. **핵심 변경**: `agent/mcp_client.py:82`, `agent/retry.py:15`, `agent/graph.py:192-231`, `server.py:172`, `web_chat.html:218`
7. **화면**: 위 "화면"
