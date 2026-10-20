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
