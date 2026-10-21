# 최종 발표 (5분) — 장애 대응 Multi-Agent 개선

- 수치 출처: `outputs/after/README.md`(Before/After 표), `bench/results/{baseline,after}_*`
- 캡처 경로 기준: `outputs/before/captures/`, `outputs/after/captures/` (같은 파일명 = 같은 장면)
- 문제 인식 슬라이드는 `01_problem_recognition.md`를 그대로 쓴다(슬라이드 A~G).
- 시간 배분: 주제 0:30 / 개선 2:00 / 기술 1:00 / 수치 1:00 / 한계 0:30

---

## 1. 주제 (0:30)

**운영 장애 질문에 답하는 Multi-Agent 에이전트의 정확도·지연·안정성 개선**

- 기능: 사용자가 "web-01 CPU 급증, auth-service 커넥션 풀도 확인해줘"라고 물으면 에이전트가 다음을 거쳐 대응 절차를 답한다.
  1. 질문 분류
  2. 조사 계획
  3. MCP로 모니터링 조회
  4. 장애 유형 판단 → runbook 검색
  5. 답변 작성
  6. 검증
- 문제: 응답 성공률은 **97%**였지만 정답 세트로 다시 재니 **4번 중 1번은 틀린 매뉴얼**을 줬다(0.739). 응답 하나가 서버를 **300초** 멈추기도 했다.
- 캡처: `outputs/before/captures/S1_q05_multi_system_db_down.png` ↔ `outputs/after/captures/S1_q05_multi_system_db_down.png`

> 대본: "장애 질문에 매뉴얼을 찾아 답하는 에이전트입니다. 응답률은 97%였는데, 정답을 맞혔는지 다시 재 보니 74%였습니다. 이 차이를 줄이는 것이 이번 개선의 목표였습니다."

## 2. 기능 개선 사항 (2:00) — 고친 순서

