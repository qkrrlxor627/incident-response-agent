# 작업 로그 — all_total_vue (운영 인시던트 대응 에이전트)

## 2026-10-20

### 1. 프로젝트 파악

- **어떤 프로젝트인가**: 서버 장애를 진단하는 LLM 에이전트(AIOps)를 만드는 캡스톤 프로젝트다.
  - 사용자가 채팅으로 "OO 서비스가 이상해요"라고 쓰면, 에이전트가 모니터링 수치(MCP Tool)와 대응 매뉴얼(MCP Resource)을 찾아 진단 답변을 만든다.
  - 사용 기술: LangGraph, MCP, FastAPI, SSE 스트리밍, SQLite 세션, LangSmith 평가, Vue 3 채팅 UI
  - 원본 `all_total`과 백엔드는 같고, `web_chat.html`만 Vue 3로 다시 작성했다.
- **문서 읽기 가이드 작성**: `doc/guide.md`에 있다(처음엔 루트에 만들었다가 `doc/`로 옮김).
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

### 6. GitHub 업로드 완료

- 레포: https://github.com/qkrrlxor627/incident-response-agent (branch `main`)
- 첫 커밋 `ae09c45`. 작성자는 본인(박기택)만이다. Claude 공동 작성자 줄은 넣지 않았다.
- `.gitignore`에 `.DS_Store`를 추가했다. `.env`, `.venv/`, `session.db`는 올라가지 않았다.

### 7. Ollama 실모델 실행 (완료)

- `.env` 설정 → `setup_ollama.sh` → `run_agent_ollma.sh` → `run_frontend.sh` 순서로 실행했다.
- `/health` 결과: `llm_backend: ollama`, fast=`qwen3:0.6b`, quality=`qwen3:8b`, v2
- 과금: OpenAI는 호출하지 않는다. LangSmith는 tracing이 켜져 있어서 기록이 올라간다(무료 한도 안).

### 8. Before 기준선(baseline) 측정 (완료, 코드 수정 없음)

- 현재 HEAD(`ae09c45`)에 git tag `baseline`을 붙였다(로컬에만 있고 push하지 않음).
- 추가한 파일(아직 커밋하지 않음):
  - `bench/queries.json`: 회귀 쿼리 10건. `expected_incident_type`은 비워 둠
  - `bench/run_baseline.py`: 워밍업 1회 + 쿼리당 3회 → raw/summary 저장
  - `bench/results/baseline_raw.jsonl`, `bench/results/baseline_summary.csv`
  - `bench/results/before.md`: 기준선 리포트
  - `bench/results_run.log`: 실행 로그
- 결과 요약:
  - 성공률 0.97 (29/30). 실패 1건은 q01 1회차 300초 타임아웃이고 원인은 미확인이다.
  - 응답시간 중앙값: incident 36초, chat 1.3초. q03(디스크)이 71~152초로 가장 느렸다.
  - retry 0회, validate 반려 0회. 3회 반복 사이에 분류가 바뀐 경우는 없었다.
- 찾은 문제:
  1. 여러 시스템을 언급해도 1개만 조사한다(q04~q06). `ollama_llm.py`의 `plan()`이 원인이고, `_guess_targets()`는 research가 0개일 때만 보충한다(추정).
  2. q05가 `db-down`으로 오분류된다. 정상인 web-01만 조사해서 `_classify_incident_type`의 기본값으로 빠졌다.
  3. analysis가 거의 매번 실행된다. incident 8종 중 7종이고, 원인은 `needs_analysis=true` 남발이다(추정).
  4. validate가 형식("1)" + 30자)만 검사해서 조사가 빠진 답변도 합격한다.
- 응답만으로는 토큰 수를 알 수 없다. LangSmith의 llm run 출력값(`usage.tokens`)으로 확인한다. `eval/run_eval.py`는 없다.

### 9. 발표 원고 작성

- `doc/presentation_k.md`를 만들었다. 기준은 미션(최종 보고서 순서 5항목)과 `doc/lessonstandard_k.md`(교안 15단원)다.
- 들어 있는 것:
  - 5분 시간 배분과 슬라이드별 대본
  - 개선 사항: 문제 해결 기록 ①~⑦ 틀
  - 기술 요소 17개 ↔ 코드 위치 ↔ 교안 단원 표
  - 캡처 체크리스트
  - Before 수치
  - 한계·트레이드오프
  - 예상 질문 3개
