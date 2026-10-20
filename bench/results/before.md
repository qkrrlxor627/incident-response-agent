# Before 기준선 리포트 (baseline)

| 항목 | 값 |
|---|---|
| 측정 시각 | 2026-10-20 14:14 (KST) 시작 |
| 코드 버전 | git tag `baseline` (에이전트 코드 수정 없음) |
| 백엔드 | `ollama`, supervisor `v2` |
| 모델 | fast=`qwen3:0.6b`, quality=`qwen3:8b` |
| 질의셋 | `bench/queries.json` (`doc/regression_test_queries.md` 10건), 쿼리당 3회 |
| 원본 / 요약 | `baseline_raw.jsonl` (33건) / `baseline_summary.csv` |
| 실행 | `./.venv/bin/python3 bench/run_baseline.py --repeat 3 --tag baseline` |

## 1. 전체 결과

| 구분 | 건수 | 평균 | 중앙값 | 최대 |
|---|---|---|---|---|
| 전체 호출 | 33 | 45.5초 | 32.4초 | 300초(타임아웃) |
| incident 경로 (성공 건) | 23 | 51.7초 | 36.0초 | 152.2초 |
| chat 경로 | 9 | 1.3초 | 1.3초 | 1.5초 |

- **성공률: 29/30 = 0.97.** 다턴 케이스는 마지막 턴만 센다. 실패 1건은 q01 1회차 타임아웃(300초)이다.
- 가상 비용 합계(`cost_usd`, 실측 토큰 × 가상 단가): $0.1637. Ollama 로컬 추론이라 실제 과금은 없다.
- retry 횟수: 전 구간 0이다. 의도적 flaky(`agent/mcp_client.py:72`)는 서버 프로세스당 첫 Tool 호출 1번뿐인데, 측정 전 수동 테스트에서 이미 소진됐다(워밍업에서도 retry_count=0).
- validate 시도 횟수: incident 23건 모두 1회 만에 합격했다. 재작성은 0건이다.

## 2. 쿼리별 분류 결과

| id | 질의 요약 | route | 조사한 시스템 | incident_type = runbook | analysis 실행 | 중앙값 | 성공 |
|---|---|---|---|---|---|---|---|
| q01 | payments CPU 급증 | incident | payments-service | cpu-spike | ✅ | 47.6초 | 2/3 |
| q02 | cache 메모리 증가 | incident | cache-service | memory-leak | ✅ | 33.2초 | 3/3 |
| q03 | log 디스크 부족 | incident | log-service | disk-full | ✅ | **92.7초** | 3/3 |
| q04 | gateway → payments 타임아웃 | incident | gateway-service **만** | network-timeout | ✅ | 32.5초 | 3/3 |
| q05 | web-01 CPU + auth 커넥션 풀 | incident | web-01 **만** | **db-down** | ✅ | 31.9초 | 3/3 |
| q06 | payments + cache 공통 원인 | incident | payments-service **만** | cpu-spike | ✅ | 62.5초 | 3/3 |
| q07 | 로그인 느림 (시스템 미언급) | incident | auth-service (폴백) | high-latency | ❌ (gate가 1개 제거) | 31.9초 | 3/3 |
| q08 | billing-service 느림 | incident | auth-service (폴백) | high-latency | ✅ | 54.2초 | 3/3 |
| q09 | 안녕, 너는 누구야? | chat | — | — | — | 1.3초 | 3/3 |
| q10 | 이름 기억 2턴 | chat | — | — | — | 2.5초 (2턴 합) | 3/3 ("민수입니다" 응답) |

- 3회 반복 사이에 분류가 달라진 쿼리는 없다. 성공한 실행은 3회 모두 같은 결과가 나왔다.
- `expected_incident_type`은 비워 뒀다(`bench/queries.json`). 채울 때 참고: 분류는 질문 문장이 아니라 **조사한 시스템의 모니터링 alerts**로 정해진다(3-2 참고).

## 3. 이상해 보이는 결과

### 3-1. 여러 시스템을 말해도 하나만 조사한다 (q04, q05, q06) — 가장 큰 문제
- 증상: 9건 모두 계획(plan) 단계에서 시스템을 1개만 골랐다. `PlanCreated.targets`가 1개다.
  - q04는 payments-service를 조사하지 않았다.
  - q05는 auth-service를 조사하지 않았다.
  - q06은 cache-service를 조사하지 않았다.
- 영향: q05는 정상 상태인 web-01만 보고 분류 규칙에 하나도 걸리지 않았다. 그래서 기본값 `db-down`으로 빠졌다. 실제 답변에도 "auth-service 커넥션 풀 정보가 누락되어 확인 불가"라고 적혔다.
- 원인 위치(추정):
  - `agent/ollama_llm.py`의 `plan()`. `qwen3:0.6b`가 research task를 1개만 내놓는다.
  - 쿼리에 나온 시스템을 전부 복구하는 `_guess_targets()`는 research task가 **0개일 때만** 동작한다. 1개라도 있으면 빠진 시스템을 보충하지 않는다.