| # | 문제 (사용자 목록 #) | 고친 방법 | 결과 | 문서 |
|---|---|---|---|---|
| 1 | P1 시스템 2개를 물어도 1개만 조사 (#1, #14) | 질문에 나온 시스템을 코드가 **항상 보충**. 3개 파일의 중복 로직을 `agent/systems.py`로 통합 | recall 0.775 → **1.0** | `03_step1_P1.md` |
| 2 | P2 근거가 없으면 무조건 db-down (#2) | 이상 있는 시스템을 언급 순서대로 보고, 근거가 없으면 runbook 생략 | runbook 정답률 0.739 → **1.0** | `04_step2_P2.md` |
| 3 | P3·P4·P9 동기 LLM 호출, 불필요한 분석, 300초 timeout, thinking 토큰 (#6, #7, #8, #10) | `AsyncClient`, 이중 게이트, 단계별 timeout, `think:false`, 노드별 `elapsed_ms` | incident 중앙값 36.0 → **12.8초**, `/health` 1.73 → **0.03초** | `05_step3_P3_P4_P9.md` |
| 4 | P5·P6 재시도가 안 되고, 실패가 조용함 (#3, #4, #5) | MCP 예외를 재시도 가능 여부로 번역, task별 격리, SSE `Error` 이벤트, 빨간 말풍선 | 화면에 오류 코드와 [다시 시도] 버튼 | `06_step4_P5_P6.md` |
| 5 | P7 빈 입력 200, 이력 유실 (#13) | Pydantic 계약, SSE 헤더, 질문 선저장 | 빈 입력 → **422** | `07_step5_P7.md` |
| 6 | P11 형식만 검증 (#9) | 규칙 3개 + 8b LLM judge, 재작성 1회 | judge 0.855 → **0.955** | `08_step6_P11.md` |
| 7 | E15·P10 동기 세션, v1 롤백 (#15) | `to_thread` 비동기 저장소, v1이 질문으로 장애 판단 | v1에서도 모니터링 조회 | `09_step7_E15_P10.md` |
| + | 측정이 찾은 회귀: think 끔 → 라우터 오분류 | route 권위 보정 | q10 14.2 → **0.52초** | `09b_step8_route_regression.md` |

캡처 (Before ↔ After, 같은 파일명):
- `S1_q05_multi_system_db_down.png`: 1개 조사·db-down → 2개 조사·high-latency·"근거 확인됨"
- `S2_q06_only_one_system.png`: 1개 → 2개 + 비교 분석
- `S6_ollama_down_silent_failure.png`: 아무 표시 없음 → 빨간 말풍선
- `S9_v1_no_monitoring.png`: v1 조회 없음 → web-01 조회

> 대본: "원인을 확인한 순서대로 고쳤습니다. 첫째, 실모델 로그를 보니 0.6b 모델이 시스템 이름 대신 'get_monitoring_status Tool for web-01' 같은 문장을 내고 있었고, 코드는 이것을 첫 시스템으로 덮어쓰고 있었습니다. 그래서 조사 범위는 모델이 아니라 코드가 정하게 바꿨습니다. …"

## 3. 사용한 기술 요소 (1:00)

| 기술 | 어디에 | 이번에 바꾼 것 | 캡처 |
|---|---|---|---|
| **Multi-Agent** (LangGraph Supervisor) | `agent/graph.py` `build_graph`: route → plan → gate → research ⇄ replan → analysis → write ⇄ validate | gate 이중 조건, validate에 judge, route 보정 | `after/captures/S1` 진행 단계 |
| **MCP** (Tool·Resource·Prompt) | `mcp_server.py`, `agent/mcp_client.py` | 모든 호출에 시간 제한 + 예외 번역(`_call`), Prompt에 시스템 전부 전달 | `after/captures/code/C06`, `C02` |
| **RAG** (runbook 검색) | 장애 유형 분류 → MCP Resource `runbook://incident-response/{type}` → write 프롬프트에 주입 | 분류 근거를 시스템별로, 근거 없으면 검색 안 함 | `after/captures/code/C03` |
| **DI** (의존성 주입) | `SupervisorDeps` + `functools.partial`, `create_session_store()` 팩토리 | 노드에 시간 측정 래퍼를 덧씌움, 저장소 팩토리 주입 | `after/captures/code/C13` |
| **LangSmith** | 노드·LLM·MCP `@traceable`, `evaluate()` 실험 | 스트림 요청도 루트 run, judge도 trace | `after/captures/terminal/S13_langsmith_evaluate_after.png` |
| **모듈화** | `agent/systems.py`(시스템 추출), `agent/errors.py`(에러 분류) | 3개 파일의 중복 제거(#14) | `after/captures/code/C02` |
| **단위 테스트** | `tests/test_agent_units.py` | 15 passed + 1 xfail → **57 passed** (LLM·MCP·서버 없이 0.7초) | `./.venv/bin/python3 -m pytest tests -q` |

- 최종 실행 화면: `outputs/after/captures/S1_q05_multi_system_db_down.png`

## 4. 개선 전/후 수치 (1:00)

| 지표 (미션 C4) | Before | After | 캡처 |
|---|---|---|---|
| **검색 정확도** (runbook 정답률) | 0.739 | **1.0** | `before/captures/terminal/S10_baseline_accuracy.png` ↔ `after/captures/terminal/S10_after_accuracy.png` |
| 조사 범위 recall | 0.775 | **1.0** | 같음 |
| LLM-judge 품질 | 0.855 | **0.955** | `S13_langsmith_evaluate_baseline.png` ↔ `S13_langsmith_evaluate_after.png` |
| **지연시간** (incident 중앙값) | 36.0초 | **12.8초** (−64%) | `terminal/S4_q05_node_timing.png` |
| 최대 응답시간 | 300초 (타임아웃) | **24.4초** | `terminal/S11_q01_timeout_trace.png` |
| q03 편차 | 70.6~152.2초 | **11.2~11.8초** | `terminal/S12_q03_write_tokens.png` |
| **비용** (가상, 33호출) | $0.1637 | **$0.1360** (−17%) | `after/captures/terminal/S14_after_bench_run.png` |
| **retry** | 0회 (실제 예외를 못 잡음) | 첫 MCP 호출 타임아웃을 재시도로 복구, 측정 중 타임아웃 0건 | `S9`·`S6` "(재시도 성공)", `terminal/P5_P6_failure_repro.png` |
| 응답 성공률 (기존 지표) | 0.97 | 1.0 | — |

> 대본: "검색 정확도는 74%에서 100%로, 장애 질문 응답시간은 36초에서 13초로 줄었습니다. 비용도 17% 줄었습니다. 같은 10개 질문을 3번씩, Before와 같은 모델로 측정했습니다."

## 5. 한계 및 트레이드오프 (0:30)

| 항목 | 내용 |
|---|---|
| 평가 표본 | 질문 10개 × 3회. 정답 세트에 맞춘 개선이라 **과적합 위험**이 있다. 새로운 질문 유형으로 검증하지는 않았다 |
| 규칙 기반 판단 | 시스템 추출, 장애 키워드, route 보정이 모두 키워드 규칙이다. "결제 서버가 안 돼요"처럼 이름이 없는 표현은 놓친다 |
| 검증 비용 | 8b judge가 요청마다 약 3초를 쓴다. 규칙 ②가 q02를 매번 재작성시켜 q02만 22.9초다 |
| think 끔 | 지연 −60%를 얻었지만 라우터 회귀가 생겼다(보정함). 다른 단계의 품질 저하는 judge 점수로만 확인했다 |
| 판정 하락 | q04 judge 0.95 → 0.75 (LangSmith 1회 실행) |
| 남은 병목 | 응답의 60~70%가 8b write다. 모델 경량화나 캐시가 다음 과제다 |
| 하지 않은 것 | LangGraph 공식 checkpointer 전환, 스트림 POST 전환, 시스템 별칭 사전 |

> 대본: "규칙으로 정확도를 올린 만큼, 규칙 밖의 질문에는 약합니다. 그리고 속도를 위해 끈 thinking이 라우팅 오류를 만들었는데, 정답 세트로 측정했기 때문에 바로 발견할 수 있었습니다. 측정 방법을 바꾼 것이 이번 작업에서 가장 큰 개선이었다고 생각합니다."
