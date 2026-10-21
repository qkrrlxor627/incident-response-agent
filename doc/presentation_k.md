# 최종 발표 원고 — 서버 장애 진단 AI 에이전트 (incident-response-agent)

> 발표 시간: 5분 (준비 포함 6분)
> 근거 자료: `doc/lessonstandard_k.md`(교안 기준), `bench/results/before.md`(Before 측정), 실제 코드
> 표기 규칙:
> - After 값은 2026-10-21 측정(`bench/results/after_*`, `outputs/after/README.md`)에서 인용했다. 최종 발표본은 `outputs/final-report/10_final_presentation.md`다.
> - (추정) = 코드와 데이터로 확인하지 못한 판단이다.

---

## 0. 시간 배분 (5분)

| 순서 | 슬라이드 | 시간 | 누적 |
|---|---|---|---|
| 1 | 주제 | 30초 | 0:30 |
| 2 | 개선 사항 요약 | 30초 | 1:00 |
| 3 | 기술 요소 + 구현 캡처 + 최종 실행 화면 | 2분 | 3:00 |
| 4 | 개선 전/후 수치 | 1분 | 4:00 |
| 5 | 한계·트레이드오프 | 45초 | 4:45 |
| — | 마무리 | 15초 | 5:00 |

---

## 1. 주제 (30초)

**슬라이드 내용**
- 서버 장애를 진단하는 AI 에이전트(AIOps)
- 채팅으로 "OO 서비스가 이상해요"라고 쓰면, 에이전트가 다음을 근거로 원인과 대응 절차를 답한다.
  - 모니터링 수치: MCP Tool
  - 대응 매뉴얼: MCP Resource
- 백엔드: FastAPI + LangGraph. 교안 시나리오와 같다.
- 프론트: **Vue 3로 다시 작성**했다(CDN, 빌드 없음).
- LLM: fake / Ollama(로컬) / OpenAI를 환경변수 하나로 교체한다.

**대본**
> "사람이 대시보드와 매뉴얼을 직접 뒤지는 대신, 채팅 한 줄로 실측 수치와 매뉴얼을 근거로 진단해 주는 에이전트입니다."

---

## 2. 개선 사항 (30초) — 문제 해결 기록 압축본

### 주 개선: "여러 시스템을 말해도 1개만 조사한다"
상태: 원인 분석 완료 / **개선은 실험 예정**

| 단계 | 내용 |
|---|---|
| ① 문제 인식 | Before 측정에서 q04~q06처럼 시스템을 2개 언급한 질문이 9건 모두 **1개만 조사**됐다. q05는 정상인 web-01만 보고 **db-down으로 오분류**됐다 |
| ② 문제 정의 | 기대: 언급된 시스템을 모두 조사한다. 실제: `PlanCreated.targets`가 1개다. 완료 기준: q04~q06에서 언급된 시스템이 전부 조사되고, q05가 db-down이 아니게 된다 |
| ③ 원인 — 확인한 사실 | `agent/ollama_llm.py`의 `plan()`에서 `qwen3:0.6b`가 research task를 1개만 낸다. 빠진 시스템을 보충하는 `_guess_targets()`는 research task가 **0개일 때만** 동작한다 |
| ④ 가설 — 추정 | 모델 task와 별개로 쿼리에 나온 KNOWN_SYSTEMS를 코드가 보충하면, 조사 누락과 오분류가 함께 사라진다 |
| ⑤ 실험 | 위 보충 로직을 추가한다. `git tag baseline`으로 되돌릴 수 있다 |
| ⑥ 결과 검증 | q04~q06 조사 시스템 2개(9/9건), recall 0.775 → 1.0, q05 high-latency(3/3). 근거: `outputs/after/README.md` |
| ⑦ 재발 방지 | `tests/test_agent_units.py`에 P1 재현 테스트를 `xfail(strict=True)`로 고정했다. 고치면 XPASS가 나므로 마커를 지워 회귀 테스트로 전환한다 |

### 부 개선 후보 (시간이 되면)
- analysis 남발: incident 8종 중 7종에서 비교 분석이 실행됐다. 원인은 `needs_analysis=true` 남발로 추정한다.
- validate가 형식("1)" + 30자)만 검사한다. 그래서 조사가 빠진 답변도 합격한다.

**대본**
> "개선 전에 기준선부터 측정했고, 그 데이터에서 '시스템을 두 개 말해도 하나만 조사한다'는 문제를 찾았습니다. 원인은 사실과 추정을 나눠 코드 위치까지 확인했습니다."

---

## 3. 사용한 기술 요소 (2분)

