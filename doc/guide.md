# 과제 읽기 가이드 — all_total_vue (운영 인시던트 대응 에이전트)

> 폴더 안의 md 문서 10개(`doc/` 4개 + `data/runbooks/` 6개)를 기준으로 정리했다.
> 과제 요구사항이 적힌 별도 문서는 이 폴더에 없으니, 제출 조건은 수업 공지를 따로 확인할 것.

## 한 줄 요약

채팅으로 "OO 서비스가 이상해요"라고 말하면 **모니터링 수치(MCP Tool) + 대응 매뉴얼(MCP Resource)**을
근거로 진단 결과를 만들어 주는 LangGraph 에이전트다. LLM은 `fake` / `ollama` / `openai` 중 하나를
골라 꽂을 수 있고, 프론트엔드(`web_chat.html`)만 Vue 3로 새로 작성됐다. 백엔드는 원본 `all_total`과 같다.

---

## 읽는 순서

| 순서 | 문서 | 왜 이 순서인가 | 소요 |
|---|---|---|---|
| 1 | `doc/manual_ollma.md` | **"이게 뭘 하는 물건인지"**를 캡처 화면으로 먼저 본다. 과금 없는 로컬 버전이라 직접 따라 하기 좋다 | 10분 |
| 2 | `doc/README.md` → "주요 실행 방법" | 실제로 띄우는 방법을 익힌다 (venv → ollama → 서버 → 프론트) | 5분 |
| 3 | `doc/README.md` → "아키텍처 구성도" · "시퀀스 다이어그램" | 그래프 노드 흐름과 MCP 구조를 이해한다. **가장 중요** | 20분 |
| 4 | `doc/README.md` → "소스 디렉토리 구조" | 각 개념이 어느 파일에 있는지 연결한다 → 이후 코드 읽기용 지도 | 5분 |
| 5 | `data/runbooks/*.md` (6개, 각 7줄 정도) | 에이전트가 근거로 쓰는 매뉴얼 원문이다. 답변에 이 내용이 들어가는지 확인할 때 쓴다 | 5분 |
| 6 | `doc/regression_test_queries.md` | 직접 던져볼 **테스트 질문 10개**와 각 질문이 검증하는 동작 | 5분 |
| 7 | `doc/manual_openai.md` (선택) | 같은 시나리오의 OpenAI 버전이다. 끝의 "Ollama와 비교" 표만 봐도 된다. **실행하면 과금된다** | 5분 |

이 다음에는 코드를 이 순서로 읽으면 된다:
`server.py` → `agent/deps.py` → `agent/graph.py` → `agent/mcp_client.py` → `mcp_server.py` → `web_chat.html`

---

## 문서별 요점

### 1. manual_ollma.md — 사용 예 5가지 + 운영자 기능

| # | 사용 예 | 뒤에 있는 기술 개념 |
|---|---|---|
| 1 | 가벼운 인사 → 바로 대답 | **라우팅** (route=chat, 무거운 파이프라인을 건너뜀) |
| 2 | 장애 진단 요청 | plan → gate → research → replan → write → **validate** |
| 3 | 진행 상황 실시간 표시 (⏳) | **SSE 스트리밍** (`/chat/stream`) |
| 4 | 서버를 재시작해도 이름을 기억 | **SQLite 세션 저장소** (`session.db`) |
| 5 | 브라우저 채팅 화면 | `web_demo_server.py`가 프록시를 맡아 CORS 문제를 피함 |
| 운영 | 품질 자동 감시 | LangSmith **Dataset 평가 + Feedback**. 실패 사례를 감시 목록에 추가 |

- 중간에 보이는 "일시 오류 → 재시도 성공"은 **의도적으로 넣은 flaky 오류**다 (`retry.py` 시연용).

### 2. README.md — 핵심 개념 (시험·발표에 나올 만한 부분)

- **싱글턴**: `lifespan`에서 `SupervisorDeps`(LLM·세션·MCP)를 **딱 1번** 만들고 `app.state`로 공유한다.
- **백엔드 교체**: `LLM_BACKEND` 환경변수 하나로 LLM이 바뀐다. 그래프 코드는 그대로다.
- **버전 토글**: `SUPERVISOR_VERSION=v1`이면 legacy 선형 파이프라인(`supervisor_v1.py`), `v2`면 LangGraph로 돈다.
- **MCP 3종 capability** (`mcp_server.py`, 서버명 `ops`):
  - Tool `get_monitoring_status` → `data/monitoring.json`
  - Resource `runbook://incident-response/{type}` → `data/runbooks/*.md`
  - Prompt `incident_analysis_prompt`
- **MCP 멀티 서버 탐색**: `docs` 서버(`mcp_server_docs.py`)는 **decoy**다. 어느 서버를 쓸지 하드코딩하지 않고
  `find_prompt()` / `find_resource_template()`로 먼저 찾아본 뒤 요청한다.
- **v2 그래프 흐름**:
  ```
  route ─chat→ chat_answer
        └incident→ plan → gate → research ⇄ replan_check → analysis → write ⇄ validate → finalize
  ```
  - `gate`: 불필요한 task를 제거한다.
  - `replan_check`: 조사 결과가 부족하면 research로 되돌아간다.
  - `analysis`: `needs_analysis` task가 있을 때만 실행하고, 없으면 내부에서 건너뛴다.
  - `validate`: 형식이 미달이면 write로 되돌려 다시 쓰게 한다.
- **포트**: 에이전트 서버 `:8100`, 프론트/프록시 `:8600`.

### 3. regression_test_queries.md — 직접 돌려볼 질문

- 1~3, 8번: 시스템명 인식 (`KNOWN_SYSTEMS`). 목록에 없는 이름이면 `auth-service`로 폴백한다.
- 4~5번: 두 시스템을 동시에 언급한 경우
- 6번: `needs_analysis=true`를 유도해서 analysis 노드가 실행되는지 확인
- 7번: 시스템명을 말하지 않은 경우 → auth-service로 폴백
- 9번: chat 경로에서도 토큰 스트리밍(`AnswerToken`)이 되는지
- 10번: 세션 기억 (서버를 재시작한 뒤에도 유지되는지)

### 4. runbooks — 6종

`db-down`, `cpu-spike`, `disk-full`, `high-latency`, `memory-leak`, `network-timeout`.
모두 "1단계: `get_monitoring_status`로 확인"으로 시작한다. 즉 Tool 결과와 Resource 내용을 묶어서 쓰도록 짜여 있다.

---

## 빠른 실행 체크리스트

```bash
bash sh/setup_venv.sh          # 1회
cp .env.example .env           # LangSmith 키 입력 (OpenAI 키는 openai 모드에서만 필요)
bash sh/setup_ollama.sh        # 로컬 모델 준비 (qwen3:0.6b / 8b)
bash sh/run_agent_ollma.sh     # 터미널 1 — :8100
bash sh/run_frontend.sh        # 터미널 2 — http://localhost:8600
```

⚠️ 주의
- `run_agent_openai.sh`는 **실제로 과금**된다.
- `.env`(API 키)는 절대 커밋하거나 남에게 넘기지 말 것. 참고로 `sh/make_student_zip.sh`는 `.env`를 빼고 zip을 만드는 배포용 스크립트다.
- 스크립트 이름의 오타 `ollma`는 원래 이름 그대로다. 명령을 칠 때 주의할 것.

---

## 코드 파일별 함수·클래스 역할

> 실제 소스를 직접 읽고 정리했다. 줄 번호는 `파일:줄` 형식이다.

### 전체 지도

```
[브라우저] web_chat.html (Vue 3)
    │  EventSource /chat/stream
    ▼
web_demo_server.py (:8600, 프록시) ──httpx──▶ server.py (:8100, FastAPI)
                                                 │ lifespan에서 1회 생성
                                                 ▼
                                        SupervisorDeps (agent/deps.py)
                                  ┌──────────┼──────────────┬──────────────┐
                              fast/quality LLM   MCPClient        SqliteSessionStore
                          (fake/ollama/openai)  (agent/mcp_client.py)  (session.db)
                                                 │ stdio subprocess
                                       ┌─────────┴─────────┐
                                 mcp_server.py        mcp_server_docs.py
                                 ("ops", 실사용)        ("docs", decoy)
    v2: agent/graph.py (LangGraph)   /   v1: agent/supervisor_v1.py (legacy)
```

| 파일 | 줄 수 | 한 줄 역할 |
|---|---|---|
| `server.py` | 197 | FastAPI 백엔드. 의존성을 1회 조립하고 `/chat`, `/chat/stream`을 제공 |
| `agent/deps.py` | 17 | 의존성 묶음 `SupervisorDeps` dataclass |
| `agent/graph.py` | 338 | **핵심**. v2 LangGraph 노드 10개 + 분기 함수 + `build_graph` |
| `agent/supervisor_v1.py` | 31 | 롤백용 legacy 선형 파이프라인 |
| `agent/mcp_client.py` | 122 | MCP 서버 2개를 stdio로 띄우고 Tool/Resource/Prompt 호출 |
| `agent/retry.py` | 22 | Timeout만 지수 백오프로 재시도 |
| `agent/session_store.py` | 37 | SQLite 대화 이력 저장소 |
| `agent/fake_llm.py` | 125 | 결정론적 가짜 LLM (네트워크 X, 기본 백엔드) |
| `agent/ollama_llm.py` | 261 | 로컬 Ollama 실모델 백엔드 |
| `agent/openai_llm.py` | 238 | OpenAI API 실모델 백엔드 (과금) |
| `mcp_server.py` | 85 | MCP 서버 "ops": Tool·Resource·Prompt 3종 |
| `mcp_server_docs.py` | 33 | MCP 서버 "docs": 탐색 시연용 decoy |
| `web_demo_server.py` | 65 | 채팅 HTML 서빙 + 8100으로 프록시 (CORS 회피) |
| `web_chat.html` | 211 | Vue 3 채팅 UI (SSE 수신) |
| `bench/run_baseline.py` | — | (커밋 안 된 폴더) `/chat` 응답 기준선 측정 스크립트 |

---

### 1. `server.py` — FastAPI 진입점

| 이름 | 종류 | 역할 |
|---|---|---|
| `CREATION_COUNT` | 전역 변수 | 의존성 번들 생성 횟수. 싱글턴이면 항상 1 (`/health`로 확인) |
| `ChatRequest` | Pydantic 클래스 | `/chat` 요청 바디 검증 (`message`, `thread_id="default"`) |
| `_build_llms()` | 함수 | `LLM_BACKEND` 환경변수(fake/ollama/openai)를 보고 fast·quality LLM 쌍을 만든다. 모델명도 환경변수로 바꿀 수 있다 |
| `lifespan(app)` | async 컨텍스트 매니저 | 서버 시작 시 `MCPClient.start()` → LLM 생성 → `SupervisorDeps` 조립 → v2면 `build_graph`. 종료 시 MCP·DB 닫고 LangSmith 플러시 |
| `health()` | `GET /health` | instance_id, creation_count, 버전, 백엔드, 모델명 반환 |
| `version()` | `GET /version` | `SUPERVISOR_VERSION`만 반환 |
| `_metadata(result, run_id)` | 함수 | 그래프 결과 state에서 route·task 수·재시도·비용 등을 뽑아 응답 metadata로 정리 |
| `_handle_chat(message, thread_id)` | async 함수 (`@traceable "chat_request"`) | 이력 로드 → v2면 `graph.ainvoke`, v1이면 `run_v1` → 이력 저장 → LangSmith run_id 반환 |
| `chat(req)` | `POST /chat` | 한 번에 `{reply, events, metadata}` 응답 |
| `chat_stream(message, thread_id)` | `GET /chat/stream` | SSE. `graph.astream(stream_mode=["updates","custom"])`로 노드 이벤트와 `AnswerToken`을 `data: {...}\n\n`으로 흘리고, 마지막에 `FinalAnswer` → `[DONE]` |

### 2. `agent/deps.py`

| 이름 | 역할 |
|---|---|
| `SupervisorDeps` (dataclass) | `fast_llm`, `quality_llm`, `mcp`, `session_store`, `version` 5개 필드. 노드 함수에 `functools.partial`로 주입된다 (전역 변수/클로저 의존 제거) |

### 3. `agent/graph.py` — v2 LangGraph (가장 중요)

**모듈 수준 헬퍼**

| 이름 | 역할 |
|---|---|
| `_load_known_systems()` / `KNOWN_SYSTEMS` | `data/monitoring.json`의 키를 시스템 목록으로 읽는다. 실패 시 `{auth-service, web-01}` |
| `_extract_system_name(query)` | 쿼리에서 **가장 먼저 등장하는** 알려진 시스템 1개. 없으면 `auth-service`. MCP Prompt의 `system_name` 인자로 쓴다 |
| `AgentState` (TypedDict) | 그래프 상태. query/history/route/tasks/collected/draft/validation_*/cost_usd/events 등 |
| `_cost(state, usage)` | 누적 비용에 이번 호출 비용 더하기 |
| `_INCIDENT_TYPE_RULES` | 알림 키워드 → runbook 종류 매핑 (`latency`→high-latency, `cpu`→cpu-spike …). **순서가 우선순위** |
| `_classify_incident_type(collected)` | 모니터링 status·alerts 문자열을 위 규칙으로 매칭. 없으면 `db-down` 폴백 |

**노드 (모두 `async def xxx_node(state, deps) -> dict`, 바뀐 필드만 반환)**

