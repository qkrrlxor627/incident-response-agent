# 최종 코드 위치 색인 (HEAD 기준, 자동 생성)

- 각 단계 문서(03~09)의 `file:줄`은 **그 단계 커밋 당시** 줄 번호다. 뒤 단계에서 코드가 추가되면 줄이 밀린다.
- 지금 코드에서 위치를 찾을 때는 이 표를 쓴다. 표는 코드의 `[Px BEFORE]` / `[Px AFTER]` 주석을 grep해서 만들었다.
- 직접 찾기: `grep -n "\[P1 " agent/*.py server.py web_chat.html`
- 단계 당시 코드 보기: `git show <커밋>:agent/graph.py | sed -n '120,140p'`

| 문제 | 구분 | 위치 | 주석 내용 |
|---|---|---|---|
| P1 | BEFORE | `agent/graph.py:41` | [P1 BEFORE] 여러 시스템이 나와도 '첫 번째 1개'만 MCP Prompt에 넘김 ── |
| P1·#14 | AFTER | `agent/graph.py:46` | [P1·#14 AFTER] 공통 모듈에서 가져온다 (agent/systems.py) ── |
| P1 | AFTER | `agent/graph.py:52` | """[P1 AFTER] MCP Prompt의 system_name에 질문에 나온 시스템 '전부'를 쉼표로 넘긴다. |
| P1 | BEFORE | `agent/ollama_llm.py:246` | [P1 BEFORE] 목록에 없는 target을 '질문의 첫 시스템'으로 바꿔 버림 → 같은 시스템이 중복돼 제거되고 나머지는 사라짐 ── |
| P1 | AFTER | `agent/ollama_llm.py:250` | [P1 AFTER] 모르는 이름은 버린다. 질문에 나온 시스템은 아래 '누락 보충'이 다시 채운다 ── |
| P1 | BEFORE | `agent/ollama_llm.py:264` | [P1 BEFORE] research가 '0개'일 때만 보충 → 모델이 1개만 내면 나머지 시스템은 조사 누락 ── |
| P1 | AFTER | `agent/ollama_llm.py:274` | [P1 AFTER] 모델이 몇 개를 내든, 질문에 나온 시스템 중 빠진 것을 '항상' 보충한다 ── |
| P1 | BEFORE | `agent/openai_llm.py:180` | [P1 BEFORE] 목록에 없는 target을 '질문의 첫 시스템'으로 바꿔 버림 → 같은 시스템이 중복돼 제거되고 나머지는 사라짐 ── |
| P1 | AFTER | `agent/openai_llm.py:184` | [P1 AFTER] 모르는 이름은 버린다. 질문에 나온 시스템은 아래 '누락 보충'이 다시 채운다 ── |
| P1 | BEFORE | `agent/openai_llm.py:198` | [P1 BEFORE] research가 '0개'일 때만 보충 → 모델이 1개만 내면 나머지 시스템은 조사 누락 ── |
| P1 | AFTER | `agent/openai_llm.py:208` | [P1 AFTER] 모델이 몇 개를 내든, 질문에 나온 시스템 중 빠진 것을 '항상' 보충한다 ── |
| P1·#14 | AFTER | `agent/systems.py:1` | """[P1·#14 AFTER] 시스템 이름 추출 공통 모듈. |
| #14 | BEFORE | `agent/graph.py:29` | [#14 BEFORE] ollama_llm.py·openai_llm.py와 똑같은 복사본 ── |
| #14 | BEFORE | `agent/ollama_llm.py:36` | [#14 BEFORE] graph.py·ollama_llm.py·openai_llm.py에 똑같이 복사돼 있던 시스템 추출 로직 ── |
| #14 | AFTER | `agent/ollama_llm.py:70` | [#14 AFTER] 공통 모듈 agent/systems.py 하나로 모았다 (K14 모듈화) ── |
| #14 | BEFORE | `agent/openai_llm.py:32` | [#14 BEFORE] graph.py·ollama_llm.py·openai_llm.py에 똑같이 복사돼 있던 시스템 추출 로직 ── |
| #14 | AFTER | `agent/openai_llm.py:64` | [#14 AFTER] 공통 모듈 agent/systems.py 하나로 모았다 (K14 모듈화) ── |
| P2 | AFTER | `agent/fake_llm.py:123` | notes = [c["data"] for c in collected if c["source"] == "note"]   # [P2 AFTER] 이상 없음/감시 대상 아님 |
| P2 | BEFORE | `agent/graph.py:267` | [P2 BEFORE] 모든 시스템의 알림을 한 문자열로 합친 뒤 규칙을 위에서부터 검사 ── |
| P2 | AFTER | `agent/graph.py:279` | [P2 AFTER] 시스템을 '하나씩', 질문에 나온 순서대로 본다 (K8 근거 기반 분류) ── |
| P2 | AFTER | `agent/graph.py:326` | [P2 AFTER] 분류 근거가 없으면(None) runbook gap task를 만들지 않고 그대로 진행 ── |
| P2 | AFTER | `agent/ollama_llm.py:280` | [P2 AFTER] 감시 대상이 아닌 시스템만 나온 질문(q08 billing-service)은 조사하지 않는다 ── |
| P2 | AFTER | `agent/ollama_llm.py:333` | elif c["source"] == "note":   # [P2 AFTER] runbook을 붙이지 않은 이유 (graph._no_runbook_note) |
| P2 | AFTER | `agent/openai_llm.py:214` | [P2 AFTER] 감시 대상이 아닌 시스템만 나온 질문(q08 billing-service)은 조사하지 않는다 ── |
| P2 | AFTER | `agent/openai_llm.py:277` | elif c["source"] == "note":   # [P2 AFTER] runbook을 붙이지 않은 이유 (graph._no_runbook_note) |
| P3 | BEFORE | `agent/graph.py:152` | [P3 BEFORE] 모델의 needs_analysis 판단만 믿음 → 0.6b 모델은 거의 항상 true (incident 8종 중 7종에서 분석 실행) ── |
| P3 | AFTER | `agent/graph.py:158` | [P3 AFTER] 이중 게이트 (K7 권위 게이트) ── |
| P4 | AFTER | `agent/fake_llm.py:35` | [P4 AFTER] 실모델 백엔드와 인터페이스를 맞추려고 route·plan·analyze를 async def로 바꿨다 |
| P4 | BEFORE | `agent/graph.py:137` | [P4 BEFORE] result, usage = deps.fast_llm.plan(state["query"], procedure) |
| P4 | AFTER | `agent/graph.py:138` | result, usage = await deps.fast_llm.plan(state["query"], procedure)   # [P4 AFTER] |
| P4 | BEFORE | `agent/graph.py:352` | [P4 BEFORE] summary, usage = deps.fast_llm.analyze(state.get("collected", [])) |
| P4 | AFTER | `agent/graph.py:354` | summary, usage = await deps.fast_llm.analyze(state.get("collected", []))   # [P4 AFTER] |
| P4 | BEFORE | `agent/graph.py:94` | [P4 BEFORE] result, usage = deps.fast_llm.route(state["query"])   ← 동기 호출: 이벤트 루프 정지 |
| P4 | AFTER | `agent/graph.py:95` | result, usage = await deps.fast_llm.route(state["query"])   # [P4 AFTER] await |
| P4 | BEFORE | `agent/ollama_llm.py:117` | [P4 BEFORE] async 노드 안에서 '동기' HTTP 호출 → 응답을 기다리는 동안 이벤트 루프 전체가 멈춤 ── |
| P4 | AFTER | `agent/ollama_llm.py:122` | [P4 AFTER] httpx.AsyncClient + await → 기다리는 동안 다른 요청을 처리한다 (K12 블로킹 금지) ── |
| P4 | AFTER | `agent/ollama_llm.py:205` | async def route(self, query: str) -> tuple[dict, dict]:   # [P4 AFTER] def → async def |
| P4 | AFTER | `agent/ollama_llm.py:224` | async def plan(self, query: str, procedure_prompt: str) -> tuple[dict, dict]:   # [P4 AFTER] |
| P4 | AFTER | `agent/ollama_llm.py:293` | async def analyze(self, collected: list[dict]) -> tuple[str, dict]:   # [P4 AFTER] |
| P4 | BEFORE | `agent/openai_llm.py:103` | [P4 BEFORE] resp = httpx.post(OPENAI_URL, json=payload, headers=headers, timeout=120.0) |
| P4 | AFTER | `agent/openai_llm.py:104` | async with httpx.AsyncClient(timeout=120.0) as client:   # [P4 AFTER] |
| P4 | AFTER | `agent/openai_llm.py:87` | [P4 AFTER] ollama_llm.py와 같은 이유로 비동기로 바꿨다 (Before: httpx.post 동기 호출, timeout=120.0) |
| P5·P6 | AFTER | `agent/errors.py:1` | """[P5·P6 AFTER] 에러 분류 공통 모듈. |
| P5 | BEFORE | `agent/graph.py:198` | data = await deps.mcp.read_resource(uri, server=runbook_server)   ← [P5 BEFORE] runbook은 재시도 없음 |
| P5 | AFTER | `agent/graph.py:215` | [P5 AFTER] runbook(Resource) 읽기도 재시도한다 |
| P5 | BEFORE | `agent/mcp_client.py:107` | [P5 BEFORE] async with self._lock: |
| P5 | BEFORE | `agent/mcp_client.py:108` | [P5 BEFORE]     result = await self.sessions[server].call_tool(name, arguments)   ← 시간 제한 없음 |
| P5 | AFTER | `agent/mcp_client.py:115` | result = await self._call("list_resource_templates",   # [P5 AFTER] 시간 제한 |
| P5 | BEFORE | `agent/mcp_client.py:132` | [P5 BEFORE] async with self._lock: |
| P5 | BEFORE | `agent/mcp_client.py:133` | [P5 BEFORE]     result = await self.sessions[server].read_resource(uri) |
| P5 | AFTER | `agent/mcp_client.py:140` | result = await self._call("list_prompts", lambda: self.sessions[server].list_prompts())   # [P5 AFTER] |
| P5 | AFTER | `agent/mcp_client.py:155` | result = await self._call(f"get_prompt({name})",   # [P5 AFTER] |
| P5 | AFTER | `agent/mcp_client.py:32` | [P5 AFTER] MCP 호출 1건의 시간 제한 ── |
| P5 | AFTER | `agent/mcp_client.py:83` | """[P5 AFTER] 모든 MCP 요청이 지나가는 관문: 시간 제한 + 예외를 '재시도 가능 여부'로 번역. |
| P5 | BEFORE | `agent/retry.py:21` | [P5 BEFORE] async def with_retry(fn, *args, retries: int = 3, base_delay: float = 0.3, **kwargs): |
| P5 | BEFORE | `agent/retry.py:30` | [P5 BEFORE] except asyncio.TimeoutError: |
| P5 | AFTER | `agent/retry.py:31` | except Exception as exc:   # [P5 AFTER] 일시적인 에러인지는 _is_transient가 판단 |
| P5 | BEFORE | `agent/retry.py:34` | [P5 BEFORE] delay = base_delay * (3 ** (attempt - 1)) |
| P5 | BEFORE | `agent/retry.py:3` | [P5 BEFORE] asyncio.TimeoutError(일시적)만 재시도하고, 그 외(ValueError 등 영구적)는 즉시 전파한다. |
| P5 | AFTER | `agent/retry.py:5` | [P5 AFTER] 재시도 대상 = TimeoutError + recoverable=True인 ToolError. |
| P6 | BEFORE | `agent/graph.py:195` | [P6 BEFORE] 예외 격리 없이 gather → task 하나가 실패하면 gather 전체가 예외 → 요청 전체 실패 ── |
| P6 | AFTER | `agent/graph.py:201` | [P6 AFTER] 코루틴마다 try/except로 격리 → 성공한 것만 모아 '부분 응답'을 만든다 (K10·K12) ── |
| P6 | AFTER | `agent/graph.py:232` | if "error" in r:   # [P6 AFTER] 실패한 task: 상태 failed + TaskFailed 이벤트, 수집 결과에는 넣지 않는다 |
| P6 | AFTER | `agent/graph.py:308` | [P6 AFTER] 조회가 실패해서 데이터가 없는 것을 '정상'으로 착각하지 않는다 |
| P6 | AFTER | `agent/graph.py:61` | RESEARCH_CONCURRENCY = 4   # [P6 AFTER] research 동시 실행 상한 |
| P6 | AFTER | `agent/ollama_llm.py:21` | [P6 AFTER] 환경변수로 바꿀 수 있게 했다 — 장애 재현 때 중간 프록시를 끼워 "답변 도중 끊김"을 만들기 위함 |
| P6 | BEFORE | `server.py:171` | [P6 BEFORE] 예외가 나면 FastAPI 기본 500 "Internal Server Error" (원인·재시도 가능 여부 없음) |
| P6 | AFTER | `server.py:173` | [P6 AFTER] 에러를 분류해 503 + {code, recoverable, message}로 돌려준다 |
| P6 | BEFORE | `server.py:200` | [P6 BEFORE] gen() 안에서 예외가 나면 스트림이 그냥 끊겼다 → 브라우저는 onerror만 받고 조용히 멈춤 (S6) |
| P6 | AFTER | `server.py:201` | [P6 AFTER] 실제 작업은 _events()에 두고, gen()이 감싸서 예외를 Error 이벤트로 바꾼 뒤 [DONE]까지 보낸다 |
| P6 | AFTER | `web_chat.html:101` | [P6 AFTER] 서버가 보낸 Error 이벤트 / 연결 끊김을 빨간 말풍선으로 보여준다 --> |
| P6 | AFTER | `web_chat.html:132` | [P6 AFTER] 조사 1건이 실패해도 나머지로 답한다(부분 응답) → 어떤 조사가 실패했는지 단계에 보여준다 |
| P6 | AFTER | `web_chat.html:170` | [P6 AFTER] '다시 시도' 버튼 — 같은 질문을 다시 보낸다 |
| P6 | AFTER | `web_chat.html:190` | let finished = false;   // [P6 AFTER] [DONE]을 받았는지 — 못 받고 끊기면 연결 오류로 표시 |
| P6 | AFTER | `web_chat.html:222` | [P6 AFTER] 서버가 보낸 오류 이벤트 {code, recoverable, message} |
| P6 | BEFORE | `web_chat.html:238` | [P6 BEFORE] es.onerror = () => { es.close(); sending.value = false; };   ← 조용히 끝남 |
| P6 | AFTER | `web_chat.html:242` | if (!finished) {   // [P6 AFTER] [DONE] 전에 끊겼으면 사용자에게 알린다 |
| P6 | AFTER | `web_chat.html:43` | * [P6 AFTER] 오류 말풍선 — Before에는 오류가 나도 화면에 아무 표시가 없었다(S6) */ |
| P7 | AFTER | `server.py:154` | [P7 AFTER] 사용자 메시지를 '먼저' 저장한다 — 처리 도중 실패해도 질문은 이력에 남는다 |
| P7 | BEFORE | `server.py:163` | [P7 BEFORE] deps.session_store.append(thread_id, "user", message) |
| P7 | BEFORE | `server.py:184` | [P7 BEFORE] async def chat_stream(message: str, thread_id: str = "default"):   ← 검증 없음 |
| P7 | AFTER | `server.py:193` | [P7 AFTER] /chat과 같은 규칙으로 검증한다 (EventSource는 GET만 쓸 수 있어 Query로 받는다) |
| P7 | AFTER | `server.py:212` | @traceable(name="chat_stream_request")   # [P7 AFTER] 스트림 요청도 LangSmith 루트 run으로 남긴다 (Before: /chat만 chat_requ |
| P7 | AFTER | `server.py:215` | await deps.session_store.append(thread_id, "user", message)   # [P7 AFTER] 질문을 먼저 저장 (중간에 끊겨도 남는다) |
| P7 | AFTER | `server.py:221` | [P7 AFTER] v1 스트림도 답변을 저장한다 (Before: v1 분기는 이력을 전혀 저장하지 않았다) |
| P7 | BEFORE | `server.py:249` | [P7 BEFORE] deps.session_store.append(thread_id, "user", message)   ← 끝까지 간 경우에만 저장 |
| P7 | BEFORE | `server.py:252` | [P7 BEFORE] return StreamingResponse(gen(), media_type="text/event-stream") |
| P7 | AFTER | `server.py:253` | [P7 AFTER] SSE 헤더: 프록시(nginx 등)·브라우저가 버퍼링/캐시하지 않고 이벤트를 즉시 흘려보내게 한다 |
| P7 | BEFORE | `server.py:42` | [P7 BEFORE] 길이·공백 검사가 없음 → 빈 메시지("")도 200 OK로 받아 LLM까지 호출했다 (S7) ── |
| P7 | AFTER | `server.py:46` | [P7 AFTER] 입력 계약을 모델에 명시한다 (K2 Pydantic 검증) — 위반하면 FastAPI가 422를 돌려준다 ── |
| P9 | AFTER | `agent/graph.py:482` | """[P9 AFTER] 노드 실행 시간을 재서 state['timings']에 누적하고, JSON 한 줄로 로그를 남긴다. |
| P9 | BEFORE | `agent/graph.py:501` | [P9 BEFORE] node = lambda fn: partial(fn, deps=deps)   # Wave 13 — 명시적 의존성 주입 |
| P9 | AFTER | `agent/graph.py:502` | [P9 AFTER] 의존성 주입은 그대로 두고, 바깥에 시간 측정 래퍼(_timed)를 씌운다 |
| P9 | AFTER | `agent/graph.py:62` | log = logging.getLogger("agent.graph")   # [P9 AFTER] JSON 한 줄 로그 (server.py가 INFO로 출력) |
| P9 | AFTER | `agent/graph.py:84` | timings: dict   # [P9 AFTER] 노드별 소요 시간(ms) — 병목 위치를 응답 metadata에서 바로 본다 |
| P9 | AFTER | `agent/ollama_llm.py:130` | "think": OLLAMA_THINK,            # [P9 AFTER] 숨은 사고 토큰 끔 |
| P9 | AFTER | `agent/ollama_llm.py:135` | async with httpx.AsyncClient(timeout=timeout) as client:   # [P9 AFTER] 단계별 timeout |
| P9 | AFTER | `agent/ollama_llm.py:156` | "think": OLLAMA_THINK,            # [P9 AFTER] |
| P9 | BEFORE | `agent/ollama_llm.py:161` | [P9 BEFORE] async with httpx.AsyncClient(timeout=300.0) as client: |
| P9 | AFTER | `agent/ollama_llm.py:162` | async with httpx.AsyncClient(timeout=timeout) as client:   # [P9 AFTER] 호출한 단계의 timeout |
| P9 | AFTER | `agent/ollama_llm.py:24` | [P9 AFTER] 단계별 시간 제한 (Before: 모든 호출이 timeout=300.0 하나) ── |
| P9 | AFTER | `agent/ollama_llm.py:29` | [P9 AFTER] qwen3의 '생각(thinking)' 토큰을 끈다 ── |
| P9 | AFTER | `agent/ollama_llm.py:338` | return await self._chat_stream(system, user, on_token=on_token, timeout=WRITE_TIMEOUT)   # [P9 AFTER] write만 1 |
| P9 | AFTER | `server.py:146` | "timings_ms": result.get("timings", {}),   # [P9 AFTER] 노드별 소요 시간 — 어디가 느린지 응답에서 바로 본다 |
| P9 | BEFORE | `server.py:238` | [P9 BEFORE] ev = {**ev, "node": node_name} |
| P9 | AFTER | `server.py:239` | ev = {**ev, "node": node_name,   # [P9 AFTER] 이 노드가 걸린 시간(누적 ms)도 같이 보낸다 |
| P9 | AFTER | `server.py:34` | [P9 AFTER] agent.* 로거의 JSON 한 줄 로그(노드별 elapsed_ms)를 서버 터미널에 출력한다 |
| P9 후속 | AFTER | `agent/graph.py:96` | [P9 후속 AFTER] route 권위 보정 — After 측정에서 발견한 회귀 ── |
| P10 | AFTER | `agent/supervisor_v1.py:10` | [P10 AFTER] (기준 외 제안) 장애 판단은 v2 route의 코드 fallback과 같은 키워드 규칙으로, |
| P10 | BEFORE | `agent/supervisor_v1.py:25` | [P10 BEFORE] |
| P10 | AFTER | `agent/supervisor_v1.py:33` | [P10 AFTER] 질문 자체로 장애 여부를 판단한다 (LLM 응답 문구에 의존하지 않음) |
| P10 | BEFORE | `agent/supervisor_v1.py:54` | [P10 BEFORE] "retry_count": next((e.get("retries", 0) for e in events if e["type"] == "TaskCompleted"), 0)} |
| P10 | BEFORE | `agent/supervisor_v1.py:7` | [P10 BEFORE] 장애 여부를 'fake LLM의 응답 문구'("도와드릴까요")로 판단했다. |
| P11 | AFTER | `agent/fake_llm.py:25` | """[P11 AFTER] 결정론 judge — 답변에 수집된 시스템 이름이 모두 있으면 grounded.""" |
| P11 | BEFORE | `agent/graph.py:385` | [P11 BEFORE] 형식만 검사: 30자 이상 + "1)" 포함이면 합격, 3번째는 무조건 통과 ── |
| P11 | AFTER | `agent/graph.py:397` | [P11 AFTER] 규칙 검사(코드) + LLM-as-a-Judge(모델) 혼합, 재작성은 1회까지 (K9) ── |
| P11 | AFTER | `agent/ollama_llm.py:104` | JUDGE_SCHEMA = {   # [P11 AFTER] judge 출력 형식 |
| P11 | AFTER | `agent/ollama_llm.py:183` | [P11 AFTER] LLM-as-a-Judge: 답변이 '수집된 사실'에 근거하는지 판정 (K9) ── |
| P11 | AFTER | `agent/openai_llm.py:117` | """[P11 AFTER] ollama_llm.OllamaLLM.judge와 같은 역할 (JSON 모드).""" |
| P11 | BEFORE | `web_chat.html:139` | [P11 BEFORE] Validation: e => e.verdict === '합격' ? '검수 통과' : '검수 반려 → 다시 작성', |
| P11 | AFTER | `web_chat.html:140` | [P11 AFTER] 반려 사유(규칙 위반·judge 판정)와 '상한 도달 후 경고 통과'를 구분해 보여준다 |
| E15 | AFTER | `agent/session_store.py:10` | [E15 AFTER] |
| E15 | BEFORE | `agent/session_store.py:28` | [E15 BEFORE] self.conn = sqlite3.connect(db_path, check_same_thread=False)   ← 모든 요청이 연결 1개 공유 |
| E15 | AFTER | `agent/session_store.py:35` | [E15 AFTER] thread_id로 찾는 쿼리(load)를 위한 인덱스 |
| E15 | AFTER | `agent/session_store.py:57` | [E15 AFTER] async 인터페이스: 이벤트 루프를 막지 않는다 ── |
| E15 | BEFORE | `agent/session_store.py:58` | [E15 BEFORE] def load(self, thread_id: str) -> list[dict]: rows = self.conn.execute(...) |
| E15 | BEFORE | `agent/session_store.py:62` | [E15 BEFORE] def append(self, thread_id, role, content): self.conn.execute(...); self.conn.commit() |
| E15 | BEFORE | `agent/session_store.py:6` | [E15 BEFORE] async 서버(FastAPI)에서 동기 sqlite3 호출을 그대로 했다. |
| E15 | AFTER | `agent/session_store.py:71` | """[E15 AFTER] 저장소 팩토리. SESSION_DB 환경변수로 파일 위치를 바꿀 수 있다 (테스트·스모크용).""" |
| E15 | AFTER | `server.py:156` | await deps.session_store.append(thread_id, "user", message)   # [E15 AFTER] await |
| E15 | AFTER | `server.py:164` | await deps.session_store.append(thread_id, "assistant", result["final"])   # [E15 AFTER] await |
| E15 | AFTER | `server.py:214` | history = await deps.session_store.load(thread_id)   # [E15 AFTER] await |
| E15 | AFTER | `server.py:222` | await deps.session_store.append(thread_id, "assistant", result["final"])   # [E15 AFTER] await |
| E15 | AFTER | `server.py:250` | await deps.session_store.append(thread_id, "assistant", final)   # [E15 AFTER] await |
| E15 | BEFORE | `server.py:97` | [E15 BEFORE] session_store=SqliteSessionStore(),   ← 동기 저장소 |
| E15 | AFTER | `server.py:98` | session_store=create_session_store(),   # [E15 AFTER] 비동기 저장소를 팩토리로 주입 |