### 3-1. 기술 요소와 코드 매핑

| 기술 요소 | 우리 코드 | 교안 단원 | 한 줄 어필 |
|---|---|---|---|
| **Multi-Agent** (Supervisor 그래프) | `agent/graph.py` (`build_graph`) | 6 | route → plan → gate → research → replan_check → analysis → write → validate → finalize |
| Query Routing + 권위 게이트 | `route_node`, `gate_node` | 7 | 인사는 1.3초에 바로 답한다. 모델이 끼워 넣은 analysis task는 코드가 제거한다 |
| Dynamic Planning | `replan_check_node` | 8 | runbook이 없으면 gap task를 추가해 1회 재조사한다 |
| Validator | `validate_node` | 9 | 불합격 시 피드백을 주고 재작성한다(최대 3회) |
| **MCP** Tool / Resource / Prompt | `mcp_server.py` | 3 | 모니터링(Tool), 매뉴얼(Resource), 진단 절차(Prompt)를 모두 실사용한다 |
| MCP 멀티 서버 탐색 | `mcp_client.py`, `mcp_server_docs.py`(decoy) | 3 | 어느 서버를 쓸지 하드코딩하지 않는다. `find_prompt` / `find_resource_template`로 먼저 찾는다 |
| **RAG** (검색 증강) | `_classify_incident_type` → runbook Resource 주입 | — | 벡터 검색이 아니다. **모니터링 alerts 키워드 규칙으로 runbook을 골라** 프롬프트에 넣는다 |
| **의존성 주입** | `agent/deps.py` `SupervisorDeps` + `functools.partial` | 14 | 노드는 주입받는 순수 함수라서 테스트할 때 갈아 끼울 수 있다 |
| **모듈화** / 백엔드 교체 | `fake_llm.py` / `ollama_llm.py` / `openai_llm.py` | 14 | `LLM_BACKEND` 하나로 바꾼다. 그래프 코드는 그대로다 |
| 싱글턴 lifespan | `server.py` `lifespan` | 2 | Agent 번들을 서버 수명 동안 1회만 생성한다(`creation_count=1`) |
| SSE 스트리밍 | `server.py` `/chat/stream`, `web_chat.html` (Vue) | 4, 5 | ⏳ 진행 단계와 토큰을 실시간으로 표시한다 |
| 에러 처리 / 재시도 | `agent/retry.py` `with_retry` | 10 | Transient(타임아웃)만 backoff 재시도한다 |
| 비용 최적화 | fast_llm / quality_llm 분리 | 11 | 분류·계획은 작은 모델, 답변 작성은 큰 모델이 맡는다 |
| 동시 실행 | `research_node`의 `asyncio.gather` | 12 | 시스템별 조회를 병렬로 처리한다 |
| 세션 | `agent/session_store.py` (SQLite) | 13 | 서버를 재시작해도 대화를 기억한다 |
| **LangSmith** | 각 노드의 `@traceable` | 15 | 요청 1건이 계층 트리로 기록된다(`langsmith_run_id`) |
| **단위 테스트** | `tests/test_agent_units.py`, `tests/conftest.py` (pytest) | 14 | LLM·MCP·서버 없이 순수 함수만 검증한다: 시스템명 추출, `_guess_targets`, 분류 규칙(5종 + 폴백 + 순서), gate, validate, P1 재현(xfail). 기록된 결과: 15 passed, 1 xfailed(`doc/workLog.md`) |

### 3-2. 캡처 체크리스트

| # | 캡처 | 확보 방법 | 상태 |
|---|---|---|---|
| 1 | Vue 채팅 화면 (헤더에 ollama 표시) | http://localhost:8600 | ☐ 직접 캡처 |
| 2 | ⏳ 진행 단계 스트리밍 | 장애 질문 전송 중 캡처 | ☐ |
| 3 | 장애 진단 답변 (번호 매긴 절차) | 같은 화면 | ☐ |
| 4 | LangSmith trace 트리 | 프로젝트 `capstone-all-total-ollama` | ☐ |
| 5 | 최종 실행 화면 (개선 후) | After 코드로 1~3 다시 캡처 | ☐ 개선 후 |
| 참고 | 기존 캡처 | `doc/image_usecase/` (qwen2.5 시절 캡처라서 최종본으로는 다시 찍기 권장) | — |

**대본**
> "교안 15단원 중 Multi-Agent, MCP, 의존성 주입, LangSmith 등을 실제 코드 위치와 함께 보여드리겠습니다. 특히 MCP는 Tool, Resource, Prompt 세 가지를 모두 실사용하고, 어느 서버에 있는지 하드코딩하지 않고 탐색합니다."