| 노드 | 하는 일 | 발생 이벤트 |
|---|---|---|
| `route_node` | `fast_llm.route`로 chat / incident 분류 | `RouteDecided` |
| `chat_answer_node` | `fast_llm.chat`(이력 포함)으로 바로 답변. `get_stream_writer()`로 토큰 스트리밍 | `AnswerToken`, `Finalize(chat-direct)` |
| `plan_node` | `mcp.find_prompt` → `get_prompt("incident_analysis_prompt")`로 표준 절차 받아 `fast_llm.plan`에 넘겨 task 목록 생성 | `PlanCreated` |
| `gate_node` | `needs_analysis=False`면 analysis task를 **코드로** 제거 (모델 자기모순 방어) | `GateApplied` |
| `research_node` | pending research task를 `asyncio.gather`로 **병렬** 실행. monitoring은 `with_retry(call_tool)`, runbook은 `find_resource_template` 후 `read_resource` | `TaskCompleted` / `ResearchSkipped` |
| `replan_check_node` | runbook이 아직 없고 1라운드 전이면 `_classify_incident_type`으로 gap task(runbook) 추가 | `ReplanCheck` |
| `analysis_node` | 남은 analysis task가 있을 때만 `fast_llm.analyze`로 시스템 간 패턴 비교 | `AnalysisCompleted` / `AnalysisSkipped` |
| `write_node` | `quality_llm.write`로 초안 작성. attempt 번호를 토큰에 실어 보냄 | `AnswerToken`, `DraftWritten` |
| `validate_node` | 30자 이상 + `"1)"` 포함이면 합격. 불합격이면 feedback 생성, 3회째는 강제 통과 | `Validation` |
| `finalize_node` | `draft` → `final` 확정 | `Finalize(incident-v2)` |

**분기 함수 & 조립**

| 이름 | 역할 |
|---|---|
| `_after_route` | route=="chat"이면 `chat_answer`, 아니면 `plan` |
| `_after_replan_check` | 마지막 이벤트 `is_sufficient`면 `analysis`, 아니면 `research`로 되돌아감 |
| `_after_validate` | feedback 없으면 `finalize`, 있으면 `write`로 재작성 |
| `build_graph(deps)` | `StateGraph(AgentState)`에 노드 10개 등록 → 엣지 연결 → `compile()` |

### 4. `agent/supervisor_v1.py`

| 이름 | 역할 |
|---|---|
| `run_v1(deps, query, thread_id, history)` | 라우팅·게이트·재계획·검증이 **없는** 선형 버전. 일단 chat으로 답하고, 쿼리에 "장애/진단"이 있으면 auth-service 모니터링만 조회. v2와 같은 모양의 dict를 반환해 서버 코드가 그대로 동작 |

### 5. `agent/mcp_client.py`

| 이름 | 역할 |
|---|---|
| `DEFAULT_SERVER_SCRIPTS` | `{"ops": mcp_server.py, "docs": mcp_server_docs.py}` |
| `_attr(obj, *names)` | mcp SDK 1.x(camelCase)/2.x(snake_case) 필드명 차이를 흡수 |
| `MCPClient` 클래스 | 서버별 `ClientSession`을 들고 있고, `asyncio.Lock`으로 호출을 직렬화 |
| ├ `start()` / `stop()` | 서버 스크립트마다 `stdio_client` subprocess 기동·initialize / `AsyncExitStack`으로 일괄 종료 |
| ├ `call_tool(name, args, server="ops")` | Tool 호출 후 JSON 파싱. **최초 `get_monitoring_status` 1회는 일부러 TimeoutError** (retry 시연) |
| ├ `list_resource_templates` / `find_resource_template(name)` | 서버들을 순회하며 이름이 맞는 resource template을 찾아 `(server, uri_template)` 반환 |
| ├ `read_resource(uri, server)` | resource 본문 텍스트 반환 |
| ├ `list_prompts` / `find_prompt(name)` | 서버들을 순회하며 prompt 보유 서버 이름 반환 |
| └ `get_prompt(name, args, server)` | 렌더된 prompt 텍스트 반환 |

### 6. `agent/retry.py`

| 이름 | 역할 |
|---|---|
| `with_retry(fn, *args, retries=3, base_delay=0.3)` | `asyncio.TimeoutError`만 재시도 (0.3s → 0.9s, ×3 증가). 다른 예외는 즉시 전파. `(결과, 재시도 횟수)` 반환 |

### 7. `agent/session_store.py`

| 이름 | 역할 |
|---|---|
| `DB_PATH` | 프로젝트 루트의 `session.db` |
| `SqliteSessionStore` | `messages(thread_id, role, content, created)` 테이블 |
| ├ `load(thread_id)` | 해당 스레드 이력을 `[{role, content}]`로 |
| ├ `append(thread_id, role, content)` | 한 줄 추가 후 즉시 commit |
| └ `close()` | 연결 종료 |

### 8. LLM 백엔드 3종 — 공통 인터페이스

세 파일 모두 **fast / quality 두 클래스**를 만들고 메서드 시그니처를 똑같이 맞춘다. 그래서 `graph.py`는 어떤 백엔드인지 모른다 (덕 타이핑).

| 메서드 | 소속 | 반환 | 용도 |
|---|---|---|---|
| `route(query)` | Fast | `({route, needs_analysis}, usage)` | 라우팅 |
| `plan(query, procedure_prompt)` | Fast | `({needs_analysis, tasks}, usage)` | task 분해 |
| `analyze(collected)` | Fast | `(summary, usage)` | 패턴 비교 |
| `async chat(query, history, on_token)` | Fast | `(reply, usage)` | 일반 대화 |
| `async write(query, collected, attempt, feedback, on_token)` | Quality | `(draft, usage)` | 최종 보고 작성 |

`usage`는 `{model, tokens, usd}`이고, 실모델은 `prompt`(실제 보낸 프롬프트)도 넣어 프론트에 보여준다.

**`agent/fake_llm.py`** (기본값, 결정론)

| 이름 | 역할 |
|---|---|
| `FakeLLM` | 공통 부모. `_usage()`가 글자 수/4로 토큰을 추정해 비용 계산 |
| `FastLLM.route` | 정규식(`장애|진단|다운|...`)으로 분류 |
| `FastLLM.plan` | 쿼리에서 `xxx-service` 추출 + `web-01` 추가. **일부러 analysis task를 끼워 넣어** gate 시연 |
| `FastLLM.analyze` | degraded 시스템 수로 정해진 문장 반환 |
| `FastLLM.chat` | "제 이름은 X입니다"를 이력에서 찾아 기억하는 척 (세션 시연) |
| `QualityLLM.write` | 1차는 **일부러 "재시작하면 됩니다."** (validate 반려 시연), 2차에 구조화된 답 |

**`agent/ollama_llm.py`** (로컬 실모델, 기본 qwen3:0.6b / qwen3:8b)

| 이름 | 역할 |
|---|---|
| `KNOWN_SYSTEMS`, `_guess_target`, `_guess_targets` | 모델이 target을 틀리게 내거나 빠뜨렸을 때 쿼리에서 시스템명을 다시 찾는 보정용 |
| `ROUTE_SCHEMA`, `PLAN_SCHEMA` | Ollama `format=`에 넘기는 JSON Schema (구조화 출력 강제) |
| `OllamaLLM._chat` | 비스트리밍 `/api/chat` 호출. 실제 토큰 수(`prompt_eval_count+eval_count`)로 비용 계산 |
| `OllamaLLM._chat_stream` | NDJSON 스트림을 받아 조각마다 `on_token` 호출 → SSE로 실시간 전달 |
| `OllamaFastLLM.route/plan/analyze/chat` | 시스템 프롬프트 + 스키마로 호출. JSON 파싱 실패, target 오타, 중복 task, research 0개 같은 경우를 **코드로 정규화** |
| `OllamaQualityLLM.write` | 수집 사실(모니터링·runbook·분석)과 반려 사유를 프롬프트에 넣고 스트리밍 작성 |

**`agent/openai_llm.py`** (OpenAI, 기본 gpt-4o-mini / gpt-4o, ⚠️ 과금)

- 구조는 ollama와 거의 같다. 차이점만 정리:
  - 스키마 대신 `response_format={"type":"json_object"}`(JSON 모드)와 `ROUTE_INSTRUCTIONS`/`PLAN_INSTRUCTIONS` 문구를 쓴다.
  - `OPENAI_API_KEY`가 없으면 `RuntimeError`를 낸다.
  - `chat`/`write`는 **스트리밍하지 않는다**. 완성된 응답을 `on_token`으로 한 번에 넘긴다.

### 9. `mcp_server.py` — MCP 서버 "ops"

| 이름 | 종류 | 역할 |
|---|---|---|
| `mcp = FastMCP(...)` | 서버 객체 | — |
| `SystemStatus` | Pydantic 모델 | Tool 반환 스키마 (system_name, status, cpu/memory %, last_checked, alerts) |
| `get_monitoring_status(system_name)` | `@mcp.tool` | `monitoring.json` 기준값에 **랜덤 jitter**를 더해 반환. 없는 시스템이면 `status="unknown"` |
| `get_incident_runbook(incident_type)` | `@mcp.resource("runbook://incident-response/{incident_type}")` | `data/runbooks/{type}.md` 내용 반환 |
| `incident_analysis_prompt(system_name, symptom)` | `@mcp.prompt` | "1) 모니터링 조회 2) runbook 확인 3) 종합" 3단계 절차 텍스트 |

### 10. `mcp_server_docs.py` — MCP 서버 "docs" (decoy)

| 이름 | 역할 |
|---|---|
| `DOC_SECTIONS` | billing/auth 더미 API 문서 |
| `get_api_doc(section)` | `@mcp.resource("docs://api-reference/{section}")`. 에이전트는 **절대 안 씀**. 서버 탐색 로직(`find_*`)이 제대로 동작하는지 보여 주는 용도 |

### 11. `web_demo_server.py` — 프론트 프록시 (:8600)

| 이름 | 역할 |
|---|---|
| `index()` `GET /` | `web_chat.html` 파일 반환 |
| `proxy_health()` `GET /health` | 8100 `/health` 중계 |
| `proxy_chat()` `POST /chat` | 8100 `/chat` 중계 |
| `proxy_stream()` `GET /chat/stream` | 8100 SSE를 바이트 단위로 그대로 relay |

### 12. `web_chat.html` — Vue 3 (CDN, 빌드 없음)

| 이름 | 역할 |
|---|---|
| `STEP_LABELS` | 이벤트 타입 → 한국어 진행 문구 변환 함수 맵. `null`을 반환하면 그 이벤트는 표시하지 않음 |
| `createApp({ setup() })` | 상태: `log`(말풍선 목록), `input`, `sending`, `backendLabel`, 랜덤 `thread` id |
| `fetch('/health')` | 헤더에 백엔드·모델명 표시 |
| `scrollToBottom()` | `nextTick` 후 채팅창 맨 아래로 |
| `onSubmit()` | `EventSource('/chat/stream')` 열고 `onmessage`에서 분기: `AnswerToken` → 말풍선에 이어붙임 (attempt가 바뀌면 새 말풍선) / `FinalAnswer` → 최종 텍스트로 덮어쓰기 + 프롬프트 표시 / 그 외 → `STEP_LABELS`로 진행 단계 추가 / `[DONE]` → 종료 |

### 13. `bench/run_baseline.py` (커밋되지 않은 폴더)

| 이름 | 역할 |
|---|---|
| `extract(body)` | `/chat` 응답 events에서 incident_type·runbook·모니터링 대상·MCP 호출 목록 추출 |
| `post(client, message, thread_id)` | `/chat` 호출 후 (status, 지연시간, body, error) 반환 |
| `p95(values)` | 95퍼센타일 계산 |
| `main()` | `queries.json`을 `--repeat`번 돌려 `results/`에 jsonl/csv 기록 |

---

### 코드 읽으며 눈여겨볼 점

1. **"모델을 믿지 말고 코드로 검증한다"가 반복된다.** gate(analysis 제거), replan(incident_type을 규칙으로 판별), validate(길이·번호 검사), LLM 백엔드의 plan 정규화가 모두 같은 원칙이다.
2. **의도적으로 심은 실패가 있다.** 첫 MCP Tool 호출 Timeout, fake 1차 초안 저품질, fake plan의 analysis 끼워 넣기. 버그가 아니라 시연용이다.
3. **중복 코드**: `_load_known_systems` / `_guess_target`이 `graph.py`·`ollama_llm.py`·`openai_llm.py`에 각각 복사돼 있다. 리팩터링 과제로 삼기 좋다.
4. `/chat`은 `_handle_chat`(`@traceable`) 안에서 돌아서 LangSmith 루트 run이 생긴다. 반면 `/chat/stream`의 `gen()`에는 `@traceable`이 없다.
5. `ollama_llm.py` 7번째 줄 docstring에 `fc`라는 오타 잔해가 있다 (동작에는 영향 없음).

---

## 주요 기능·개선사항 분석 (lessonstandard_k.md 대조)

> 2026-10-20 기준. 코드를 먼저 읽고(1단계) 기준 문서와 대조한 뒤(2단계) 우선순위를 매겼다(3단계). 실측 근거는 `bench/results/before.md`다.

### 1단계 — 현재 프로젝트 파악 (기준 문서를 보기 전)

#### 1-a. 기능 목록
| 기능 | 근거 |
|---|---|
| `POST /chat` 동기 응답 (reply, events, metadata) | `server.py:141` |
| `GET /chat/stream` SSE: 노드 이벤트, AnswerToken, FinalAnswer, [DONE] | `server.py:148-192` |
| `GET /health`, `GET /version` | `server.py:93,103` |
| 라우팅 chat/incident | `agent/graph.py:76`, `_after_route:297` |
| 계획 → 게이트 → 병렬 조사 → 재계획 → 분석 → 작성 → 검증 | `agent/graph.py:101-294`, `build_graph:310` |
| MCP Tool / Resource / Prompt, 서버 탐색(find_*) | `mcp_server.py`, `agent/mcp_client.py:85-116` |
| LLM 백엔드 교체 (fake/ollama/openai) | `server.py:40` `_build_llms` |
| v1/v2 롤백 토글 | `agent/supervisor_v1.py`, `server.py:78,129` |
| 세션 이력 유지 (SQLite) | `agent/session_store.py` |
| Timeout 재시도 | `agent/retry.py` |
| Vue 채팅 화면: 진행 단계, 토큰 스트림, 재작성 시 말풍선 분리, 프롬프트 표시 | `web_chat.html:114-206` |
| 프런트 프록시 (CORS 회피) | `web_demo_server.py` |
| 기준선 측정 스크립트 | `bench/run_baseline.py` (커밋 안 됨) |

