# Before 증거 묶음 (코드 수정 전, 2026-10-21)

- 대상 코드: 에이전트 코드가 git tag `baseline`과 같다(`git diff baseline HEAD -- agent server.py mcp_server.py web_chat.html` 결과가 비어 있음).
- 실행 조건: `LLM_BACKEND=ollama`, fast=`qwen3:0.6b`, quality=`qwen3:8b`, `SUPERVISOR_VERSION=v2`(S9만 v1). Before 측정(`bench/results/before.md`)과 같은 조건이다.
- 이 단계에서는 문제를 **찾아서 기록만** 했다. 개선안 열은 교안 기준(`doc/lessonstandard_k.md`) 채택안이고, 아직 적용하지 않았다.
- 직접 다시 실행하는 명령: `doc/guide.md` 맨 끝의 "Before 증거 수집 — 직접 실행할 때의 터미널 명령"

## 1. Before 성능 (미션 C4: 지연시간·비용·검색 정확도·retry)

| 지표 | Before | 출처 |
|---|---|---|
| 응답 성공률 (기존 지표: HTTP 200 여부) | 29/30 = 0.97 | `bench/results/before.md` |
| **장애 유형(runbook) 정답률** = 검색 정확도 | **0.739** (raw 재채점) / **0.75** (LangSmith evaluate) | `evidence/S10`, `evidence/S13` |
| **조사 범위 recall** (기대 시스템 중 조사한 비율) | **0.775** / **0.786** | `evidence/S10`, `evidence/S13` |
| 조사 정밀도 precision | 0.87 / 0.875 | 같음 |
| 답변 토픽 포함률 | 0.718 / 0.778 | 같음 |
| LLM-judge 품질 (Ollama qwen3:8b, 4기준 평균) | 0.855 (q08 0.25, q05 0.6 최저) | `evidence/S13` |
| incident 응답시간 중앙값 / chat | 36.0초 / 1.3초 | `before.md` |
| 가상 비용 합계 | $0.1637 | `before.md` |
| retry 합계 / 타임아웃 | 0 / 1건(q01, 300초) | `before.md` |

- 정답 세트: `bench/eval_set.json`(근거 포함). Before 입력인 `bench/queries.json`은 수정하지 않았다.
- LangSmith 실험: `baseline-36e5189f` (Dataset `incident-agent-eval-v1`). URL은 `evidence/S13` 맨 위에 있다.

## 2. 문제 → 증거 → 교안 기준 개선안