- 비어 있는 것: After 수치, ⑥ 결과 검증, 단위 테스트 경로. `【After 측정 후 기입】`으로 두고, 지어낸 수치는 넣지 않았다.
- 솔직하게 적은 것: RAG는 벡터 검색이 아니라 코드 규칙으로 runbook을 고르는 방식이다. 단위 테스트는 현재 없다.

### 10. `/improve` 스킬 구성 (미션 + 교안 기준 → 개선안 문서)

- 만든 파일:
  - 로컬 전용:
    - `.claude/skills/improve/SKILL.md`, `template.md`
    - `.claude/agents/rubric-reviewer.md`: Read/Grep/Glob만 쓰는 sonnet 채점자
    - `.claude/settings.json`
    - `CLAUDE.md`
  - GitHub 대상:
    - `doc/mission_k.md`: 미션 원문을 그대로 저장
    - `outputs/.gitkeep`
- ID 체계:
  - C = 미션 항목(C1~C5, C3-a~i)
  - K = 교안 단원 번호(K1 ADR ~ K15 Observability)
- 사용법: `/improve v1`, 또는 `/improve v1 C3-g K9`(특정 ID 집중). 산출물은 `outputs/improvement-<버전>.md`다.
- 안전장치:
  - `.claude/`와 `CLAUDE.md`는 `.git/info/exclude`로 업로드에서 뺐다. `.gitignore`는 고치지 않았다.
  - `settings.json`의 deny로 `mission_k.md`와 `lessonstandard_k.md`의 Edit을 막았다. Bash 쓰기는 막지 못한다.
  - 기존 파일은 하나도 수정하지 않았다.
- 작성자 고정:
  - 저장소 로컬 git config: `user.name=박기택`, `user.email=qkrrlxor627@gmail.com`
  - `settings.json`에서 attribution을 껐다(`includeCoAuthoredBy: false`).
  - 커밋·PR에 Claude 공동 작성자 표기를 넣지 않는다.

### 11. 하네스 구축 — hook 3개 + `/bench` 스킬 + 단위 테스트 (완료)

전부 직접 시험했다. 각 hook은 스크립트 단독 시험과 실제 하네스 차단을 둘 다 확인했다.

| 구성 | 파일 | 동작 | 검증 |
|---|---|---|---|
| **git commit guard** (PreToolUse·Bash) | `.claude/hooks/git_guard.py` | `.claude`/`CLAUDE.md` add, `git add -f`, Claude 표기(`Co-Authored-By` 등) 커밋·태그, `--author` 변경을 차단 | 단독 12건 통과. 실제로 `git add --dry-run CLAUDE.md`가 실행 전에 차단됨 |
| **원본 보호** (PreToolUse·Bash) | `.claude/hooks/protect_files.py` | `mission_k.md`·`lessonstandard_k.md`에 대한 `>`, `>>`, `sed -i`, `rm`, `mv`, `cp`(덮어쓰기), `git checkout`을 차단. 읽기는 통과 | 단독 13건 통과. 실제로 `echo >> doc/mission_k.md`가 차단됨 |
| **auto pytest** (PostToolUse·Edit\|Write) | `.claude/hooks/auto_pytest.py` | `agent/`·`tests/`의 `.py`를 고친 직후 `pytest tests -q -x` 실행. 실패하면 결과를 Claude에 전달(exit 2) | 통과·대상 아님·실패 3가지 경로 확인. 실패용 임시 테스트는 삭제함 |
| **`/bench` 스킬** | `.claude/skills/bench/SKILL.md`, `scripts/compare.py` | 덮어쓰기 방지 → /health·모델 일치 확인 → 측정(백그라운드) → `compare_<tag>_vs_baseline.md` 생성 → 요약 | baseline 대 baseline 수치가 `before.md`와 일치(29/30, 36.0초, $0.1637). 가짜 After로 ⚠️ 표시 확인 |
| **단위 테스트** | `tests/conftest.py`, `tests/test_agent_units.py`, `requirements-dev.txt`(pytest 8.3.4) | 시스템명 추출, `_guess_targets`, 분류 규칙(5종 + 폴백 + 순서), gate, validate | **15 passed, 1 xfailed** |