#### 1-b. 구조 요약
- **레이어**
  - Vue(CDN) → 프록시(:8600) → FastAPI(:8100) → LangGraph 노드 → LLM(httpx) / MCP(stdio subprocess 2개)
- **상태 저장**
  - 요청 단위: `AgentState`(메모리)
  - 대화 이력: `session.db`(SQLite)
  - LangGraph 체크포인터는 없다.
- **외부 연동**
  - Ollama `/api/chat`
  - OpenAI Chat Completions
  - LangSmith(`@traceable`)
- **에러 처리**
  - MCP Tool Timeout만 `with_retry`로 재시도한다.
  - 그 밖의 예외는 노드와 엔드포인트 어디에서도 잡지 않는다.
  - LLM 출력 파싱 실패는 코드에서 fallback 처리한다.
- **테스트**
  - 없다. `tests/` 폴더가 없다.
  - 수동 회귀 질문 목록(`doc/regression_test_queries.md`)과 bench만 있다.

#### 1-c. 코드에서 보이는 문제
| # | 위치 | 무엇이 왜 문제인가 |
|---|---|---|
| P1 | `agent/ollama_llm.py:104`, `agent/openai_llm.py:98`, 호출부 `agent/graph.py:78,113,243`, `openai_llm.py:201,234` | 동기 `httpx.post`를 async 노드 안에서 호출해 이벤트 루프 전체를 막는다. 응답이 30~150초 걸리는 동안 다른 요청과 `/health`까지 멈춘다 |
| P2 | `agent/ollama_llm.py:205` (openai `:168` 동일) | 빠진 시스템을 `_guess_targets` 보충하는 로직이 research task가 **0개일 때만** 돈다. 실측에서 여러 시스템을 언급한 q04·q05·q06이 1개만 조사됐다 (before.md 3-1) |
| P3 | `agent/graph.py:205-213` | 분류는 모니터링 alerts만 보고, 매칭이 없으면 `db-down`으로 폴백한다. 질문 문장은 보지 않는다. q05가 오분류됐다 (before.md 3-2) |
| P4 | `agent/graph.py:127` | gate는 `needs_analysis=False`일 때만 analysis task를 지운다. 소형 모델이 true를 남발해서 시스템을 1개만 조사해도 분석이 돈다. 7/8건에서 실행됐다 (before.md 3-3) |
| P5 | `agent/graph.py:279` | 검증 기준이 "30자 이상 + `1)` 포함"뿐이다. 조사가 빠진 답변도 23/23건 1회 만에 합격했다 (before.md 3-6) |
| P6 | `agent/graph.py:172` | `asyncio.gather`에 `return_exceptions`도 없고 task별 try/except도 없다. task 하나가 실패하면 요청 전체가 실패한다 |
| P7 | `server.py:157-190`, `web_chat.html:203` | 스트림 도중 예외가 나면 에러 이벤트 없이 연결만 끊긴다. 프런트는 `onerror`에서 조용히 닫아서 사용자에게 아무 표시가 없다 |
| P8 | `server.py:188-189` | `/chat/stream`은 스트림이 **끝까지 간 뒤에만** 이력을 저장한다. 중간에 끊기면 그 턴이 사라진다 |
| P9 | `server.py:192` | SSE 응답에 `Cache-Control: no-cache`, `X-Accel-Buffering: no` 헤더가 없다 |
| P10 | `server.py:149` | `/chat/stream`의 `message`는 검증하지 않는다(빈 문자열, 길이 제한 없음). `/chat`만 Pydantic을 쓴다 |
| P11 | `server.py:157` | `/chat/stream`에 `@traceable` 루트가 없어서 노드 trace가 요청 단위로 묶이지 않는다. `/chat`은 `_handle_chat:125`로 묶인다 |
| P12 | `agent/graph.py:26-47`, `ollama_llm.py:23-55`, `openai_llm.py:32-62` | `KNOWN_SYSTEMS`·`_guess_target(s)`가 3곳에 복사돼 있다. 한 곳만 고치면 동작이 서로 달라진다 |
| P13 | `agent/ollama_llm.py:104,127` | LLM timeout이 300초다. 실측에서 1건이 300초 타임아웃으로 실패했고 원인은 미확인이다 (before.md 3-4) |
| P14 | `agent/supervisor_v1.py:21` | v1은 대상 시스템을 `auth-service`로 하드코딩했다. 롤백하면 기능이 크게 줄어든다 (의도된 legacy) |
| P15 | `agent/session_store.py:22-34` | 동기 sqlite3를 async 핸들러에서 쓴다. 지금 부하에서는 영향이 작다 |

---

### 2단계 — 기준 문서(`doc/lessonstandard_k.md`)와 대조

| 단원 | 판정 | 근거 |
|---|---|---|
| 1 ADR | **미충족** | `adr/` 폴더가 없다. 결정 근거(subprocess MCP, SQLite 세션, v1/v2 토글, 백엔드 교체)가 docstring에만 흩어져 있다 |
| 2 FastAPI 통합 | 부분 충족 | lifespan 싱글턴 ✓ (`server.py:62-90`), Pydantic ✓ (`/chat`). 스트림 입력 검증 ✗ (P10) |
| 3 MCP Server | 이미 충족 | Tool/Resource/Prompt 분리, stdio subprocess, docstring 명시 (`mcp_server.py`) |
| 4 SSE-Backend | 부분 충족 | `stream_mode=["updates","custom"]` ✓. 버퍼링 헤더 ✗ (P9). 에러/Done 이벤트 중 에러 이벤트 ✗ (P7) |
| 5 SSE-Frontend | 부분 충족 | EventSource는 브라우저가 이벤트 단위로 나눠 주므로 버퍼 split 문제가 해당 없다. 새 요청 시 전송 버튼 비활성화 ✓. 에러 표시 ✗ (P7) |
| 6 Multi-agent | 이미 충족 | Supervisor 그래프, 노드는 바뀐 필드만 반환 (`graph.py`) |
| 7 Query Routing | 부분 충족 | fast_llm 라우팅 ✓, 권위 게이트 ✓. 게이트가 needs_analysis를 모델 판단에만 맡긴다 (P4). RouteDecided 이벤트는 만들지만 `web_chat.html` STEP_LABELS에는 없다 |
| 8 Dynamic Planning | 이미 충족 | replan_check 상한 1, append로만 확장, pending만 실행 (`graph.py:141,221`). 단, 계획 단계의 대상 누락은 replan이 보완하지 못한다 (P2) |
| 9 Validator | **미충족(형식 검사만)** | LLM-as-a-Judge 없음, 시간 한도 없음. 반복 상한(3)만 있다 (P5) |
| 10 Error Handling | 부분 충족 | Timeout만 재시도 ✓, 마지막 시도 뒤 sleep 없음 ✓ (`retry.py:19`). Graceful Degradation ✗ (P6, P7) |
| 11 Cost Optimization | 이미 충족 | fast/quality 모델 분리, 가상 비용 누적 (`server.py:40-59`) |
| 12 동시 실행 | 부분 충족 | gather Fan-out ✓. 블로킹 호출 ✗ (P1), 코루틴 격리 ✗ (P6). Semaphore는 task 2~3개라 불필요 |
| 13 Stateless Session | 부분 충족 | 이력은 프로세스 밖 SQLite ✓. 체크포인터·팩토리·Postgres는 없다 (아래 C 참고) |
| 14 Modularization | 부분 충족 | 역할별 모듈 + `SupervisorDeps` partial 주입 ✓. pytest ✗, 헬퍼 중복 (P12) |
| 15 Observability & Eval | 부분 충족 | `@traceable` 계층 trace ✓, bench 기준선 ✓. `/chat/stream` 루트 run ✗ (P11). Dataset evaluate/Feedback 코드는 **저장소에서 확인 못 함** (README:88과 manual 캡처에만 언급) |

---

### 3단계 — 결과

#### A. 주요기능 (우선순위 순)
| 순위 | 기능 | 상태 | 왜 이 순위인가 | 근거 | 작업량 |
|---|---|---|---|---|---|
| 1 | 장애 진단 파이프라인 (질문 → 모니터링 + runbook 근거 → 번호 절차 답변) | 부분 구현 | 기준1: 핵심 흐름인데 여러 시스템 질문에서 조사 누락·오분류가 난다 | `graph.py:310`, P2·P3, before.md 3-1/3-2 / 6·8단원 | M |
| 2 | 실시간 스트리밍 채팅 화면 | 부분 구현 | 기준1: 정상 경로는 동작한다. 실패하면 화면이 조용히 멈춘다 | `server.py:148`, `web_chat.html:160-203`, P7 / 4·5단원 | S |
| 3 | 동시 사용자 처리 (한 요청이 다른 요청을 막지 않음) | 미구현 | 기준1: ollama/openai 모드에서 요청 1건이 서버 전체를 멈춘다. 기준2: 이게 돼야 12단원 병렬 효과가 의미 있다 | P1 / 12단원 | S |
| 4 | 답변 품질 검증 (내용 근거 확인) | 부분 구현 (형식만) | 기준1: 틀린 진단이 그대로 나간다 | `graph.py:275`, P5 / 9단원 | M |
| 5 | 부분 실패 시에도 응답 (Graceful Degradation) | 미구현 | 기준1: MCP/LLM 오류 1건이 요청 전체 실패로 이어진다 | P6 / 10·12단원 | S |
| 6 | 세션 대화 기억 | 구현됨 | 이미 동작한다(before.md q10). 스트림 중단 시 유실(P8)만 남았다 | `session_store.py`, `server.py:188` / 13단원 | S |
| 7 | 질의 라우팅 chat/incident | 구현됨 | 실측 chat 1.3초 vs incident 32초 이상으로 효과가 확인됐다 | `graph.py:76` / 7단원 | — |
| 8 | MCP Tool/Resource/Prompt + 서버 탐색 | 구현됨 | 다른 모든 기능의 기반이고 이미 충족한다 | `mcp_server.py`, `mcp_client.py` / 3단원 | — |
| 9 | LLM 백엔드 교체 · v1 롤백 | 구현됨 | 운영 안전장치로 이미 동작한다 | `server.py:40,78` / 11·2단원 | — |
| 10 | 품질 평가 (Dataset evaluate + Feedback) | 확인 못 함 | 기준2: 위 1·4번 개선 효과를 재려면 필요하다. 지금은 bench가 대신한다 | README:88에만 언급, 코드 없음 / 15단원 | M |

#### B. 개선사항 추천 (우선순위 순)
| 순위 | 개선사항 | 현재 문제 (파일:줄) | 어떻게 바꾸나 | 근거 단원 | 작업량 |
|---|---|---|---|---|---|
| 1 | LLM 호출을 비동기로 | `ollama_llm.py:104`, `openai_llm.py:98` 동기 `httpx.post` | `_chat`을 `httpx.AsyncClient`로 바꾸고 route/plan/analyze를 async로, `graph.py`에서 await | 12 | S |
| 2 | 계획 대상 시스템 보충 | `ollama_llm.py:205`, `openai_llm.py:168` (0개일 때만 보충) | 모델 결과에 쿼리에서 찾은 KNOWN_SYSTEMS 중 빠진 것을 항상 합친다 | 7(코드가 결정권)·8 | S |
| 3 | 공통 헬퍼 한 곳으로 | `graph.py:26`, `ollama_llm.py:23`, `openai_llm.py:32` 중복 | `agent/systems.py`로 모아 import한다. 2번 수정이 한 곳에서 끝나도록 **2번보다 먼저** 한다 | 14 | S |
| 4 | 조사 task 격리와 부분 결과 | `graph.py:159-172` | `run_one` 안에서 try/except로 `{"source":"error"}`를 기록하고 write 단계는 남은 사실로 작성 | 10·12 | S |
| 5 | 스트림 에러 이벤트와 화면 표시 | `server.py:157-190`, `web_chat.html:203` | gen()을 try/except로 감싸 `{"type":"Error"}` 이벤트를 보낸 뒤 [DONE], 프런트는 말풍선으로 표시 | 4·5·10 | S |
| 6 | 분류에 질문 문장도 반영 + 폴백 개선 | `graph.py:205-213` | alerts가 매칭되지 않으면 query 키워드로 한 번 더 매칭한다. 시스템별로 분류해 runbook을 여러 개 허용할지 검토 | 8 | M |
| 7 | 검증을 내용 기준으로 | `graph.py:279` | 수집된 시스템명·수치가 답변에 들어갔는지 코드로 검사하고, 필요하면 fast_llm judge 추가. 시간 한도도 추가 | 9 | M |
| 8 | 게이트 강화 | `graph.py:127` | 조사 대상이 2개 미만이면 needs_analysis와 관계없이 analysis task를 제거 | 7 | S |
| 9 | 테스트 도입 | 테스트 없음 | fake 백엔드와 mock deps로 노드 단위 pytest 작성(gate·replan·validate·분류 규칙). bench는 통합 테스트로 유지 | 14 | M |
| 10 | 스트림 경로 정리 | `server.py:149,157,188,192` | `message` 길이 검증, SSE 헤더 2개 추가, `@traceable` 루트 추가, 이력 저장을 `finally`로 | 2·4·13·15 | S |

> 1→3→2→4→5 순서로 하면 각 단계가 앞 단계를 전제로 한다. 6~8은 9(테스트)가 있으면 회귀를 잡기 쉽다. bench `--tag after`로 before.md와 비교한다.