| # | 문제 정의 (실제 → 기대) | 화면·터미널 증거 | 코드 캡처 | 교안 기준 개선안 (채택안) | K / C |
|---|---|---|---|---|---|
| P1 | 여러 시스템을 물어도 첫 시스템 1개만 조사 → 언급된 시스템 전부 조사 | S1, S2, S3(plan 입력에 `시스템: web-01`만), S8, S10(q04~q06 recall 0.5) | C01, C02 | 코드의 권위 정규화로 쿼리 속 KNOWN_SYSTEMS를 항상 보충. MCP Prompt에 시스템 목록 전달. 공통 모듈로 분리 | K6 K7 K3 K14 / C3-a C3-b C3-f |
| P2 | 정상·미존재 시스템도 db-down → 증상에 맞는 runbook, 이상이 없으면 "이상 없음" | S1, S8, S10(q05·q08 type X) | C03 | 주 시스템(첫 언급) 우선 분류, 전부 healthy면 runbook 불필요 판정. db-down 폴백 제거 | K8 / C3-c |
| P3 | analysis가 거의 항상 실행(gate 제거 0건) → 필요할 때만 실행 | S3(needs_analysis=true), S11(불필요한 analyze에서 300초 정지) | C04 | 이중 게이트: LLM 판단(1) + 코드 권위 게이트(2, research 2개 이상일 때만 허용) | K7 K11 / C3-a |
| P4 | async 노드 안의 동기 LLM 호출로 이벤트 루프 정지 → 대기 중에도 다른 요청 처리 | S5(최대 1.73초), S8(2초 동안 tick 1회), **S11(q01 300초 정지)** | C05 | 블로킹 금지: `httpx.AsyncClient`로 바꾸고 route/plan/analyze를 async로 | K12 / C3-d |
| P5 | MCP 호출에 timeout 없음, SDK timeout(`MCPError`)은 재시도 대상이 아님 → 시간 제한 + 재시도 | S8(시도 1회, MCPError) | C06 | Tool layer에서 timeout→`TimeoutError`, 그 외→`ToolError(code, recoverable)`. `with_retry` 0.5s×3, 총 3회. `read_resource`도 재시도 | K10 / C3-b |
| P6 | task 하나 실패 = 요청 전체 실패, 화면은 조용히 멈춤 → 부분 응답 + 오류 표시 | **S6(Ollama 종료 → 오류 표시 없음)**, S11 | C07 | 코루틴별 try/except 격리 → 부분 응답, `Semaphore`. 스트림은 `Error{code, recoverable}` 이벤트 후 Done. 화면에서 재시도 가능/불가 구분 | K10 K12 K4 K5 / C3-a C3-i |
| P7 | `/chat`·`/chat/stream` 모두 빈 입력 200, 스트림 헤더 없음, 중단된 턴과 v1 스트림의 이력 유실 → 입력 검증·헤더·이력 보장 | S7, S8(repro_stream) | C08 | `ChatRequest`에 길이 제약, 스트림 POST + 같은 모델, `X-Accel-Buffering`/`Cache-Control` 헤더, 사용자 메시지 선저장, v1 분기도 저장 | K2 K4 K13 / C3-e |
| P8 | bench가 응답 여부만 셈(0.97) → 정답률로 측정 | S10, S13 | C09 | 고정 Dataset + `evaluate()`, heuristic + LLM-judge 혼합 — **이 단계에서 구축 완료**(`bench/eval_set.json`, `rescore.py`, `eval_langsmith.py`) | K15 / C4 C3-e |
| P9 | 단계별 시간 제한 없음(전부 300초), qwen3 thinking 토큰으로 write 편차(추정) → 단계별 예산과 관측 | S4(write 86%), S11, **S12(65.7초/1,863토큰 ~ 147.4초/3,537토큰, 답변 107~120자)** | C10 | 노드별 `elapsed_ms` + JSON 구조화 로그(run_id 연결). 단계별 timeout과 요청 전체 시간 예산. `think` 옵션 명시(답변 품질과 함께 측정) | K15 K9 K10 / C3-e |
| P10 | v1 롤백이 fake 문구("도와드릴까요")에 의존 → 실모델에서도 롤백 가능 | **S9(장애 질문에 모니터링 조회 없음)**, S8 | C11 | 기준 외 제안: 장애 판단을 route와 같은 규칙으로, 대상은 쿼리에서 추출 | 기준 외 |
| P11 | validate가 형식(30자 + "1)")만 검사, 3회째 강제 통과 → 내용 검증 | S13(q05 judge 0.6, q08 0.25인데 validate는 합격) | C12 | LLM-as-a-Judge 4기준 + 규칙 검사 혼합, 재작성 1회 상한 | K9 / C3-a |
| E15 | 동기 sqlite 세션 저장소(연결 공유, 인덱스 없음) | — | C13 | 비동기 checkpointer + `create_checkpointer()` 팩토리 + lifespan 주입 | K13 K14 |

## 3. 이번에 새로 확인한 것 (워크스루 추정 → 확정)

- **#5 q01 300초 타임아웃 원인 확정**: `ollama_fast.analyze`가 300.07초 만에 `ReadTimeout`으로 끝났다(S11). 불필요한 analysis(P3) + 동기 호출(P4) + 단계별 timeout 없음(P9) + 실패 격리 없음(P6)이 겹친 결과다.
- **P1 입력 쪽 원인 확인**: plan 입력의 표준 절차에 `- 시스템: web-01` 한 줄만 들어간다(S3). LangSmith에는 정규화 후 출력만 남아서 모델의 원래 출력은 확인하지 못했다.
- **q03 편차**: write 단계의 토큰 수에 비례한다(S12). `think` 옵션이 없어서 생긴 qwen3 숨은 사고 토큰으로 추정한다(prompt와 eval 토큰이 합산돼 기록됨 → 확정하려면 eval_count를 따로 기록해야 함).
- **P4 실측 영향**: q05에서 `/health` 지연이 최대 1.73초였다(S5). write는 비동기 스트림이라 막지 않는다. 최악의 경우는 q01의 300초다(S11).
- **P7 범위 확대**: `/chat`도 빈 메시지를 200으로 받는다(S7). `ChatRequest.message`에 길이 조건이 없다.

## 4. 파일 목록

| 폴더 | 내용 |
|---|---|
| `captures/` | 실제 Vue 화면(Playwright + 설치된 Chrome): S1 S2 S6 S9 |
| `captures/code/` | 문제 코드 C01~C13. 실제 소스 줄을 읽어 렌더링했고, 빨간 줄이 문제 지점이다 |
| `captures/terminal/` | `evidence/*.txt`(실제 명령 출력)를 터미널 스타일로 렌더링한 것 |
| `evidence/` | 원본 텍스트 증거. S3·S4·S11·S12는 LangSmith trace에서, S13은 evaluate에서 나왔다 |
| `scripts/` | 재현·캡처 스크립트(`doc/guide.md`의 명령에서 사용) |