- xfail 1건 = P1 버그(여러 시스템 중 1개만 조사, `before.md` 3-1)를 테스트로 고정한 것이다.
  - `strict=True`라서 고치는 순간 "예상 밖 통과(XPASS)"로 실패가 뜬다. 그때 마커를 지우면 정식 회귀 테스트가 된다.
- pytest는 `.venv`에만 설치했다. 기존 `requirements.txt`는 고치지 않고 `requirements-dev.txt`를 새로 만들었다.
- 하네스 동작 원리(직접 확인):
  - 하네스가 도구 입력을 JSON으로 stdin에 넘긴다.
  - 스크립트가 exit 2 + stderr를 돌려주면 차단되고, 그 이유가 Claude에게 전달된다.
  - exit 0이면 그대로 통과한다.
- 한계:
  - hook은 **Claude가 실행하는 명령만** 검사한다. 터미널에서 직접 치는 git은 검사하지 않는다(막으려면 git `commit-msg` hook이 따로 필요).
  - `git commit -F 파일`의 메시지 내용, `python -c`로 파일 쓰기는 검사하지 못한다.
- 내장이라 따로 설치하지 않은 것:
  - `/code-review`, `/simplify`, `/security-review`
  - 발표자료용 Slides 아티팩트, `dataviz`

### 12. Claude 구성 설명서 분리

- Claude 관련 구성(스킬·에이전트·hook·설정·사용한 내장 스킬)은 이제 `doc/workClaude.md`에 따로 기록한다. 처음 이름은 `claudeSkillDes.md`였다.
- `workLog.md`에는 프로젝트 진행만 남긴다.
- `workClaude.md`도 로컬 전용이다(`.git/info/exclude`). `CLAUDE.md`에 갱신 규칙을 1줄 추가했다.

### 13. 파일별 워크스루 (진행 중 — 2/8단계까지 완료)