#### C. 제외한 것
- **13단원 AsyncPostgresSaver·체크포인터 팩토리**: 단일 프로세스 실습이라 SQLite 이력으로 충분하다. 수평 확장 계획도 없다.
- **11단원 Spot·Bin-packing**: GPU 인프라 배포 범위가 없다.
- **12단원 Semaphore**: 동시 task가 2~3개라 rate limit 위험이 없다.
- **5단원 fetch 직접 파싱·Zod·공유 상수**: EventSource(GET)라 buffer split이 필요 없다. 폼 검증 필드도 메시지 1개뿐이다.
- **4단원 `messages` 모드 / ToolCallStart·End**: ReAct sub-agent가 없고 노드가 MCP를 직접 호출한다. `custom` 토큰 스트림으로 대체돼 있다.
- **2단원 `--workers` 운영 분리**: 운영 배포가 없다. 게다가 MCP subprocess와 SQLite가 워커마다 따로 생겨서 지금 구조에는 다중 워커가 맞지 않는다.
- **3단원 Resource 캐시 hash, subscribe**: 클라이언트 쪽 캐시가 없다.
- **15단원 OpenTelemetry·구조화 로그**: 단일 서비스라 LangSmith trace로 충분하다.
- **1단원 ADR**: 미충족이지만 사용자 흐름에는 영향이 없다. 과제 제출 요건이라면 B표 다음 순위로 넣는다(작업량 S, 결정 4건 정도).
- **P13 타임아웃 300초, P14 v1 하드코딩, P15 동기 sqlite3**: 원인이 미확인이거나, 의도된 legacy이거나, 영향이 작아서 B표에 넣지 않았다.




[주요기능]
* 장애 진단 파이프라인: FastAPI와 LangGraph 기반 Supervisor 패턴 그래프를 구성하고, 요청 분류→작업 계획→MCP 조사→답변 작성→검증 순서로 장애 진단 수행
* 실시간 스트리밍 채팅: Vue 3와 SSE를 활용해 작업 진행 상황과 답변을 전달하는 채팅 화면 구현. LLM 백엔드에 따라 답변은 실시간 분할 또는 일괄 전송
* MCP 연동: MCP Tool·Resource·Prompt를 분리 구현하고, 사전에 연결된 MCP 서버 중 필요한 Resource·Prompt를 제공하는 서버를 조회해 호출하도록 구성. 모니터링에는 실습용 모의 데이터 활용
* 대화 세션 관리: SQLite 기반으로 대화 기록을 저장하고, 서버 재시작 이후에도 이전 대화 맥락을 이어서 응답하도록 구현
* LLM 백엔드 관리: 환경변수로 fake·Ollama·OpenAI 백엔드를 선택할 수 있도록 구성하고, SUPERVISOR_VERSION 변경 및 서버 재시작을 통해 기존 v1 파이프라인으로 수동 롤백 가능
[개선 사항]
* 동시 요청 처리 개선: Ollama·OpenAI 백엔드의 동기 LLM 호출로 인해 응답 대기 중 다른 요청까지 차단되는 문제를 해결하기 위해 비동기 호출 방식으로 전환 
* 다중 시스템 조사 보완: 여러 시스템을 대상으로 한 질문에서 일부 조사 대상이 누락되는 현상이 확인되어, 작업 계획 단계에서 조사 대상의 누락 여부를 검증하도록 개선 
* 부분 장애 대응: 개별 조사 Task가 실패하더라도 전체 파이프라인을 중단하지 않고, 정상적으로 수집한 결과를 활용해 부분 응답을 생성하도록 개선 
* 스트리밍 오류 처리: SSE 처리 중 발생한 예외를 별도 에러 이벤트로 전달하고, Vue 3 화면에서 오류 내용을 확인할 수 있도록 개선 
* 답변 검증 강화: 현재의 길이·번호 형식 검증을 넘어, 실제 조사 결과와 최종 답변의 일치 여부를 확인하는 근거 기반 검증 로직 도입 

---

## 정상 작동을 위한 우선 수정 항목 (문제 해결 기록)