### 3-2. 분류가 기본값(db-down)으로 빠진다 (q05)
- 원인 위치: `agent/graph.py`의 `_classify_incident_type()`. 모니터링 status/alerts에 `_INCIDENT_TYPE_RULES` 키워드가 하나도 없으면 무조건 `db-down`을 반환한다.
- 질문에 "커넥션 풀"이 있어도 질문 문장은 보지 않는다.
- 참고(추정): 여러 시스템을 제대로 조사하게 고쳐도, alerts가 합쳐진 뒤 규칙 순서(latency → pool → cpu → … → timeout)상 앞에 있는 키워드가 이긴다. 예를 들어 q04에서 payments-service까지 조사하면 `CPU 91%` 때문에 network-timeout이 아니라 cpu-spike가 될 수 있다.

### 3-3. 비교 분석(analysis)이 거의 모든 질문에서 실행된다
- 증상: analysis가 필요한 질문은 q06뿐인데, incident 8종 중 7종(q07 제외)에서 `AnalysisCompleted`가 기록됐다.
- 원인 위치(추정):
  - `qwen3:0.6b`가 route/plan에서 `needs_analysis=true`를 남발한다.
  - `agent/graph.py`의 `gate_node()`는 `needs_analysis=False`일 때만 analysis task를 지운다.
- 영향: 시스템을 1개만 조사한 경우에도 "비교 분석"을 돌린다. 시간이 늘어난다(추정).

### 3-4. 타임아웃 1건 (q01 1회차, 300초)
- 클라이언트 timeout 300초 안에 응답이 없었다. 바로 다음 같은 질문은 47.6초, 27.2초에 끝났다.
- 원인은 **미확인**이다. 후보(추정): Ollama 모델 교체/로드 지연, `qwen3:8b`의 긴 생성. 서버 로그와 LangSmith trace로 확인이 필요하다.

### 3-5. 응답시간 편차가 크다 (q03, q04)
- q03: 70.6초 → 152.2초 → 92.7초. 답변은 107~120자로 오히려 가장 짧다.
- q04: 1회차만 108.5초, 나머지는 32초.
- 원인은 미확인이다. 로컬 모델의 생성 길이나 thinking 편차로 추정한다.

### 3-6. 검증(validate)이 한 번도 반려하지 않았다
- `agent/graph.py`의 `validate_node()`는 "30자 이상 + `1)` 포함"만 검사한다.
- 그래서 q05처럼 조사가 빠진 답변도 1회 만에 합격했다. 내용의 정확성은 검증하지 않는다.

## 4. 측정 가능 여부

| 항목 | 얻는 곳 | 상태 |
|---|---|---|
| incident_type | `events`의 `ReplanCheck.target` (is_sufficient=false) | 측정함 |
| 선택된 runbook | `events`의 `TaskCompleted(source=runbook).target` | 측정함 |
| MCP 호출 | `TaskCompleted.source` (monitoring=Tool `get_monitoring_status`, runbook=Resource) | 측정함 |
| MCP Prompt 호출 | `events`에 없다. 코드상 incident 경로에서 항상 호출된다(`plan_node`) | 간접 (코드 근거) |
| retry 횟수 | `metadata.retry_count` | 측정함 (전부 0) |
| 최종 응답 | `reply` | 측정함 (raw에 원문 저장) |
| 토큰 수 | 응답에 없다. `cost_usd`(가상)로만 간접 추정 가능 | 응답 기준 측정 불가 → LangSmith 확인 |
| `eval/run_eval.py` | 이 폴더에 없다 | 해당 없음 |

## 5. LangSmith에서 쿼리별 토큰 확인하는 방법
1. https://smith.langchain.com → 프로젝트 `capstone-all-total-ollama`로 간다(`sh/run_agent_ollma.sh`가 지정한 이름).
2. `baseline_raw.jsonl`의 `langsmith_run_id`(= `chat_request` 루트 run)로 검색한다.
3. 트리에서 `ollama_fast.*` / `ollama_quality.*` (run_type=llm) 노드를 연다.
   - 각 메서드가 `(content, usage)`를 반환하므로, 출력값의 `usage.tokens`(prompt_eval_count + eval_count)를 더하면 쿼리별 총 토큰이 된다.
   - LangSmith의 토큰 칸(usage_metadata)에 자동 표시되는지는 **확인하지 않았다.** 코드에 usage_metadata 설정은 없다.

## 6. After 측정 시
- `git checkout baseline`로 이 상태를 재현할 수 있다.
- 개선 후에는 `--tag after`로 같은 스크립트를 돌리면 `after_raw.jsonl` / `after_summary.csv`가 나온다.
- 측정 전에 서버를 새로 띄우면 첫 Tool 호출에서 retry 1회가 생긴다. 스크립트의 워밍업 요청이 이를 흡수한다.
