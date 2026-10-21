# 발표 자료 1부 — 문제 인식 (Before, 고치는 순서대로)

- 수치 출처: `bench/results/before.md`, `bench/results/baseline_accuracy.csv`, `outputs/before/evidence/`
- 캡처 경로는 모두 `outputs/before/captures/` 기준이다.
- (추정) = 증거로 확정하지 못한 판단이다.

---

## 슬라이드 A. 측정 방법을 바꾸니 문제가 보였다

| 기존 지표 (응답이 왔는가) | 새 지표 (정답을 맞혔는가) |
|---|---|
| 성공률 **0.97** (29/30) | 매뉴얼(runbook) 정답률 **0.739** |
| | 조사 범위(recall) **0.775** |
| | LLM 채점 품질 **0.855** (q08 0.25, q05 0.6) |

- 캡처: `terminal/S10_baseline_accuracy.png`, `terminal/S13_langsmith_evaluate_baseline.png`
- 대본: "응답만 세면 97점이었습니다. 정답 세트를 만들어 다시 채점하니, 4번 중 1번은 틀린 매뉴얼을 주고 있었습니다."

## 슬라이드 B. 문제 지도 (고치는 순서)

| 순서 | 문제 | 수준 | 영향 지표 |
|---|---|---|---|
| ① | P1 여러 시스템을 물어도 1개만 조사 | L3 | 조사 범위, 정확도 |
| ② | P2 맞는 규칙이 없으면 무조건 db-down | L2 | **검색 정확도** |
| ③ | P3·P4·P9 불필요한 분석 + 동기 호출 → 300초 멈춤 | L3 | **지연시간**, 비용 |
| ④ | P5·P6 재시도가 안 되고, 실패해도 화면에 표시 없음 | L3 | **retry**, 안정성 |
| ⑤ | P7 빈 입력 허용, 이력 유실 | L3 | 안정성 |
| ⑥ | P11 답변 검증이 형식만 봄 | L2 | 품질 |
| ⑦ | E15 동기 세션 저장, P10 v1 롤백 | L2 | 구조 |

- ①~④가 발표 요구 지표(지연시간·비용·검색 정확도·retry)에 하나씩 대응한다.
- 대본: "찾은 문제를 정답률에 주는 영향이 큰 순서로 정렬했습니다."

---

## 슬라이드 C. ① P1 여러 시스템을 물어도 1개만 조사

- **기대**: 질문에 나온 시스템을 모두 조사한다.
- **실제**: q04~q06은 3회 반복 모두 첫 번째 시스템만 조사했다(9/9건, recall 0.5).
- **증거**: plan 입력에 `시스템: web-01` 한 줄만 들어간다. 코드 보정은 research가 **0개일 때만** 동작한다(`agent/ollama_llm.py:205`).
- 캡처: `S2_q06_only_one_system.png`, `terminal/S3_q05_plan_trace.png`, `code/C01_P1_plan_supplement_only_when_empty.png`, `code/C02_P1_prompt_single_system.png`
- 대본: "'두 서비스 공통 원인을 분석해줘'라고 해도 한 서비스만 봤습니다. 모델이 1개만 내면 코드가 보충하지 않는 구조였습니다."

## 슬라이드 D. ② P2 맞는 규칙이 없으면 무조건 db-down

- **기대**: 증상에 맞는 매뉴얼을 고르고, 이상이 없으면 "이상 없음"이라고 답한다.
- **실제**:
  - q05(web-01 CPU 급증)에 **DB 다운 매뉴얼**이 붙었다(3/3).
  - q08(감시하지 않는 billing-service)은 엉뚱한 auth-service를 조사했다(3/3, judge 0.25).
- **증거**: 분류 규칙에 하나도 걸리지 않으면 db-down으로 폴백한다(`agent/graph.py:213`).
- 캡처: `S1_q05_multi_system_db_down.png`, `code/C03_P2_db_down_fallback.png`
- 대본: "CPU가 급증했다고 했는데 DB 다운 대응 절차를 안내했습니다."