> 2026-10-20 기준. 아직 아무것도 고치지 않았으므로 모두 "조사 중"이다. ⑤의 변경 내용은 제안이고, ⑥의 변경 후 값은 수정한 뒤 `bench/run_baseline.py --tag after`로 채운다.
>
> **우선순위**
> 1. 핵심 답변이 틀리는 문제(#1, #2)
> 2. 실패하면 화면이 멈추는 문제(#3)
> 3. 서버 전체가 멈추는 문제(#4)
> 4. 원인을 모르는 타임아웃(#5)
>
> 답변 검증 강화(P5)는 #1·#2를 고친 뒤 효과를 다시 재고 나서 진행한다.

### #1. 여러 시스템을 물어도 하나만 조사한다
상태: 조사 중

① 문제 인식
- 발견한 현상: 시스템 2개를 언급한 질문(q04·q05·q06)에서 `PlanCreated.targets`가 항상 1개였다. 9회 모두 그랬다.
- 사용자/서비스에 미치는 영향: 조사하지 않은 시스템은 답변에서 빠지거나 "확인 불가"로 나온다. 실제 q05 답변에 "auth-service 커넥션 풀 정보가 누락되어 확인 불가"라고 적혔다. 장애 진단이라는 핵심 기능이 틀린 답을 낸다.

② 문제 정의
- 기대 동작: 질문에 나온 알려진 시스템(`KNOWN_SYSTEMS`)이 전부 research task가 된다.
- 실제 동작: 첫 번째 시스템 하나만 조사한다. q04는 gateway만, q05는 web-01만, q06은 payments만 조사했다.
- 발생 조건 및 재현 방법: `LLM_BACKEND=ollama`(fast=qwen3:0.6b)로 서버를 띄운다. "web-01 CPU가 높고 auth-service 커넥션 풀이 부족해요"를 `/chat`에 보낸다. 응답 events의 `PlanCreated.targets`를 확인한다.
- 해결 완료 기준: q04·q05·q06을 3회씩 돌려서 9/9건 모두 targets에 언급한 시스템이 전부 들어 있다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드
  - `bench/results/baseline_summary.csv`의 `monitored_systems` 열
  - `agent/ollama_llm.py:189-212` `plan()`의 정규화 루프 (`openai_llm.py:152-175`도 같은 코드)
- 확인한 사실
  - 빠진 시스템을 쿼리에서 다시 채우는 `_guess_targets()`는 `if not seen:` 조건일 때만, 즉 research task가 **0개일 때만** 호출된다(`ollama_llm.py:205`).
  - target이 `KNOWN_SYSTEMS`에 없으면 `_guess_target(query)`로 바꾼다(`:193`). 이 함수는 쿼리에서 **가장 먼저 나온 시스템 하나**만 돌려준다(`:44-45`). 그 뒤 `seen`으로 중복을 지운다(`:194-196`).
  - fake 백엔드는 정규식으로 시스템을 모두 뽑기 때문에 이 문제가 없다(`fake_llm.py:40`).
- 아직 확인하지 못한 것: 모델이 처음부터 task를 1개만 냈는지, 2개를 냈는데 target 오타 때문에 둘 다 같은 시스템으로 바뀌어 중복 제거됐는지. LangSmith의 `ollama_fast.plan` run 원본 출력을 봐야 안다.

④ 가설 수립 — 추정
- 가설 A: 소형 모델(qwen3:0.6b)이 research task를 1개만 낸다.
- 가설 B: 모델은 2개를 냈지만 target 표기가 달라서(예: `auth service`) 둘 다 `_guess_target`의 첫 시스템으로 덮였다.
- 의심 근거: 어느 쪽이든 결과는 "1개"로 같다. 코드상 두 경로 모두 보충 로직을 지나치지 않는다.
- 가설이 맞다면 관찰될 결과: A라면 LangSmith 원본 `tasks` 길이가 1이다. B라면 길이가 2 이상이고 target이 `KNOWN_SYSTEMS`와 다르다.

⑤ 실험·실행
- 확인할 방법: q05 run(`01a157ca-f8a7-...`)의 `ollama_fast.plan` 출력을 LangSmith에서 연다.
- 변경한 내용 (미실행, 제안)
  - 모델 결과와 관계없이 쿼리에서 찾은 `KNOWN_SYSTEMS` 중 빠진 것을 **항상** research task로 덧붙인다.
  - `_guess_target`으로 덮어써서 생긴 중복은 버린다.
  - 이 로직은 3개 파일에 복사돼 있으므로(P12) 먼저 `agent/systems.py` 한 곳으로 모은 뒤 고친다.
- 이 방법을 선택한 이유: 가설 A·B 모두를 한 번에 막는다. 7단원 원칙("실행 직전 결정권은 코드에")과도 맞는다. 프롬프트만 고치면 소형 모델이 또 어길 수 있다.
- 필요 시 되돌리는 방법: `git revert <커밋>`. 측정 기준선은 `git checkout baseline` 태그로 재현한다.

⑥ 결과 검증
- 변경 전: q04·q05·q06 targets가 9/9건 1개
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: 조사 대상이 늘어나면 research 시간과 write 입력이 늘어난다. 분류 결과도 바뀔 수 있다(#2 참고).
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: fake 백엔드 + mock MCP로 "시스템 2개 쿼리 → research task 2개"를 확인하는 pytest를 추가한다. bench 질의셋의 `expected` 필드에 조사 대상 목록도 넣는다.
- 남은 작업: 모델이 엉뚱한 시스템을 추가로 넣는 경우(질문에 없는 시스템)도 걸러낼지 결정한다.

### #2. 장애 유형이 db-down으로 잘못 분류된다
상태: 조사 중

① 문제 인식
- 발견한 현상: q05(web-01 CPU + auth 커넥션 풀)가 3/3회 `db-down` runbook으로 분류됐다.
- 사용자/서비스에 미치는 영향: 질문과 관계없는 DB 장애 절차가 답변에 들어간다.

② 문제 정의
- 기대 동작: 증상에 맞는 runbook을 고른다(q05라면 high-latency 계열).
- 실제 동작: 매칭되는 규칙이 없으면 기본값 `db-down`을 쓴다.
- 발생 조건 및 재현 방법: 조사한 시스템이 모두 healthy이고 alerts가 비어 있을 때 발생한다. 예: q05에서 web-01만 조사된 경우.
- 해결 완료 기준: q01~q08의 runbook이 사람이 정한 기대값(`bench/queries.json`의 `expected_incident_type`)과 8/8 일치한다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `agent/graph.py:192-213` `_INCIDENT_TYPE_RULES`, `_classify_incident_type`; `data/monitoring.json`의 web-01 항목
- 확인한 사실
  - 분류는 모니터링 결과의 status와 alerts 문자열만 본다. 질문 문장은 보지 않는다.
  - web-01은 `status: healthy`, `alerts: []`라서 어떤 키워드에도 걸리지 않는다. 그래서 `return "db-down"`(`:213`)으로 빠진다.
  - 규칙은 리스트 순서대로 먼저 맞는 것을 고른다.
- 아직 확인하지 못한 것: #1을 고쳐 여러 시스템의 alerts가 합쳐졌을 때 결과가 기대값과 맞는지.

④ 가설 수립 — 추정
- 가설: q05 오분류의 직접 원인은 #1(auth-service 미조사)이고, 기본값 `db-down`이 그 문제를 가렸다.
- 의심 근거: auth-service의 alerts에는 "latency"와 "pool"이 있어서, 조사만 됐다면 high-latency로 분류됐을 것이다.
- 가설이 맞다면 관찰될 결과: #1만 고쳐도 q05가 high-latency가 된다. 다만 q04는 payments의 "CPU 91%"가 함께 들어와 network-timeout이 아니라 cpu-spike로 바뀔 수 있다(규칙 순서상 cpu가 timeout보다 앞).

⑤ 실험·실행
- 확인할 방법: #1 수정 후 bench를 돌려 incident_type을 비교한다.
- 변경한 내용 (미실행, 제안)
  1. #1을 먼저 고친다.
  2. 모니터링 매칭에 실패하면 질문 문장으로 한 번 더 매칭한다.
  3. 그래도 없으면 `db-down` 대신 "유형 불명"을 표시한다.
  4. q04 같은 순서 문제가 실제로 생기면 시스템별로 분류하는 방식을 검토한다.
- 이 방법을 선택한 이유: 기본값이 오답을 숨기는 것이 가장 큰 문제다. 규칙을 다시 짜는 것보다 작은 변경이다.
- 필요 시 되돌리는 방법: `git revert`

⑥ 결과 검증
- 변경 전: q05가 db-down 3/3. 그 밖의 쿼리는 키워드가 그럴듯하게 맞았다.
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인. `expected_incident_type`이 아직 비어 있어서 먼저 채워야 한다.
- 관련 기능에 미친 영향: runbook이 바뀌면 답변 내용이 바뀐다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: `_classify_incident_type`에 대한 표 기반 단위 테스트(alerts 입력 → 기대 유형)를 추가한다. bench의 `expected_incident_type`을 채워서 일치율을 자동으로 계산한다.
- 남은 작업: runbook을 하나가 아니라 여러 개 허용할지 결정한다.

### #3. 처리 중 오류가 나면 화면이 아무 표시 없이 멈춘다
상태: 조사 중

① 문제 인식
- 발견한 현상: 코드상 조사 task나 LLM 호출에서 예외가 나면 SSE 연결이 그냥 끊긴다. 화면에는 빈 진행 단계만 남는다.
- 사용자/서비스에 미치는 영향: 사용자는 실패했는지 아직 처리 중인지 알 수 없다. task 하나만 실패해도 이미 모은 정상 결과까지 버려진다.

② 문제 정의
- 기대 동작
  - 일부 task가 실패하면 나머지 결과로 답하고, 실패 사실을 답변에 적는다.
  - 전체가 실패하면 화면에 오류 메시지를 띄운다.
- 실제 동작: 요청 전체가 예외로 끝나고, 프런트는 조용히 입력창만 다시 연다.
- 발생 조건 및 재현 방법: `LLM_BACKEND=ollama`로 서버를 띄운 뒤 `ollama serve`를 끈다. 브라우저(:8600)에서 장애 질문을 보낸다.
- 해결 완료 기준
  - 위 재현에서 화면에 오류 말풍선이 뜬다.
  - MCP Tool 하나를 일부러 실패시켜도 나머지 시스템으로 답변이 나온다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `agent/graph.py:159-172`, `server.py:157-190`, `web_chat.html:203`
- 확인한 사실
  - `asyncio.gather(*...)`에 `return_exceptions`도, `run_one` 안의 try/except도 없다.
  - `with_retry`는 `asyncio.TimeoutError`만 재시도한다. 그 밖의 예외는 그대로 위로 올라간다(`retry.py:18`).
  - `chat_stream`의 `gen()`에도 try/except가 없어서 에러 이벤트를 보내지 않는다.
  - 프런트 `es.onerror`는 `es.close(); sending.value = false;`만 한다.
- 아직 확인하지 못한 것
  - 실제 재현 화면. 아직 직접 돌려보지 않았다.
  - bench 33건 중 이 유형의 실패는 없었다(q01 타임아웃은 클라이언트 쪽 타임아웃이다).

④ 가설 수립 — 추정
- 가설: 예외가 노드 → 그래프 → `gen()`까지 그대로 올라가서 스트림이 비정상 종료된다. 브라우저 EventSource는 이것을 `onerror`로만 받는다.
- 의심 근거: 경로 중간 어디에도 예외를 잡는 코드가 없다.
- 가설이 맞다면 관찰될 결과: 서버 로그에 traceback이 찍히고, 브라우저 Network 탭의 stream 응답이 `[DONE]` 없이 끝난다.

⑤ 실험·실행
- 확인할 방법: ②의 재현 절차를 실행하고 서버 로그와 브라우저 Network 탭을 확인한다.
- 변경한 내용 (미실행, 제안)
  1. `run_one` 안에서 예외를 잡아 `{"source": "error", "target": ..., "message": ...}`로 기록한다.
  2. write 단계 프롬프트에 "조사 실패한 시스템"을 사실로 넘긴다.
  3. `gen()`을 try/except로 감싸 `{"type": "Error"}` 이벤트를 보낸 뒤 `[DONE]`을 보낸다.
  4. 프런트에서 Error 이벤트와 `onerror`를 오류 말풍선으로 표시한다.
- 이 방법을 선택한 이유: 10·12단원의 Graceful Degradation 원칙대로 실패를 task 하나로 가둔다. 사용자에게 실패를 알리는 가장 작은 변경이다.
- 필요 시 되돌리는 방법: `git revert`

⑥ 결과 검증
- 변경 전: (재현 후 기록)
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: replan_check는 `source == "runbook"`만 세므로 error 항목이 섞여도 동작은 같다. 다만 write 입력 형식은 바뀐다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: mock MCP의 `call_tool`이 예외를 던지게 해서 research_node가 부분 결과를 돌려주는지 확인하는 pytest를 추가한다.
- 남은 작업: 이력 저장을 `finally`로 옮길지 결정한다(P8: 스트림이 끊기면 그 턴이 저장되지 않음).

### #4. LLM을 기다리는 동안 서버 전체가 멈춘다
상태: 조사 중

① 문제 인식
- 발견한 현상: Ollama·OpenAI 백엔드의 LLM 호출 일부가 동기 `httpx.post`다. async 노드 안에서 그대로 부른다.
- 사용자/서비스에 미치는 영향: 한 사용자의 장애 질문(실측 32~150초)이 처리되는 동안 다른 사용자의 요청, `/health`, 화면 첫 로딩의 백엔드 표시까지 응답하지 않을 수 있다.

② 문제 정의
- 기대 동작: LLM 응답을 기다리는 동안에도 다른 요청이 처리된다.
- 실제 동작: 이벤트 루프가 막힌다(코드상 추정, 아직 측정 안 함).
- 발생 조건 및 재현 방법
  1. `LLM_BACKEND=ollama`로 서버를 띄우고 장애 질문을 보낸다.
  2. 처리 도중 다른 터미널에서 `time curl localhost:8100/health`를 실행한다.
- 해결 완료 기준: 장애 질문이 처리되는 중에도 `/health`가 1초 안에 응답한다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `agent/ollama_llm.py:104`, `agent/openai_llm.py:98`, 호출부 `agent/graph.py:78,113,243`, `openai_llm.py:201,234`
- 확인한 사실
  - Ollama는 `route`·`plan`·`analyze`가 동기 `_chat`을 쓴다. `chat`·`write`는 비동기 스트리밍(`_chat_stream`, `httpx.AsyncClient`)이다.
  - OpenAI는 `chat`·`write`까지 **모든 호출**이 동기 `_chat`이다. `async def` 안에서 부르기만 할 뿐이다.
  - fake 백엔드는 네트워크 호출이 없어서 해당하지 않는다.
  - bench는 요청을 순서대로 보내서 동시성을 재지 않았다.
- 아직 확인하지 못한 것: 실제 `/health` 지연 시간

④ 가설 수립 — 추정
- 가설: 동기 호출이 이벤트 루프 스레드를 점유해서 다른 코루틴이 실행되지 못한다.
- 의심 근거: 12단원 필드 주의점("await 없는 requests.post 하나가 gather 전체를 멈춘다")과 같은 패턴이다.
- 가설이 맞다면 관찰될 결과: ollama 모드에서는 plan 단계 동안, openai 모드에서는 모든 LLM 단계 동안 `/health` 응답이 그 호출이 끝날 때까지 늦어진다.

⑤ 실험·실행
- 확인할 방법: ②의 재현 절차로 변경 전 `/health` 응답 시간을 잰다.
- 변경한 내용 (미실행, 제안)
  1. `_chat`을 `httpx.AsyncClient`로 바꾼다.
  2. `route`·`plan`·`analyze`를 `async def`로 바꾼다.
  3. `graph.py` 호출부에 `await`를 붙인다.
  4. fake 백엔드도 같은 인터페이스로 맞춘다.
- 이 방법을 선택한 이유: `run_in_executor`보다 코드가 단순하다. Ollama `_chat_stream`에 이미 같은 패턴이 있다.
- 필요 시 되돌리는 방법: `git revert`

⑥ 결과 검증
- 변경 전: 미측정. ②의 방법으로 먼저 잰다.
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: 메서드 시그니처가 바뀐다. `supervisor_v1.py`와 fake 백엔드도 함께 고쳐야 한다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: 장애 질문과 `/health`를 동시에 보내는 동시성 테스트 1개를 bench에 추가한다.
- 남은 작업: 동기 sqlite3(P15)도 같은 문제인지 측정한다. 지금은 영향이 작다고 추정한다.

### #5. 장애 질문 1건이 300초 동안 응답하지 않았다
상태: 조사 중

① 문제 인식
- 발견한 현상: bench에서 q01 1회차가 `ReadTimeout`(300초)으로 실패했다. 같은 질문의 2·3회차는 47.6초, 27.2초였다.
- 사용자/서비스에 미치는 영향: 사용자는 5분 동안 기다리다 실패한다. 원인을 모르니 다시 일어날 수 있다.

② 문제 정의
- 기대 동작: 장애 질문이 일정 시간(예: 120초) 안에 답하거나, 실패를 알린다.
- 실제 동작: 300초 동안 응답하지 않았다.
- 발생 조건 및 재현 방법: 아직 재현하지 못했다. 서버를 띄운 뒤 첫 장애 질문이었을 가능성이 있다.
- 해결 완료 기준: bench 3회 반복에서 타임아웃 0건. 또는 원인을 확정하고 재현 조건을 문서화한다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드
  - `bench/results/baseline_raw.jsonl`: q01 1회차 `error: ReadTimeout`, `langsmith_run_id` 없음
  - `agent/ollama_llm.py:104,127`: LLM 호출 timeout 300초
  - bench 클라이언트 timeout도 300초
- 확인한 사실
  - bench 클라이언트가 먼저 끊었다. 서버 쪽 처리가 그 뒤에 끝났는지는 기록이 없다.
  - 클라이언트가 실패해서 run_id가 응답에 없다. LangSmith에서는 시각(2026-10-20 14:14 무렵)으로 찾아야 한다.
- 아직 확인하지 못한 것: 어느 노드에서 시간이 걸렸는지, 서버가 끝까지 처리했는지

④ 가설 수립 — 추정
- 가설 A: 첫 요청 때 Ollama가 qwen3:8b를 메모리에 올리느라(모델 로드) 오래 걸렸다.
- 가설 B: qwen3 모델의 사고(thinking) 출력이 길어져 생성이 늦어졌다.
- 의심 근거: 첫 회차만 실패했고 바로 다음 회차는 정상이었다(A를 지지). 같은 질문인데 응답 시간 편차가 컸다(q03 70~152초, B를 지지).
- 가설이 맞다면 관찰될 결과: A라면 서버를 다시 띄운 뒤 첫 장애 질문만 매번 느리다. B라면 LangSmith의 `ollama_quality.write` 출력 토큰 수가 비정상적으로 크다.

⑤ 실험·실행
- 확인할 방법
  - LangSmith에서 해당 시각의 `chat_request` run을 찾아 노드별 시간을 본다.
  - `ollama ps`로 모델이 메모리에 올라와 있는지 확인한 상태와 내려간 상태에서 각각 첫 질문 시간을 비교한다.
- 변경한 내용 (미실행, 원인 확정 후 결정)
  - 후보 1: 서버를 띄울 때 모델을 미리 로드(워밍업)한다.
  - 후보 2: LLM timeout을 줄이고 #3의 오류 이벤트로 실패를 알린다.
- 이 방법을 선택한 이유: 원인이 확정되지 않았으므로 먼저 측정한다.
- 필요 시 되돌리는 방법: 설정값 변경이므로 원래 값으로 되돌린다.

⑥ 결과 검증
- 변경 전: 30건 중 1건 타임아웃(성공률 0.97)
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: timeout을 줄이면 정상적으로 오래 걸리는 요청(최대 152초 실측)이 실패로 바뀔 수 있다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: bench가 실패한 요청에도 요청 시각과 thread_id를 남겨 LangSmith에서 찾을 수 있게 한다. 노드별 소요 시간을 metadata에 넣는 방안도 검토한다.
- 남은 작업: #4를 고친 뒤에도 재발하는지 확인한다.

---

## 다음 할 일 — 개선 항목 (문제 해결 기록 #6~#10)

> 2026-10-20 기준. #1~#5(정상 작동 문제) 다음 단계다. 모두 아직 손대지 않았으므로 "조사 중"이다.
>
> **순서**
> 1. 고친 것을 확인할 장치(#6 테스트, #7 정답 기준)
> 2. 답변 품질(#8 분석 단계, #9 검증)
> 3. 스트림 경로 정리(#10)
>
> #6·#7은 #1을 시작하기 **전에** 해 두면 #1~#5의 ⑥ 결과 검증을 숫자로 채울 수 있다.

### #6. 고친 뒤 다른 곳이 깨졌는지 확인할 자동 테스트가 없다
상태: 조사 중

① 문제 인식
- 발견한 현상: `tests/` 폴더가 없다. `.venv`에 pytest도 설치돼 있지 않다(`ModuleNotFoundError: No module named 'pytest'`).
- 사용자/서비스에 미치는 영향: #1~#5를 고칠 때마다 Ollama를 띄우고 bench를 돌려야 확인할 수 있다(10개 질의 × 3회에 약 25분). 규칙 하나를 바꿨을 때 다른 규칙이 깨져도 바로 알 수 없다.

② 문제 정의
- 기대 동작: 네트워크와 LLM 없이 몇 초 안에 핵심 규칙(게이트, 재계획, 검증, 분류, 계획 정규화)을 확인할 수 있다.
- 실제 동작: 수동 질문 목록(`doc/regression_test_queries.md`)과 실모델 bench만 있다.
- 발생 조건 및 재현 방법: `./.venv/bin/python3 -m pytest`를 실행하면 모듈이 없다는 오류가 난다.
- 해결 완료 기준
  - `pytest`를 실행하면 노드 단위 테스트가 10초 안에 통과한다.
  - #1·#2·#3·#8·#9의 완료 기준이 각각 테스트 1개 이상으로 표현돼 있다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `requirements.txt`(pytest 없음), `agent/deps.py`, `agent/fake_llm.py`, `agent/graph.py`
- 확인한 사실
  - 노드는 모두 `(state, deps)`를 받아 바뀐 필드만 돌려주는 함수다. `deps`는 `SupervisorDeps`로 주입한다(`graph.py:312`). 그래서 mock deps로 바꿔 끼우기 쉽다. `deps.py` docstring에도 이 의도가 적혀 있다.
  - `gate_node`, `replan_check_node`, `validate_node`, `_classify_incident_type`은 LLM이나 MCP를 부르지 않는 순수 로직이다.
  - `OllamaFastLLM.plan()`의 정규화 부분은 `_chat` 결과만 바꿔 넣으면 네트워크 없이 시험할 수 있다.
- 아직 확인하지 못한 것: `@traceable` 데코레이터가 LangSmith 키 없이 테스트 환경에서 조용히 넘어가는지

④ 가설 수립 — 추정
- 가설: 순수 로직 노드 4개와 plan 정규화만 테스트해도 #1·#2·#8·#9 수정이 다른 부분을 깨뜨리는지 대부분 잡을 수 있다.
- 이 가설을 의심하는 근거: bench에서 나온 이상 결과(조사 누락, 오분류, 분석 과다)가 모두 이 함수들 안에서 생긴다.
- 가설이 맞다면 관찰돼야 하는 결과: 지금 코드로 "시스템 2개 쿼리 → research task 2개" 테스트를 쓰면 **실패**한다. #1의 버그를 테스트로 재현할 수 있다.

⑤ 실험·실행
- 확인할 방법: 테스트를 먼저 써서 현재 코드에서 실패하는지 확인한다(빨간불 확인).
- 변경한 내용 (미실행, 제안)
  1. `requirements.txt`에 `pytest`를 추가한다.
  2. `tests/test_graph_rules.py`를 만든다. 대상은 gate·replan·validate·분류 규칙이다. async 노드는 `asyncio.run`으로 부른다.
  3. `tests/test_plan_normalize.py`를 만든다. `OllamaFastLLM._chat`을 monkeypatch로 바꿔 모델 출력 사례를 넣는다. 사례는 task 1개, target 오타, analysis만 있는 경우다.
  4. `LANGCHAIN_TRACING_V2=false`로 실행한다.
- 이 방법을 선택한 이유: 14단원 기준(의존성 주입 + pytest + Mock)이다. 구조가 이미 주입식이라 코드를 고치지 않고 테스트만 추가할 수 있다.
- 필요 시 되돌리는 방법: `tests/` 폴더와 requirements 한 줄만 지우면 된다. 운영 코드는 바뀌지 않는다.

⑥ 결과 검증
- 변경 전: 자동 테스트 0개
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: 없음. 테스트 코드만 추가한다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: `sh/`에 `run_tests.sh`를 추가하고, guide.md의 빠른 실행 체크리스트에 한 줄 넣는다.
- 추가하지 않아도 되는 것: MCP·LLM을 실제로 띄우는 통합 테스트는 bench가 이미 맡고 있으므로 pytest에는 넣지 않는다(14단원 "유닛 테스트는 연동 문제를 못 잡는다"를 bench로 보완).
- 남은 작업: CI가 없으니 커밋 전에 직접 실행하는 규칙을 정한다.

### #7. bench의 "성공률"이 정답 여부가 아니라 응답 여부만 잰다
상태: 조사 중

① 문제 인식
- 발견한 현상: before.md의 성공률 0.97은 "HTTP 200으로 응답이 왔다"는 뜻이다. q05는 오분류(#2)인데도 3/3 성공으로 집계됐다.
- 사용자/서비스에 미치는 영향: 개선 전후를 비교할 때 "맞게 진단했는가"를 숫자로 보여 줄 수 없다. #1~#5의 ⑥ 결과 검증을 사람이 응답을 읽어서 판단해야 한다.

② 문제 정의
- 기대 동작: 쿼리마다 기대 route, 조사 대상 시스템, 장애 유형을 정해 두고 일치율을 계산한다.
- 실제 동작: 기대값 열은 CSV에 복사만 되고 비교하지 않는다. 장애 유형 기대값은 비어 있다.
- 발생 조건 및 재현 방법: `bench/results/baseline_summary.csv`의 `expected_incident_type` 열이 전부 빈칸이다.
- 해결 완료 기준: summary에 `route_match`, `systems_match`, `incident_type_match` 열이 생기고, baseline 데이터로 다시 계산했을 때 q05가 불일치로 나온다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `bench/run_baseline.py`의 `main()`(`ok` 판정), `bench/queries.json`
- 확인한 사실
  - `ok = status == 200 and err is None`이다. 그 밖에는 q10의 `expect_in_last_reply`("민수" 포함)만 추가로 본다.
  - `expected_route`와 `expected_incident_type`은 summary CSV에 그대로 옮겨 적기만 한다.
  - `queries.json`에는 기대 조사 대상 시스템 필드가 없다. `purpose` 문장에만 설명돼 있다.
  - LangSmith Dataset·`evaluate()`·Feedback 코드는 저장소에 없다(README:88에만 언급).
- 아직 확인하지 못한 것: 쿼리마다 "정답" runbook을 무엇으로 볼지에 대한 합의. 예를 들어 q04는 network-timeout과 cpu-spike 중 무엇이 맞는지.

④ 가설 수립 — 추정
- 가설: 기대값 3가지(route, systems, incident_type)만 채워도 #1·#2·#8의 개선 여부를 자동으로 판정할 수 있다.
- 이 가설을 의심하는 근거: before.md 3장에서 사람이 찾아낸 이상 결과가 모두 이 세 값의 불일치였다.
- 가설이 맞다면 관찰돼야 하는 결과: baseline raw로 다시 계산하면 q04·q05·q06은 systems 불일치, q05는 incident_type 불일치가 나온다.

⑤ 실험·실행
- 확인할 방법: 새 열을 기존 `baseline_raw.jsonl`에 적용해 다시 계산한다. 서버를 다시 돌릴 필요가 없다.
- 변경한 내용 (미실행, 제안)
  1. `queries.json`에 `expected_systems`를 추가하고 `expected_incident_type`을 채운다. 애매한 쿼리는 허용값 목록으로 둔다.
  2. `run_baseline.py`에 일치 여부 열 3개를 추가한다.
  3. raw 파일에서 summary만 다시 만드는 `--from-raw` 옵션을 추가한다.
- 이 방법을 선택한 이유: 기존 측정 데이터를 그대로 재활용할 수 있다. LangSmith Dataset으로 옮기는 것(15단원)은 기준이 정해진 뒤에 해도 늦지 않다.
- 필요 시 되돌리는 방법: `git revert`. 기존 결과 파일은 tag 이름이 달라서 덮어쓰지 않는다.

⑥ 결과 검증
- 변경 전: 성공률 0.97(응답 기준). 정답 기준 일치율은 없음.
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: 없음. 측정 도구만 바뀐다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: 새 질의를 추가할 때 기대값 3가지를 반드시 채우도록 `queries.json` 맨 위에 형식 예시를 둔다.
- 남은 작업: 답변 문장 품질(근거 인용, 지어낸 내용)은 이 방식으로 잴 수 없다. #9의 검증 기준과 같은 규칙을 bench에서도 재사용할지 정한다.

### #8. 비교 분석이 필요 없는 질문에서도 분석 단계가 돈다
상태: 조사 중

① 문제 인식
- 발견한 현상: incident 질의 8종 중 7종에서 `AnalysisCompleted`가 기록됐다. 분석이 필요한 질문은 q06 하나뿐이다.
- 사용자/서비스에 미치는 영향
  - 시스템을 1개만 조사했는데도 "비교 분석"을 돌린다. 그 결과인 "특이 패턴 없음"이 답변에 근거처럼 들어간다. 실제 q06 2·3회차 답변에 "패턴 분석 결과 특이 패턴 없음"이 있다.
  - LLM 호출이 1회 더 생긴다.

② 문제 정의
- 기대 동작: 조사한 시스템이 2개 이상이고, 질문이 비교나 공통 원인을 요구할 때만 분석한다.
- 실제 동작: 모델이 `needs_analysis=true`를 내면 조사 대상 수와 관계없이 분석한다.
- 발생 조건 및 재현 방법: ollama 백엔드에서 q02 "cache-service 메모리 사용률이 계속 올라가고 있어요"를 보낸다. events에 `AnalysisCompleted`가 생긴다.
- 해결 완료 기준: 단일 시스템 질의(q01·q02·q03·q07·q08)에서 분석 실행 0/15. #1을 고친 뒤 q06에서는 3/3 실행.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `agent/graph.py:122-134` `gate_node`, `agent/graph.py:233-251` `analysis_node`, `baseline_raw.jsonl`의 `analysis_ran`
- 확인한 사실
  - gate는 `needs_analysis`가 False일 때만 analysis task를 지운다. True이면 그대로 둔다.
  - `needs_analysis`는 plan 단계 모델 출력을 그대로 쓴다(`graph.py:118`).
  - 분석 안 함은 q07 하나뿐이었다(gate가 1개 제거).
  - analysis_node는 수집된 모니터링이 1건이어도 비교 분석을 부른다.
- 아직 확인하지 못한 것: 분석 단계가 응답 시간에 더하는 몫. 노드별 시간을 기록하지 않아서 LangSmith에서 확인해야 한다.

④ 가설 수립 — 추정
- 가설: 소형 모델(qwen3:0.6b)이 `needs_analysis`를 거의 항상 true로 낸다. 게이트가 이 값을 그대로 믿는 것이 원인이다.
- 이 가설을 의심하는 근거: 7단원 원칙("프롬프트 지시는 사전 유도일 뿐, 결정권은 코드에")을 이 값에는 적용하지 않았다.
- 가설이 맞다면 관찰돼야 하는 결과: LangSmith의 `ollama_fast.plan` 출력에서 `needs_analysis: true`가 7/8종에서 보인다.

⑤ 실험·실행
- 확인할 방법: LangSmith에서 q02 run의 plan 출력을 본다.
- 변경한 내용 (미실행, 제안)
  1. gate에 코드 조건을 추가한다. research 대상이 2개 미만이면 `needs_analysis`와 관계없이 analysis task를 지운다.
  2. analysis_node에서도 모니터링 결과가 2건 미만이면 건너뛴다(이중 방어).
- 이 방법을 선택한 이유: 1줄 수준의 변경으로 모델 오판을 막는다. 비교할 대상이 1개면 비교 분석은 정의상 의미가 없다.
- 필요 시 되돌리는 방법: `git revert`

⑥ 결과 검증
- 변경 전: 분석 실행 7/8종(21/24회)
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: q06은 #1을 고치기 전까지는 대상이 1개라 분석이 꺼진다. 그래서 **#1 다음에** 적용해야 한다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: #6 테스트에 "대상 1개 + needs_analysis=True → analysis 제거" 사례를 추가한다. #7 bench에 `expected_analysis` 기대값을 추가한다.
- 남은 작업: 질문 문장의 "공통 원인", "비교" 같은 표현을 조건에 넣을지 결정한다.

### #9. 검증 단계가 답변 내용을 보지 않아 근거 없는 답도 통과한다
상태: 조사 중

① 문제 인식
- 발견한 현상: incident 23건이 모두 검증을 1회 만에 통과했다. 조사하지 않은 시스템에 대해 추측한 답변도 통과했다.
  - q06 1회차: cache-service를 조사하지 않았는데 "cache-service도 동일한 원인이 있을 수 있음"이라고 썼다.
  - q05: "확인 불가"가 들어간 답변이 통과했다.
- 사용자/서비스에 미치는 영향: 사용자는 근거 있는 진단과 추측을 구분할 수 없다. 장애 대응 판단을 잘못할 수 있다.

② 문제 정의
- 기대 동작: 답변이 수집한 사실(조사한 시스템, 수치, runbook)에 근거하는지 확인한다. 질문에 나왔지만 조사하지 못한 시스템이 있으면 반려하거나 그 사실을 명시하게 한다.
- 실제 동작: "30자 이상 + `1)` 포함"만 보면 합격이다.
- 발생 조건 및 재현 방법: #1 버그가 있는 상태에서 q06을 보낸다. 조사하지 않은 cache-service에 대한 서술이 있어도 통과한다.
- 해결 완료 기준: 조사하지 않은 시스템을 근거 없이 서술한 답변이 반려되고, 재작성본에 "미조사"가 명시된다. 정상 답변의 첫 시도 합격률이 크게 떨어지지 않는다(예: 80% 이상 유지).

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `agent/graph.py:274-288` `validate_node`, `baseline_raw.jsonl`의 q05·q06 응답
- 확인한 사실
  - 검증 조건은 `len(draft) >= 30 and "1)" in draft`뿐이다(`graph.py:279`).
  - 반려 사유(feedback)도 길이와 번호 형식만 말한다.
  - 3회째에는 무조건 통과시킨다(`:281`). 반복 상한은 있지만 시간 상한은 없다.
- 아직 확인하지 못한 것: 수치를 지어낸 답변(수집하지 않은 CPU 값 등)이 얼마나 되는지. 23건의 답변 문장을 수집 사실과 하나씩 대조해야 한다.

④ 가설 수립 — 추정
- 가설: 코드 규칙 두 가지만으로도 근거 없는 답변 대부분을 잡을 수 있다.
  - 규칙 1: 질문에 나온 시스템 중 조사하지 않은 것을 답변이 서술하는가?
  - 규칙 2: 조사한 시스템 이름이 답변에 모두 들어 있는가?
- 이 가설을 의심하는 근거: 위에서 찾은 문제 사례가 모두 "조사 안 한 시스템" 관련이었다.
- 가설이 맞다면 관찰돼야 하는 결과: baseline 답변에 규칙을 적용하면 q05·q06 일부가 불합격으로 나오고, q01·q02·q03은 대부분 합격으로 나온다.

⑤ 실험·실행
- 확인할 방법: 규칙 함수를 먼저 만들어 `baseline_raw.jsonl`의 답변 23건에 오프라인으로 적용해 본다. 서버를 다시 돌리지 않아도 된다.
- 변경한 내용 (미실행, 제안)
  1. 위 코드 규칙 두 가지를 `validate_node`에 추가하고, 위반 내용을 feedback에 구체적으로 적는다.
  2. 시간 상한(예: 검증·재작성 합계 60초)을 추가한다.
  3. 코드 규칙으로 부족하면 그다음에 fast_llm judge(9단원 LLM-as-a-Judge)를 검토한다.
- 이 방법을 선택한 이유: LLM judge는 비용과 시간이 들고, 소형 모델로는 판정 자체가 흔들릴 수 있다. 코드 규칙은 결정적이어서 #6 테스트로 고정할 수 있다.
- 필요 시 되돌리는 방법: `git revert`

⑥ 결과 검증
- 변경 전: 첫 시도 합격 23/23, 근거 없는 서술 최소 2건(q05·q06)
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: 재작성이 늘면 응답 시간이 늘어난다. **#1을 먼저 고치지 않으면** 여러 시스템 질문이 매번 반려돼 최대 3회까지 재작성하게 된다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: 규칙 함수를 #6 테스트와 #7 bench에서 같이 쓴다(답변 품질 지표).
- 남은 작업: 수치 인용이 정확한지(수집 값과 일치하는지)도 검사할지 정한다. 모니터링 값에 jitter가 있어서 허용 오차를 정해야 한다.

### #10. 브라우저가 쓰는 `/chat/stream` 경로가 `/chat`보다 보호 장치가 적다
상태: 조사 중

① 문제 인식
- 발견한 현상: 화면(`web_chat.html`)은 `/chat/stream`만 쓴다. 그런데 이 경로에는 `/chat`에 있는 것들이 빠져 있다.
  - Pydantic 요청 모델이 없다.
  - LangSmith 요청 단위 루트 run이 없다.
  - 이력 저장 시점이 다르다.
  - SSE 버퍼링 방지 헤더도 없다.
- 사용자/서비스에 미치는 영향
  - 스트림이 중간에 끊기면 그 대화가 이력에 남지 않는다.
  - 프록시를 거치면 토큰이 한꺼번에 몰려 나올 수 있다.
  - LangSmith에서 브라우저 요청 하나를 한 트리로 보기 어렵다.

② 문제 정의
- 기대 동작: 두 경로가 같은 입력 검증, 같은 trace 구조, 같은 이력 저장 규칙을 가진다.
- 실제 동작
  - 이력은 스트림이 끝까지 간 뒤에만 저장한다.
  - 빈 메시지도 그대로 처리한다.
  - 헤더는 기본값이다.
- 발생 조건 및 재현 방법
  - 이력 유실: 장애 질문을 보낸 뒤 답변 도중 브라우저 탭을 닫는다. 같은 thread_id로 이력을 확인하면 그 턴이 없다.
  - 빈 입력: `curl 'localhost:8100/chat/stream?message='`를 보낸다.
- 해결 완료 기준
  - 중단된 턴도 사용자 메시지가 저장된다.
  - 빈 메시지나 지나치게 긴 메시지(예: 2,000자 초과)는 422로 거절된다.
  - LangSmith에서 스트림 요청 하나가 루트 run 하나로 보인다.
  - 응답 헤더에 `Cache-Control: no-cache`, `X-Accel-Buffering: no`가 있다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `server.py:35-37`(`ChatRequest`), `server.py:125-138`(`_handle_chat`), `server.py:148-192`(`chat_stream`)
- 확인한 사실
  - `chat_stream`은 `message: str`을 쿼리 파라미터로 받는다. 길이 제한이 없다. `/chat`의 `ChatRequest`도 길이 제한은 없다.
  - 이력 `append`는 `async for` 루프가 정상 종료된 뒤에만 실행된다(`:188-189`). `try/finally`가 아니다.
  - `_handle_chat`에는 `@traceable(name="chat_request")`가 있지만 `gen()`에는 없다.
  - `StreamingResponse(..., media_type="text/event-stream")`에 headers 인자가 없다(`:192`).
- 아직 확인하지 못한 것
  - LangSmith에서 스트림 요청의 노드 run들이 실제로 어떻게 보이는지(따로따로 루트로 흩어지는지)
  - 클라이언트가 끊었을 때 `gen()`이 어느 시점에 취소되는지

④ 가설 수립 — 추정
- 가설: `/chat`을 먼저 만들고 `/chat/stream`을 나중에 붙이면서, 공통 처리(검증, trace, 저장)를 함수로 빼지 않고 따로 구현했다.
- 이 가설을 의심하는 근거: 두 경로 모두 "이력 로드 → 그래프 실행 → 이력 저장"으로 순서가 같은데 코드는 중복돼 있고 세부가 다르다.
- 가설이 맞다면 관찰돼야 하는 결과: 공통 함수 하나로 묶으면 위 4가지 차이가 한 번에 사라진다.

⑤ 실험·실행
- 확인할 방법: ②의 재현 절차 두 가지와 `curl -I`로 응답 헤더를 확인하고, LangSmith에서 trace 모양을 본다.
- 변경한 내용 (미실행, 제안)
  1. `message`에 `Query(min_length=1, max_length=2000)`을 걸고, `ChatRequest`에도 같은 제한을 둔다.
  2. 사용자 메시지는 그래프 실행 **전**에 저장하고, 답변은 `finally`에서 저장한다(중단 시에는 표시를 붙인다).
  3. 스트림 실행 부분을 `@traceable` 함수로 감싼다.
  4. `StreamingResponse`에 헤더 2개를 추가한다.
- 이 방법을 선택한 이유: 각각 몇 줄짜리 변경이다(2·4·13·15단원 기준). #3(스트림 오류 이벤트)과 같은 함수를 고치므로 #3과 함께 작업하면 충돌이 적다.
- 필요 시 되돌리는 방법: `git revert`

⑥ 결과 검증
- 변경 전: (재현 후 기록)
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: 이력 저장 시점을 바꾸면 그래프에 넘기는 `history`에 이번 질문이 들어가지 않게 순서를 맞춰야 한다. 지금은 로드 후 실행하는 순서다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: FastAPI `TestClient`로 두 경로에 같은 입력을 넣고, 검증·저장 결과가 같은지 비교하는 테스트를 #6에 추가한다.
- 남은 작업: `web_demo_server.py` 프록시도 헤더를 그대로 전달하는지 확인한다.

### 기록 없이 남겨 둔 것 (필요해지면 위 양식으로 옮긴다)
- **ADR 작성(1단원)**: 사용자 흐름에는 영향이 없다. 과제 제출 요건이면 결정 4건을 `adr/`에 정리한다. 대상은 MCP subprocess, SQLite 세션, v1/v2 토글, LLM 백엔드 교체다.
- **LangSmith Dataset·evaluate·Feedback(15단원)**: #7로 기준을 먼저 정한 뒤 옮긴다.
- **화면에 라우팅 결과 표시**: `RouteDecided` 이벤트가 `web_chat.html`의 STEP_LABELS에 없어서 표시되지 않는다(7단원 "라우팅 이벤트 최우선").
- **v1 하드코딩(P14), 동기 sqlite3(P15)**: 의도된 legacy이거나 영향이 작다. #4를 고친 뒤 다시 본다.

---

## 기준 문서 대조 점검 (#1~#10이 빠뜨린 것)

> 2026-10-20 점검. **코드 변경은 아직 0건이다**(`git status`에 문서만 있음). 그래서 #1~#10은 모두 "조사 중"이고, 완료된 개선사항은 없다.

| 단원 | 이 프로젝트 상태 | 다루는 기록 |
|---|---|---|
| 1 ADR | 미충족 | "기록 없이 남겨 둔 것"(제출 요건일 때만) |
| 2 FastAPI 통합 | 입력 길이 검증 없음 | #10 |
| 3 MCP Server | 충족 | — |
| 4 SSE-Backend | 에러 이벤트·버퍼링 헤더 없음 | #3, #10 |
| 5 SSE-Frontend | 오류 표시 없음 | #3 |
| 6 Multi-agent | 충족 | — |
| 7 Query Routing | 게이트가 모델 판단을 그대로 믿음 | #8 |
| 8 Dynamic Planning | 계획 단계 대상 누락, 분류 기본값 | #1, #2 |
| 9 Validator | 형식만 검사, 시간 상한 없음 | #9 |
| 10 Error Handling | 부분 실패 격리 없음 / **재시도가 실제 장애에는 동작 안 함** | #3 / **#11 (신규)** |
| 11 Cost Optimization | 충족 | — |
| 12 동시 실행 | 블로킹 호출, 격리 없음 | #4, #3 |
| 13 Stateless Session | SQLite로 충분 | — (제외) |
| 14 Modularization | 테스트 없음, 헬퍼 중복 | #6, #1 |
| 15 Observability & Eval | 정답 기준 없음 / **어디서 느린지 알 수 없음** | #7 / **#12 (신규)** |

> **최우선 순서 갱신**: #12 → #6 → #7 → #1 → #2 → #11 → #3 → #4 → #5 → #8 → #9 → #10
> - #12는 #4·#5의 원인을 확인하는 데 필요한 **선행 조건**이라 가장 앞에 둔다.
> - #11은 #3(오류 처리)과 같은 경로를 고치므로 #3 바로 앞에 둔다.

### #11. 재시도가 시연용 가짜 Timeout에만 동작하고, 실제 MCP 호출에는 timeout이 없다
상태: 조사 중

① 문제 인식
- 발견한 현상
  - `with_retry`는 `asyncio.TimeoutError`만 재시도한다.
  - 그런데 이 예외를 실제로 내는 곳은 `MCPClient.call_tool`의 **의도적 flaky 1회**뿐이다.
  - 실제 MCP 호출과 LLM 호출에는 이 예외가 나오는 경로가 없다.
  - before.md 측정에서 retry 횟수는 전 구간 0이었다.
- 사용자/서비스에 미치는 영향
  - MCP 서버가 응답하지 않으면 요청이 끝없이 기다린다. timeout이 없기 때문이다.
  - LLM 호출이 일시적으로 실패해도(연결 끊김, OpenAI 429·5xx) 재시도 없이 요청 전체가 실패한다.
  - 매뉴얼의 "재시도 성공" 시연은 실제 장애 대응 능력을 보여 주지 않는다.

② 문제 정의
- 기대 동작(10단원)
  - Tool 계층은 정해진 시간 안에 응답이 없으면 Timeout으로 끊고, backoff 후 재시도한다.
  - 영구 오류는 즉시 실패로 넘긴다.
- 실제 동작
  - MCP 호출에는 시간 제한이 없다.
  - Resource 읽기(`read_resource`)는 재시도로 감싸지 않았다.
  - LLM 호출은 httpx timeout 300초가 지나면 `httpx.ReadTimeout`이 나는데, 이건 `asyncio.TimeoutError`가 아니라서 재시도 대상이 아니다.
- 발생 조건 및 재현 방법
  - `mcp_server.py`의 `get_monitoring_status`에 `time.sleep(600)`을 임시로 넣는다.
  - 장애 질문을 보내면 요청이 끝나지 않는 것을 확인한다.
- 해결 완료 기준
  - 위 재현에서 요청이 정해진 시간(예: Tool 10초 × 3회 + backoff) 안에 끝난다.
  - 실패한 task가 #3의 부분 결과로 처리된다.
  - 일시 오류 1회를 주입하면 retry_count=1로 복구된다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `agent/retry.py:18`, `agent/mcp_client.py:60,72-77,97-100`, `agent/graph.py:163-168`, `.venv`의 mcp 2.2.0 `ClientSession`
- 확인한 사실
  - `ClientSession(read, write)`를 만들 때 `read_timeout_seconds`를 넘기지 않는다(`mcp_client.py:60`).
  - `call_tool(name, arguments)`도 timeout 없이 부른다(`:76`). SDK 시그니처상 둘 다 기본값이 `None`(제한 없음)이다.
  - `asyncio.TimeoutError`를 일부러 던지는 곳은 `mcp_client.py:74` 한 곳뿐이다.
  - `read_resource`는 `with_retry` 없이 바로 부른다(`graph.py:168`).
  - before.md: "retry 횟수 전 구간 0", "의도적 flaky는 서버 프로세스당 첫 Tool 호출 1번뿐"
- 아직 확인하지 못한 것
  - mcp SDK에서 `read_timeout_seconds`를 넘었을 때 어떤 예외 타입이 나는지. `asyncio.TimeoutError`가 아닐 수 있어서, 그렇다면 `with_retry` 조건도 함께 바꿔야 한다.
  - MCP 서버 프로세스가 죽었을 때 어떤 예외가 나는지

④ 가설 수립 — 추정
- 가설: 재시도 로직 자체(`retry.py`)는 맞다. 문제는 그 앞단에 실제 timeout이 걸려 있지 않아서 동작할 계기가 없다는 것이다.
- 이 가설을 의심하는 근거: 실제 장애를 측정한 33건에서 retry가 한 번도 일어나지 않았다. timeout 설정은 코드 어디에도 없다.
- 가설이 맞다면 관찰돼야 하는 결과: ②의 재현에서 요청이 끝나지 않는다. timeout만 걸면 `with_retry`가 동작한다(예외 타입이 맞는다면).

⑤ 실험·실행
- 확인할 방법: ②의 재현으로 끝없이 기다리는지 확인한다. 그다음 `read_timeout_seconds`를 짧게 걸어 어떤 예외가 나는지 기록한다.
- 변경한 내용 (미실행, 제안)
  1. `call_tool`·`read_resource`에 `read_timeout_seconds`(예: 10초)를 넘긴다.
  2. SDK가 내는 timeout 예외를 `asyncio.TimeoutError`로 바꾸거나 `with_retry`의 재시도 대상에 추가한다.
  3. `read_resource`도 `with_retry`로 감싼다.
  4. LLM 호출은 httpx의 연결 오류·timeout만 1~2회 재시도하는 별도 정책을 둔다. 영구 오류(4xx)는 바로 실패시킨다.
- 이 방법을 선택한 이유
  - 10단원의 "TimeoutError만 재시도, 나머지는 즉시 전파" 원칙을 그대로 지킨다.
  - 이미 있는 `with_retry`를 재사용하므로 바뀌는 범위가 작다.
- 필요 시 되돌리는 방법: `git revert`. timeout 값은 상수 하나로 둬서 조정할 수 있게 한다.

⑥ 결과 검증
- 변경 전: 실제 장애에서 retry 0회. MCP가 응답하지 않으면 무한 대기(재현 후 기록).
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향
  - timeout을 너무 짧게 잡으면 정상 호출도 실패한다. 지금 Tool은 로컬 JSON을 읽기만 하므로 수 ms 안에 끝난다.
  - 의도적 flaky 시연은 그대로 둔다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치: #6 테스트에 두 사례를 추가한다.
  - mock MCP가 timeout을 1회 던진 뒤 성공 → retry_count=1
  - 영구 오류 → 재시도 없이 즉시 실패
- 남은 작업: 4번 LLM 재시도는 OpenAI 과금과 연결되므로, 재시도 횟수 상한을 비용 기준으로 정한다.

### #12. 어느 단계에서 느린지 알 수 없어서 지연·타임아웃 원인을 찾지 못한다
상태: 조사 중

① 문제 인식
- 발견한 현상: before.md에서 원인을 "미확인"으로 남긴 이상 결과가 두 건이다.
  - 3-4: q01이 300초 타임아웃
  - 3-5: q03 응답시간이 70~152초로 크게 들쭉날쭉함
- 사용자/서비스에 미치는 영향
  - 느린 원인을 모르면 #4(블로킹)와 #5(타임아웃)를 고쳐도 효과를 확인할 수 없다.
  - 장애가 나도 서버 쪽에 남는 기록이 없다.

② 문제 정의
- 기대 동작(15단원): 요청 하나를 추적 ID로 따라가며 노드별 소요 시간과 오류를 볼 수 있다. 클라이언트가 실패한 요청도 서버 쪽에서 찾을 수 있다.
- 실제 동작
  - 응답 metadata에는 전체 결과만 있다. `parallel_elapsed`(research 병렬 구간) 하나만 시간 정보다.
  - 서버는 `log_level="warning"`으로 돌고, 애플리케이션 로그는 한 줄도 남기지 않는다.
  - 클라이언트가 timeout으로 끊으면 run_id도 받지 못한다.
- 발생 조건 및 재현 방법: bench의 q01 1회차 실패 건을 서버 기록만으로 추적해 보려고 하면, 기록이 없어서 실패한다.
- 해결 완료 기준
  - 모든 응답 metadata에 노드별 소요 시간이 있다.
  - 서버 로그 한 줄에 thread_id·노드·소요 시간·오류가 있다.
  - before.md 3-4·3-5를 이 기록으로 다시 분석해 원인을 하나로 좁힌다.

③ 원인 분석 — 확인한 사실
- 로그/데이터/관련 코드: `server.py:108-122`(`_metadata`), `server.py:197`(`log_level="warning"`), `agent/graph.py`(노드에 시간 기록 없음), `baseline_raw.jsonl`(실패 건 `langsmith_run_id` 없음)
- 확인한 사실
  - `server.py`·`agent/*.py`에 `logging` 사용이 없다(grep 결과 0건).
  - 노드 이벤트(`events`)에 시각과 소요 시간 필드가 없다.
  - LangSmith에는 `@traceable` run별 시간이 남는다. 다만 `/chat/stream`은 루트 run이 없어서 요청 단위로 묶이지 않는다(#10).
- 아직 확인하지 못한 것: before.md 3-4 시각(14:14 무렵)의 LangSmith 기록이 남아 있는지, 그 기록에서 노드별 시간이 보이는지

④ 가설 수립 — 추정
- 가설: 노드 이벤트에 소요 시간만 넣어도 3-4·3-5의 원인이 어느 노드인지 좁혀진다. 후보는 plan(동기 호출), write(긴 생성), 모델 로드다.
- 이 가설을 의심하는 근거: 응답시간 편차가 큰데, 짧은 단계(route·gate·replan)는 코드상 거의 시간을 쓰지 않는다. 의심 구간은 LLM 호출 3곳으로 좁혀진다.
- 가설이 맞다면 관찰돼야 하는 결과: q03의 느린 회차에서 특정 한 노드(예: write)의 시간만 크게 늘어나 있다.

⑤ 실험·실행
- 확인할 방법: 시간 기록을 넣은 뒤 bench를 3회 돌리고, 쿼리별로 어느 노드 시간이 편차를 만드는지 비교한다.
- 변경한 내용 (미실행, 제안)
  1. 각 노드 이벤트에 `elapsed_ms`를 추가하고, 응답 metadata에 `node_timings`를 넣는다.
  2. 서버에 `logging`을 설정하고, 요청 시작·노드 종료·오류를 한 줄 구조화 로그로 남긴다. 필드: thread_id, node, elapsed_ms, error.
  3. bench가 실패한 요청에도 요청 시각과 thread_id를 raw에 남긴다(#5 ⑦과 같은 작업).
- 이 방법을 선택한 이유
  - OpenTelemetry 같은 새 인프라 없이 지금 구조 안에서 할 수 있는 가장 작은 계측이다. 15단원 C(제외) 판단과도 맞는다.
  - LangSmith가 꺼져 있어도(키 없음) 동작한다.
- 필요 시 되돌리는 방법: `git revert`. 응답에 필드만 추가하는 것이라 기존 소비자(프런트, bench)는 깨지지 않는다.

⑥ 결과 검증
- 변경 전: 노드별 시간 없음. 원인 미확인 2건(before.md 3-4, 3-5).
- 변경 후: 미측정
- 완료 기준 충족 여부: 미확인
- 관련 기능에 미친 영향: SSE 이벤트에 필드가 하나 늘지만, 프런트는 모르는 필드를 무시하므로 영향이 없다.
- 결론: 판단 보류

⑦ 재발 방지·자동화
- 필요한 조치
  - bench summary에 노드별 중앙값 열을 추가해, 다음 측정부터 자동으로 비교되게 한다.
  - 로그 필드명은 처음 정한 이름으로 고정한다(15단원 필드 주의점: 필드명 통일).
- 남은 작업: 로그를 파일로 남길지 터미널에만 둘지 정한다. 지금은 실습 환경이라 터미널 출력으로 충분하다고 본다.

---

## Before 증거 수집 — 직접 실행할 때의 터미널 명령 (2026-10-21)

> 코드를 고치기 **전** 상태에서 문제 화면·문제 코드·성능(정확도 포함)을 남기는 절차다. 에이전트 코드는 바꾸지 않는다.
> 산출물: `outputs/before/` (captures/·evidence/·scripts/) → `outputs/before/before_evidence.zip`
> 모든 명령은 프로젝트 루트(`~/subject/1020/all_total_vue_student`)에서 실행한다.

### 0) 서버 띄우기 (터미널 3개)

```bash
# 터미널 1 — Ollama (이미 떠 있으면 생략)
ollama serve
# 터미널 2 — 백엔드 :8100 (ollama, v2). ⚠️ session.db를 지운다
bash sh/run_agent_ollma.sh
# 터미널 3 — Vue 화면 :8600
bash sh/run_frontend.sh

# 확인 — llm_backend=ollama, fast=qwen3:0.6b, quality=qwen3:8b 이어야 Before 측정과 같은 조건
curl -s localhost:8100/health
git diff --stat baseline HEAD -- agent server.py mcp_server.py web_chat.html   # 비어 있으면 Before 코드 그대로
```

### 1) 문제 화면 캡처 (S1·S2)

수동: 브라우저 `http://localhost:8600` → 아래 질문 입력 → 답변이 끝나면 `⌘⇧4`로 캡처
- S1(P1·P2): `web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘` → 기대: "시스템: web-01"만, 매뉴얼 db-down
- S2(P1): `payments-service랑 cache-service 둘 다 저하됐는데 공통 원인이 있는지 분석해줘` → 기대: payments-service만 조사

자동(Playwright + 설치된 Chrome, 프로젝트 밖 가상환경):
```bash
python3 -m venv /tmp/capvenv && /tmp/capvenv/bin/pip install playwright==1.47.0
mkdir -p outputs/before/captures outputs/before/evidence
/tmp/capvenv/bin/python outputs/before/scripts/ui_capture.py \
  outputs/before/captures/S1_q05_multi_system_db_down.png \
  "web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘" \
  --probe-health outputs/before/evidence/S5_health_during_q05.txt     # S5: 처리 중 /health 지연도 같이 기록
/tmp/capvenv/bin/python outputs/before/scripts/ui_capture.py \
  outputs/before/captures/S2_q06_only_one_system.png \
  "payments-service랑 cache-service 둘 다 저하됐는데 공통 원인이 있는지 분석해줘"
```
- macOS `screencapture`는 터미널에 "화면 기록" 권한이 없으면 `could not create image from display`로 실패한다. 그래서 Playwright를 쓴다.

### 2) 서버가 멈추는지 확인 (S5, P4)

질문을 처리하는 동안 다른 터미널에서:
```bash
while true; do curl -s -o /dev/null -w "%{time_total}s\n" localhost:8100/health; sleep 1; done
```
- 2026-10-21 결과: 최대 1.73초. route·plan·analyze(동기 호출) 동안만 멈추고, 가장 긴 write는 비동기 스트림이라 막히지 않는다.
- 최악의 경우는 Before q01이다. 동기 analyze 호출이 300초 동안 멈췄다(S11).

### 3) LangSmith에서 Before 원인 꺼내기 (S3·S4·S11·S12)

```bash
set -a; source .env; set +a
./.venv/bin/python3 -W ignore outputs/before/scripts/fetch_langsmith_evidence.py outputs/before/evidence
```
- S3: q05 plan 입력의 표준 절차에 `- 시스템: web-01` 한 줄만 들어 있다(P1).
- S4: q05 전체 31.9초 중 write가 27.5초(86%)다.
- S11: q01 300초 실패는 `ollama_fast.analyze`의 `ReadTimeout`이다(P3+P4+P5+P6). #5의 원인이 확인됐다.
- S12: q03의 write는 65.7초/1,863토큰에서 147.4초/3,537토큰까지 차이가 나는데, 답변은 107~120자다. qwen3 thinking 토큰으로 추정된다(P9). `ollama_llm.py`에 `think` 옵션이 없다.
- 화면 캡처가 필요하면 출력 파일 맨 위의 `# trace:` URL을 브라우저에서 열고 `⌘⇧4`로 찍는다.

### 4) 입력 검증·스트림 헤더 확인 (S7, P7)

```bash
curl -sS -i --max-time 60 'http://localhost:8100/chat/stream?message=&thread_id=t-empty' | head -20
curl -sS -o /dev/null -w '%{http_code}\n' -X POST localhost:8100/chat \
  -H 'Content-Type: application/json' -d '{"message":"","thread_id":"t-empty2"}'
```
- 기대(문제): 둘 다 `200`이다. 헤더에 `Cache-Control`·`X-Accel-Buffering`이 없다. `ChatRequest.message`에 길이 조건이 없다(`server.py:36`).

### 5) 서버 없이 고장 지점 재현 (S8, P1·P2·P4·P5·P10)

```bash
./.venv/bin/python3 outputs/before/scripts/repro.py "$PWD"           # plan 정규화·분류 폴백·이벤트 루프 정지·MCP timeout·v1
./.venv/bin/python3 outputs/before/scripts/repro_stream.py "$PWD" v2  # 스트림 예외·빈 메시지·헤더·이력 (fake, 임시 DB)
./.venv/bin/python3 outputs/before/scripts/repro_stream.py "$PWD" v1  # v1 스트림 이력 0건
```

### 6) Before 정확도 측정 (S10·S13, 미션 C4 "검색 정확도", 교안 K15)

```bash
# (a) 이미 측정한 baseline raw를 정답 세트로 다시 채점 — 서버 불필요
./.venv/bin/python3 bench/rescore.py --tag baseline

# (b) LangSmith Dataset + evaluate() — heuristic + LLM-judge(Ollama qwen3:8b, 무료). 서버 필요, 약 10~15분
set -a; source .env; set +a
cd bench && ../.venv/bin/python3 -W ignore eval_langsmith.py --prefix baseline; cd ..
```
- 정답은 `bench/eval_set.json`에 있다. `queries.json`(Before 입력)은 수정하지 않았다.
- (a) 결과: 응답 성공률 29/30인데 runbook 정답률 0.739, 조사 범위 recall 0.775다.

### 7) 문제 코드 캡처 (C01~C13)

수동: VS Code에서 각 파일의 해당 줄을 열고 `⌘⇧4`로 찍는다(줄 번호는 `outputs/before/scripts/code_capture.py`의 ITEMS 목록 참고).
자동:
```bash
/tmp/capvenv/bin/python outputs/before/scripts/code_capture.py "$PWD" outputs/before/captures/code
/tmp/capvenv/bin/python outputs/before/scripts/term_render.py outputs/before/captures/terminal outputs/before/evidence/*.txt
```

### 8) 서버 상태를 바꿔야 하는 장면 (S6·S9) — 맨 마지막에

```bash
# S6(P6) 답변 도중 Ollama 종료 → 화면에 오류 표시 없이 입력창만 다시 열린다
/tmp/capvenv/bin/python outputs/before/scripts/ui_capture.py \
  outputs/before/captures/S6_ollama_down_silent_failure.png "log-service 디스크 공간이 부족하다는 알림이 왔어요" \
  --during 'pkill -f "ollama serve"' --during-delay 8
ollama serve &      # 다시 켜기

# S9(P10) v1 롤백 모드 — 장애 질문에도 모니터링을 조회하지 않는다
lsof -ti:8100 | xargs kill -9
set -a; source .env; set +a
LANGCHAIN_PROJECT=capstone-all-total-ollama LLM_BACKEND=ollama SUPERVISOR_VERSION=v1 ./.venv/bin/python3 server.py &
/tmp/capvenv/bin/python outputs/before/scripts/ui_capture.py \
  outputs/before/captures/S9_v1_no_monitoring.png "web-01 장애 진단해줘"
lsof -ti:8100 | xargs kill -9 && bash sh/run_agent_ollma.sh    # v2로 되돌리기
```

### 9) 묶기·정리

```bash
cd outputs && zip -r before/before_evidence.zip before -x 'before/before_evidence.zip' && cd ..
lsof -ti:8100,8600 | xargs kill -9 2>/dev/null; pkill -f "ollama serve"   # 끝나면 종료
```
