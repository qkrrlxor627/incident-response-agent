# 작업 로그 — all_total_vue (운영 인시던트 대응 에이전트)

## 2026-10-20

### 1. 프로젝트 파악

- **어떤 프로젝트인가**: 서버 장애를 진단하는 LLM 에이전트(AIOps)를 만드는 캡스톤 프로젝트다.
  - 사용자가 채팅으로 "OO 서비스가 이상해요"라고 쓰면, 에이전트가 모니터링 수치(MCP Tool)와 대응 매뉴얼(MCP Resource)을 찾아 진단 답변을 만든다.
  - 사용 기술: LangGraph, MCP, FastAPI, SSE 스트리밍, SQLite 세션, LangSmith 평가, Vue 3 채팅 UI
  - 원본 `all_total`과 백엔드는 같고, `web_chat.html`만 Vue 3로 다시 작성했다.
- **문서 읽기 가이드 작성**: 프로젝트 루트에 `guide.md`를 만들었다.
  - md 읽는 순서: manual_ollma → README → runbooks → regression_test_queries → manual_openai
  - 문서별 요점과 빠른 실행 체크리스트도 함께 정리했다.
- 과제 요구사항(제출 조건)을 적은 문서는 폴더 안에 없다. 수업 공지에서 따로 확인해야 한다.

### 2. 가상환경 세팅 (수동)

`sh/setup_venv.sh`와 같은 명령을 직접 실행했다. 결과는 스크립트로 만든 것과 같다.

```bash
python3 -m venv .venv
./.venv/bin/python3 -m pip install --upgrade pip
./.venv/bin/python3 -m pip install -r requirements.txt
```

### 3. Vue 화면 로컬 실행 확인 (fake 백엔드)

API 키와 Ollama 모델 없이 화면을 보려고 fake 모드로 띄웠다.

```bash
# 터미널 1 — 백엔드 :8100
LANGCHAIN_TRACING_V2=false LLM_BACKEND=fake SUPERVISOR_VERSION=v2 ./.venv/bin/python3 server.py
# 터미널 2 — Vue 화면 :8600
./.venv/bin/python3 web_demo_server.py
```

| 확인 항목 | 결과 |
|---|---|
| `:8100/health` | 정상 (`llm_backend: fake`, `v2`) |
| `:8600` 페이지 | HTTP 200 |
| 화면 서버 → 백엔드 중계 | 정상 |
| "web-01 CPU 급증 원인 진단해줘" | 장애 진단 흐름이 끝까지 동작함 (route → plan → gate → research → replan → write ⇄ validate → finalize) |

알게 된 점:
- fake 모드는 메시지에 `장애|진단|다운|지연|급증|incident|티켓` 중 하나가 있어야 장애 진단으로 처리한다(`agent/fake_llm.py:29`). "느려졌어요"처럼 이 단어가 없으면 일반 대화로 처리한다.
- fake 모드는 정해진 답을 내놓기 때문에, CPU 질문에도 "DB Down" 매뉴얼이 붙는다. 진짜 답변 품질은 Ollama나 OpenAI 모드에서 봐야 한다.

### 4. sh 스크립트를 쓸 때 주의할 점

- `run_agent_ollma.sh`
  - 8100 포트를 쓰는 프로세스를 강제 종료한다.
  - 실행할 때마다 `session.db`를 지운다. 그래서 "재시작 후 대화 기억"(사용 예 4)을 확인하려면 스크립트를 다시 돌리지 말고 `server.py`만 다시 띄워야 한다.
- `setup_ollama.sh`
  - 이미 켜져 있는 Ollama를 강제로 끄고 다시 켠다.
  - `qwen3:8b` 모델은 몇 GB라서 처음 받을 때 시간이 걸린다.
- `run_frontend.sh`: 8600 포트를 쓰는 프로세스를 정리한 뒤 띄운다.
- 지금 쓰는 맥(메모리 16GB)에서는 `qwen3:8b` 응답에 수십 초 걸릴 수 있다.

### 5. GitHub 업로드 준비

- 레포 이름 후보: `incident-response-agent` (1순위), `aiops-incident-agent`, `langgraph-incident-agent`
- About 설명 후보: 모니터링 수치와 대응 매뉴얼을 근거로 서버 장애를 진단하는 LangGraph 에이전트. MCP · FastAPI · SSE 스트리밍 · Vue 3 채팅 UI
- Topics 후보: `langgraph mcp llm-agent fastapi vue3 sse ollama openai langsmith aiops`
- 올리기 전에 `.env`가 `.gitignore`에 들어 있는지 확인해야 한다.

---

## 다음에 할 작업

- [ ] **`.env`를 설정하고 Ollama 실모델로 실행해 본다**
  1. `cp .env.example .env`
     - LangSmith 키가 있으면 `LANGCHAIN_API_KEY`에 넣는다.
     - 키가 없으면 `LANGCHAIN_TRACING_V2=false`로 바꾼다.
  2. `bash sh/setup_ollama.sh` — `qwen3:0.6b`와 `qwen3:8b`를 받는다.
  3. `bash sh/run_agent_ollma.sh` (터미널 1) → `bash sh/run_frontend.sh` (터미널 2)
  4. http://localhost:8600 에서 `doc/regression_test_queries.md`의 질문을 던져 보고, 상황에 맞는 runbook이 붙는지 확인한다.
