# 5단계 — P7 API 입력 검증 · SSE 헤더 · 이력 보장 · 스트림 trace

| 항목 | 내용 |
|---|---|
| 수준 | L3 |
| 매핑 | C3-e / K2(Pydantic 검증)·K4(SSE)·K13(세션) |
| 사용자 문제 목록 | #13 스트리밍 경로 보호 부족 (입력 검증·헤더·이력 저장·trace) |
| 커밋 | `git log --oneline -- outputs/final-report/07_step5_P7.md` 맨 위 줄 |

## ② 정의
- **기대**:
  - 빈 입력이나 너무 긴 입력은 422로 거절한다.
  - 스트림은 버퍼링 없이 흘러간다.
  - 실패하거나 v1으로 처리한 턴도 이력에 남는다.
- **실제**:
  - `/chat`과 `/chat/stream` 모두 빈 메시지를 **200 OK**로 받아 LLM까지 호출했다(S7).
  - 중간에 끊긴 턴과 v1 스트림은 이력이 저장되지 않았다(S8).
  - 스트림 요청은 LangSmith에 루트 run이 없었다.
- **증거**: `outputs/before/evidence/S7_stream_empty_message.txt`, `S8_offline_repro.txt`, `captures/code/C08_P7_stream_endpoint_unprotected.png`

## ③ 원인 (Before)
| 위치 | 문제 |
|---|---|
| `server.py:35-37` `ChatRequest` | `message: str`에 길이나 공백 조건이 없다 |
| `server.py:148-149` `chat_stream` | 쿼리 파라미터 검증이 없다 |
| `server.py:135-136`, `188-189` | 성공한 뒤에만 user와 assistant를 함께 저장한다 → 실패한 턴은 질문까지 사라진다 |
| `server.py:159-163` | v1 분기는 저장 코드 자체가 없다 |
| `server.py:192` | `StreamingResponse`에 SSE 헤더가 없다 |

## ④ 대안
| 대안 | 장점 | 단점 | 선택 |
|---|---|---|---|
| A. 핸들러 안에서 `if not message` 검사 | 간단하다 | 두 엔드포인트에 중복된다. 422 형식이 제각각이다 | ✗ |
| **B. Pydantic 모델에 계약을 두고(`Field` + `field_validator`), 스트림도 같은 모델로 검증** | 규칙이 한 곳에 있다. FastAPI 표준 422 형식이다(K2) | GET 쿼리라 모델 검증을 수동으로 한 번 호출한다 | ✅ |
| C. 스트림을 POST로 바꾼다 | 바디로 검증할 수 있다 | 브라우저 `EventSource`는 GET만 지원한다 → 프론트를 fetch 스트림으로 다시 짜야 한다 | ✗ (기준 외로 남김) |

## ⑤ 실행
| 파일:줄 | 변경 |
|---|---|
| `server.py:42-62` | Before `ChatRequest` 주석. `message` 1~2000자, 공백만 있으면 거절, `thread_id`는 영숫자·`_`·`-` 64자 |
| `server.py:153-163` | `/chat`: 질문을 **먼저** 저장한다 |
| `server.py:183-196` | `/chat/stream`: Query 길이 제약 + `ChatRequest`로 같은 규칙을 검증한다 → 422 |
| `server.py:211` | `@traceable(name="chat_stream_request")`: 스트림 요청도 LangSmith 루트 run이 된다 |
| `server.py:214`, `220-221` | 스트림도 질문을 먼저 저장하고, v1 분기도 답변을 저장한다 |
| `server.py:251-257` | `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive` |

## ⑥ 검증 (`outputs/after/evidence/P7_validation_headers_history.txt`)
| 확인 | Before | After |
|---|---|---|
| `/chat` 빈 메시지 | 200 | **422** `string_too_short` |
| `/chat/stream` 공백 메시지 | 200 | **422** `message must not be blank` |
| 스트림 헤더 | `content-type`만 | `cache-control: no-cache`, `x-accel-buffering: no` |
| 이력 | 성공한 v2만 저장 | 질문 먼저 + 답변(v1·v2 모두) |
| 실패한 스트림의 질문 | 사라짐 | 남는다(단위 테스트) |

pytest는 39 passed다.

## ⑦ 재발 방지 (테스트)
- `test_chat_rejects_invalid_message[""/"   "/2001자]`: `/chat`과 `/chat/stream` 둘 다 확인한다
- `test_chat_rejects_bad_thread_id`
- `test_stream_has_sse_headers_and_keeps_question_when_it_fails`

## 트레이드오프
- 2000자를 넘는 긴 로그를 붙여 넣으면 거절된다. 로그 분석 기능을 만들면 한도를 다시 정해야 한다.
- 질문을 먼저 저장하므로, 실패한 턴은 답 없이 질문만 이력에 남는다. 다음 턴에서 모델이 "답이 없는 질문"을 보게 된다.
- `thread_id` 형식을 제한해서, 기존에 공백이나 한글이 들어간 thread_id를 쓰던 클라이언트는 422를 받는다. 현재 클라이언트(web_chat, bench, eval)는 모두 형식에 맞는다.

---

## 직접 확인하는 방법 (수동)
```bash
grep -n "P7 " server.py
./.venv/bin/python3 -m pytest tests -q -k "reject or sse_headers"
# 서버(8100)가 떠 있을 때
curl -s -w " → HTTP %{http_code}\n" -X POST localhost:8100/chat -H 'content-type: application/json' -d '{"message":""}'
curl -s -D - -o /dev/null -G localhost:8100/chat/stream --data-urlencode "message=web-01 장애 진단" | grep -i "cache-control\|x-accel"
sqlite3 session.db "select thread_id, role, substr(content,1,30) from messages order by rowid desc limit 6"
```
- `curl ... /chat`의 실행 순서: FastAPI가 바디를 `ChatRequest`(`server.py:51`)로 바꾸려다 `min_length`에 걸린다 → `chat()` 함수는 아예 실행되지 않는다 → 422.

**화면**
- 입력창은 원래 빈 문자열을 보내지 않는다(`web_chat.html` `send()`의 `if (!text) return`). 그래서 이 단계는 화면보다 curl로 확인한다.
- 이력: :8600에서 `제 이름은 민수입니다` → `제 이름이 뭐였죠?`를 보내면 "민수"라고 답한다.

## 커밋 보고 7항목
1. **커밋**: 위 표
2. **Before 증거**: `outputs/before/captures/terminal/S7_stream_empty_message.png`, `code/C08_P7_stream_endpoint_unprotected.png`
3. **After 비교**: 8단계에서 같은 curl 명령의 출력을 `outputs/after/captures/terminal/S7_stream_empty_message.png`로 렌더링한다. 200 → 422를 비교한다.
4. **선택**: B. Pydantic 계약 한 곳(K2)
5. **트레이드오프**: 위 절
6. **핵심 변경**: `server.py:51-62`, `server.py:192-196`, `server.py:211-221`, `server.py:253-257`
7. **화면**: 위 "화면"