## 슬라이드 E. ③ P3·P4·P9 응답 하나가 서버를 300초 멈춤

- **기대**: 분석은 필요할 때만 하고, 기다리는 동안에도 다른 요청을 처리한다.
- **실제**:
  - q01 1회차는 314.9초 만에 실패했다. 그중 `analyze` 단계 하나가 **300.07초 동안 멈춰** 있다가 `ReadTimeout`으로 끝났다.
  - 비교 분석은 incident 8종 중 7종에서 실행됐다. 필요한 질문은 q06 하나다.
  - q03은 같은 질문인데 응답시간이 70.6초~152.2초로 흔들렸다.
- **증거**:
  - async 노드 안에서 동기 HTTP 호출을 한다(`agent/ollama_llm.py:104`).
  - 분석 실행 여부를 모델 판단에 그대로 맡긴다(`agent/graph.py:127`).
  - write 토큰 수가 1,863~3,537인데 답변 길이는 107~120자로 거의 같다. qwen3의 "생각" 토큰으로 (추정)한다.
- 캡처: `terminal/S11_q01_timeout_trace.png`, `terminal/S12_q03_write_tokens.png`, `terminal/S4_q05_node_timing.png`, `code/C04_P3_gate_trusts_model.png`, `code/C05_P4_sync_llm_call_in_async_node.png`, `code/C10_P9_timeout_and_think.png`
- 대본: "필요 없는 분석 단계가 동기로 호출되면서 300초 동안 멈췄습니다. 문제 4개가 한 번에 겹친 사례입니다."

## 슬라이드 F. ④ P5·P6 재시도는 동작하지 않고, 실패는 조용함

- **기대**: 일시적인 오류는 재시도하고, 실패하면 화면에 오류를 알린다.
- **실제**:
  - retry가 **0회**다. MCP 시간 초과는 `MCPError`로 오는데, 재시도 코드는 `asyncio.TimeoutError`만 잡는다.
  - 답변 중 Ollama를 끄면 백엔드에는 `RemoteProtocolError`가 찍히는데, **화면에는 아무 표시가 없다**.
- **증거**: `agent/retry.py:18`, `agent/graph.py:172`(gather에 예외 격리 없음), `web_chat.html:203`
- 캡처: `S6_ollama_down_silent_failure.png`, `terminal/S6_backend_log_on_ollama_down.png`, `terminal/S8_offline_repro.png`, `code/C06_P5_retry_and_mcp_timeout.png`, `code/C07_P6_no_isolation_no_error_event.png`
- 대본: "재시도 코드는 있었지만, 실제로 발생하는 예외를 잡지 못해 한 번도 동작하지 않았습니다."

## 슬라이드 G. ⑤~⑦ 그 밖의 문제 (한 장에 묶음)

| 문제 | 실제 | 캡처 |
|---|---|---|
| P7 API | 빈 메시지도 200 OK로 받고 답한다. 중간에 끊긴 턴과 v1 스트림은 이력이 저장되지 않는다 | `terminal/S7_stream_empty_message.png`, `code/C08_P7_stream_endpoint_unprotected.png` |
| P11 답변 검증 | incident 23건 모두 1회에 합격, 반려 0건. 30자 이상이고 "1)"만 있으면 통과한다 | `code/C12_P11_validate_format_only.png` |
| E15 세션 저장 | async 서버에서 동기 sqlite를 쓰고 연결 하나를 공유한다 | `code/C13_E15_sync_sqlite_session.png` |
| P10 v1 롤백 | 장애 질문에도 모니터링을 조회하지 않는다(fake 응답 문구에 의존) | `S9_v1_no_monitoring.png`, `code/C11_P10_v1_rollback_condition.png` |

- 대본: "이 문제들은 지표 영향이 작아서 뒤로 미뤘고, 끝내지 못한 항목은 한계에서 설명하겠습니다."