작업에 들어가기 전에 코드를 파일 단위로 같이 읽으면서, `doc/guide.md`의 문제 기록(#1~#12)이 실제 코드 어디에 있는지 확인하고 있다. 코드는 아직 수정하지 않았다.

| 단계 | 파일 | 관련 기록 | 상태 |
|---|---|---|---|
| 0 | 전체 폴더 구조와 요청 흐름 | — | ✅ |
| 1 | `server.py` | #3 #10 #12 | ✅ |
| 2 | `agent/deps.py` + `agent/graph.py` | #2 #3 #8 #9 #12 | ✅ |
| 3 | `agent/ollama_llm.py` (+ `openai_llm.py`는 다른 점만) | #1 #4 #5 | ⬜ **다음 차례** |
| 4 | `agent/mcp_client.py` + `agent/retry.py` | #11 | ⬜ |
| 5 | `fake_llm.py` · `session_store.py` · `supervisor_v1.py` | #6 | ⬜ |
| 6 | `mcp_server.py` · `mcp_server_docs.py` | — | ⬜ |
| 7 | `web_demo_server.py` + `web_chat.html` | #3 #10 | ⬜ |
| 8 | `bench/run_baseline.py` + `queries.json` | #7 #12 | ⬜ |

1~2단계에서 확인한 내용:
- `server.py`
  - lifespan 싱글턴은 교안 2단원을 충족한다.
  - 브라우저가 쓰는 `/chat/stream`(148줄)은 `/chat`보다 보호 장치가 적다. 입력 검증(149), `@traceable`(157), 예외 처리, 버퍼링 헤더(192)가 없다. 이력은 스트림이 끝까지 가야만 저장한다(188-189).
  - `logging`이 없다(197줄 `log_level="warning"`).
- `graph.py`
  - gate가 모델의 `needs_analysis`를 그대로 믿는다(127).
  - `gather`에 예외 격리가 없다(172). `read_resource`는 재시도도 없다(168).
  - 분류 규칙이 아무것도 맞지 않으면 `db-down`으로 빠진다(213).
  - validate는 "30자 + `1)`"만 본다(279).
  - 시간을 재는 곳은 research 하나뿐이다(171-173).
- `deps.py`: 주입식 구조라 테스트하기 쉽다. 문제 없음.

워크스루 중에 발견한 문서 불일치:
- `guide.md`의 **#6(자동 테스트 없음)은 이미 상당 부분 해결된 상태다.** 11번 작업에서 `tests/`(15 passed, 1 xfailed)와 `requirements-dev.txt`를 만들었는데, guide.md는 그 전 상태를 기준으로 썼다.
  - 그래서 #6의 "상태"와 ③ 내용을 갱신해야 한다.
  - 아직 남은 부분: `OllamaFastLLM.plan()` 정규화 테스트(xfail 1건으로 고정됨), research 실패 격리 테스트, 스트림 경로 테스트.

워크스루를 마친 뒤 할 일: guide.md의 최우선 순서(#12 → #6 → #7 → #1 …)대로 작업한다. 단, #6은 위 상태를 반영해 순서를 다시 본다.

### 현재 파일 위치

| 파일 | 위치 | GitHub |
|---|---|---|
| 작업 로그 (이 파일) | `doc/workLog.md` | 올라감 |
| 읽기 가이드 | `doc/guide.md` | 올라감 |
| 교안 기준표 | `doc/lessonstandard_k.md` | **제외** (교안 정리본이라 로컬 전용) |
| 미션 | `doc/mission_k.md` | 올라감 |
| 발표 원고 | `doc/presentation_k.md` | 올라감 |
| Before 리포트 | `bench/results/before.md` | 올라감 |
| 측정 스크립트 / 질의셋 | `bench/run_baseline.py`, `bench/queries.json` | 올라감 |
| 개선안 산출물 폴더 | `outputs/` | 올라감 |
| 단위 테스트 | `tests/`, `requirements-dev.txt` | 올라감 |
| 스킬(`/improve`, `/bench`) · 리뷰어 · hook 3개 · 설정 | `.claude/` | **제외** (로컬 전용) |
| 작업 규칙 | `CLAUDE.md` | **제외** (로컬 전용) |
| Claude 구성 설명서 | `doc/workClaude.md` | **제외** (로컬 전용) |

### git 상태 메모

- GitHub(`main`)에 올라간 커밋은 3개다(2026-10-20). 작성자는 전부 박기택이고 Claude 표기는 없다.
  - `ae09c45` Initial commit
  - `2d54843` test: bench(Before 측정) + 단위 테스트
  - `f8d3de3` docs: workLog, 미션, 발표 원고
- `baseline` 태그도 push했다. GitHub에서 개선 전 코드 시점으로 바로 이동할 수 있다.
- 올리지 않은 것(로컬 전용): `.claude/`, `CLAUDE.md`, `doc/workClaude.md`, `doc/lessonstandard_k.md`(교안 정리본). 모두 `.git/info/exclude`에 들어 있다.
- 커밋할 때는 경로를 지정해서 add한다(`git add .` 대신). git_guard hook이 Claude 표기와 로컬 전용 파일 add를 막는다.

## 2026-10-21

### 1. GPT(Codex)가 만든 설정 복사본 삭제

- 아침에 GPT에 설정을 물어보다가 Codex용 복사본(`.agents/`, `.codex/`, `AGENTS.md`)이 생겼다.
- 어제 만든 `.claude/` 구성을 "Claude"를 "Codex"로 바꿔 복사한 것뿐이라 새 내용은 없었다. 일부 경로는 깨져 있었다(`.Codex/skills/...`).
- exclude에 들어 있지 않아서 업로드될 수 있는 상태였으므로 삭제했다. Claude 원본은 바뀐 것이 없다.
- 삭제 후 `pytest`: 15 passed, 1 xfailed

---

## 컴퓨터를 다시 켰을 때 (재시작 절차)

`.venv`, Ollama 모델, `.env`는 디스크에 남아 있다. 그래서 다시 설치할 필요는 없고, **프로세스만 다시 띄우면 된다.**

### 0) 프로젝트 폴더로 이동 + 가상환경 켜기 (모든 터미널 공통)

```bash
cd ~/subject/1020/all_total_vue_student
source .venv/bin/activate          # 프롬프트 앞에 (.venv)가 붙으면 성공
python -c "import fastapi, langgraph, mcp; print('venv OK')"
```
- `activate`를 쓰지 않으려면 명령마다 `./.venv/bin/python3`로 실행한다.
- `.venv`가 깨졌으면 `bash sh/setup_venv.sh`로 다시 만든다. 테스트까지 돌리려면 그다음 `./.venv/bin/python3 -m pip install -r requirements-dev.txt`도 실행한다.

### 1) 코드 상태 확인 (선택, 10초)

```bash
git status --short                 # 바뀐 파일 확인
./.venv/bin/python3 -m pytest tests -q   # 기대값: 15 passed, 1 xfailed
```

### 2-A) fake 모드로 띄우기 — 가장 빠름, 키·모델 불필요

```bash
# 터미널 1 — 백엔드 :8100
LANGCHAIN_TRACING_V2=false LLM_BACKEND=fake SUPERVISOR_VERSION=v2 ./.venv/bin/python3 server.py
# 터미널 2 — Vue 화면 :8600
./.venv/bin/python3 web_demo_server.py
```

### 2-B) Ollama 실모델로 띄우기 — bench 측정, 실제 답변 확인용

```bash
# Ollama가 켜져 있는지 확인 (응답이 없으면 Ollama 앱을 실행하거나 `ollama serve &`)
curl -s http://127.0.0.1:11434/api/tags >/dev/null && echo "ollama OK"
ollama list                        # qwen3:0.6b, qwen3:8b가 있어야 함

# 터미널 1 — 백엔드 (.env 로드 + 모델 웜업 + :8100)
bash sh/run_agent_ollma.sh
# 터미널 2 — Vue 화면 :8600
bash sh/run_frontend.sh
```
- ⚠️ `run_agent_ollma.sh`는 실행할 때마다 **`session.db`를 지운다.** 대화 이력을 남기려면 아래처럼 직접 띄운다.
  ```bash
  set -a; source .env; set +a; LLM_BACKEND=ollama ./.venv/bin/python3 server.py
  ```
- `run_agent_openai.sh`는 실제로 **과금**된다. 필요할 때만 쓴다.

### 3) 동작 확인

```bash
curl -s localhost:8100/health      # llm_backend, supervisor_version 확인
open http://localhost:8600         # 브라우저 채팅 화면
```

### 4) 종료

각 터미널에서 `Ctrl+C`를 누른다. 포트가 남아 있으면 아래로 정리한다.
```bash
lsof -ti:8100,8600 | xargs kill -9 2>/dev/null
```

### 5) Claude Code 작업 이어서 하기

```bash
cd ~/subject/1020/all_total_vue_student
claude --continue                  # 마지막 대화를 그대로 이어서 연다
```
- 이어서 연 뒤 "workLog 13번 워크스루 3단계부터 이어서 하자"라고 말하면 된다.
- 대화를 새로 시작해도 이 파일 13번 표와 `doc/guide.md`(#1~#12)를 보면 어디까지 했는지 알 수 있다.

---

## 다음에 할 작업

- [ ] **문제 1번(여러 시스템 중 1개만 조사)을 고치고 After를 측정한다**
  1. `/improve v1`을 실행해 개선안을 만들고, P1이 이 문제인지 확인한다.
  2. `agent/ollama_llm.py`의 `plan()`이 모델 task와 별개로 쿼리에 나온 KNOWN_SYSTEMS를 전부 research task로 보충하게 한다.
  3. 고치면 auto pytest hook이 자동으로 돈다. xfail이던 P1 테스트가 XPASS로 바뀌면 `@pytest.mark.xfail` 마커를 지운다(단위 테스트 C3-g, ⑦ 재발 방지).
  4. `/bench after`를 실행해 측정하고 `before.md`와 비교한다. q04~q06의 조사 시스템, q05의 db-down 오분류를 본다.
     - 주의: 여러 시스템의 alerts가 합쳐지면 규칙 순서 때문에 분류가 달라질 수 있다(예: q04 → cpu-spike).
  5. 결과를 `doc/presentation_k.md`의 `【After 측정 후 기입】` 칸에 채운다.