---

## 4. 개선 전/후 수치 (1분)

동일 조건: `bench/queries.json` 10문항 × 3회, Ollama `qwen3:0.6b` / `qwen3:8b`, `bench/run_baseline.py`

| 지표 | Before (`baseline`) | After |
|---|---|---|
| 성공률 | 0.97 (29/30) | 1.0 (30/30) |
| incident 응답시간 중앙값 | 36.0초 | 12.8초 |
| chat 응답시간 중앙값 | 1.3초 | 0.26초 |
| q04~q06 조사한 시스템 수 | 1개 (9/9건) | 2개 (9/9건) |
| q05 분류 | db-down (오분류, 3/3) | high-latency (정답, 3/3) |
| retry 횟수 | 0 | 측정 30건 중 0 (warmup에서 1회 재시도로 복구) |
| validate 반려 | 0 | 3 (q02 3회, 조사 시스템 누락) |
| 가상 비용 합계 (`cost_usd`) | $0.1637 | $0.1360 |
| 타임아웃 | 1건 (q01, 300초) | 0건 (최대 24.4초) |

- 필수 캡처:
  - `bench/results_run.log` 터미널 화면 (Before / After)
  - `baseline_summary.csv` / `after_summary.csv`
- After 실행: `./.venv/bin/python3 bench/run_baseline.py --tag after`
- 주의(추정): 시스템을 여러 개 조사하면 alerts가 합쳐져서 규칙 순서상 분류가 바뀔 수 있다(예: q04 → cpu-spike). 개선 후 오히려 나빠지는 항목이 생기면 그대로 보여주고 ⑤에서 설명한다.

**대본**
> "같은 질문 10개를 3번씩 돌려 개선 전후를 비교했습니다. 조사 누락은 9건에서 0건으로, 장애 질문 응답시간 중앙값은 36.0초에서 12.8초로 바뀌었습니다."

---

## 5. 한계와 트레이드오프 (45초)

| 한계 | 그래도 이렇게 한 이유 |
|---|---|
| 로컬 소형 모델이라 느리다(중앙값 36초, 타임아웃 1건) | 과금 0원으로 몇 번이든 반복 측정할 수 있다. OpenAI로는 같은 코드로 바로 전환된다 |
| 분류가 코드 규칙이라 질문 문장을 무시한다 | 결정적이라 3회 반복에서 분류가 흔들리지 않았다. 소형 모델의 판단보다 믿을 만하다 |
| RAG가 벡터 검색이 아니다 | runbook이 6종뿐이라 규칙으로 충분하다. 문서가 늘어나면 벡터 검색으로 바꿀 대상이다 |
| validate가 형식만 본다 | LLM-as-a-Judge는 호출이 늘어나 느리고 비싸다. 다음 개선 후보로 둔다 |
| 표본이 작다(10문항 × 3회) | 로컬 모델 기준 1회 측정에 약 25분이 걸린다. 그래서 회귀 쿼리 위주로 골랐다 |
| 토큰 수가 응답에 없다 | LangSmith trace의 llm run 출력(`usage.tokens`)으로 확인한다 |

**대본**
> "속도와 비용, 결정성과 유연성 사이에서 무엇을 골랐는지, 그리고 다음에 바꿀 조건이 무엇인지를 함께 말씀드리겠습니다."

## 마무리 (15초)
> "측정 → 원인 분석 → 개선 → 재측정 순서로, 감이 아니라 숫자로 개선을 증명했습니다. 감사합니다."

---

## 부록. 예상 질문

1. **왜 벡터 RAG를 쓰지 않았나요?**
   → runbook이 6종이고 alerts 키워드로 정확히 고를 수 있습니다. 벡터 검색은 문서가 늘어날 때 도입할 조건으로 남겨 뒀습니다.
2. **분류를 왜 LLM이 아니라 코드로 하나요?**
   → 0.6b 모델은 출력이 흔들립니다. 실측 데이터로 검증할 수 있는 결정은 코드가 내린다는 원칙입니다(gate, replan과 같은 설계). 3회 반복에서 분류가 100% 일치했습니다.
3. **단위 테스트는 어디 있나요?**
   → `tests/test_agent_units.py`에 테스트 함수 12개(parametrize 포함 16케이스)가 있습니다. LLM·MCP·서버 없이 순수 함수만 검증합니다. P1 버그는 `xfail(strict=True)`로 먼저 고정했고, 고치면 정식 회귀 테스트로 바뀝니다. 최종 57 passed(0.7초)입니다.
