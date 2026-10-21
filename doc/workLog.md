# 작업 로그 — all_total_vue (운영 인시던트 대응 에이전트)

## 📌 전체 요약 (2026-10-20 ~ 10-21) — 처음 보는 사람은 여기부터

| 단계 | 한 일 | 결과 / 문서 |
|---|---|---|
| 1. Before 측정 | 질문 10개 × 3회. 응답 성공률 0.97 | `bench/results/before.md` |
| 2. 측정 방법 변경 | 정답 세트(`eval_set.json`) 재채점 + LangSmith judge | **0.97 → 0.739**: 문제가 드러남 (`outputs/before/`) |
| 3. 문제 정의 | P1~P11, E15. 증거 캡처 S1~S13, C01~C13 | `outputs/final-report/01_problem_recognition.md` |
| 4. 단계별 수정 1~7 | 단계마다 커밋 1개 + 문서 1개(7단계 문제 해결 형식) | `outputs/final-report/03~09` |
| 5. After 측정 (Ollama) | 회귀(q10) 발견 → 보정 → 재측정 | 정답률 1.0, 36 → 12.8초 (`outputs/after/README.md`, `09b`) |
| 6. 실사용·탐색 스윕 | 새 문제 N1~N8 (6개 수정, 2개 한계) | `outputs/final-report/11_new_issues_N1_N8.md` |
| 7. OpenAI Before/After | 정답률 0.75 → 1.0, 대신 +1.2초·비용 2배. N9 발견·수정 | `outputs/openai/README.md` |
| 8. 정리 | 트레이드오프 총정리, 최종 발표, README | `12_tradeoffs_summary.md`, `10_final_presentation.md`, `README.md` |

- 테스트: 15 passed + 1 xfail → **70 passed**
- 결과 파일이 여러 회차라, 무엇이 최신인지는 README의 "측정 이력" 표를 본다.
- 코드에서 `[P1 BEFORE]` / `[P1 AFTER]`(N도 같은 형식)로 검색하면 바뀐 곳이 모두 나온다. 위치 목록: `outputs/final-report/00_code_index.md`

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

### 13. 파일별 워크스루 (완료 — 3~8단계는 10-21)

작업에 들어가기 전에 코드를 파일 단위로 같이 읽으면서, `doc/guide.md`의 문제 기록(#1~#12)이 실제 코드 어디에 있는지 확인하고 있다. 코드는 아직 수정하지 않았다.

| 단계 | 파일 | 관련 기록 | 상태 |
|---|---|---|---|
| 0 | 전체 폴더 구조와 요청 흐름 | — | ✅ |
| 1 | `server.py` | #3 #10 #12 | ✅ |
| 2 | `agent/deps.py` + `agent/graph.py` | #2 #3 #8 #9 #12 | ✅ |
| 3 | `agent/ollama_llm.py` (+ `openai_llm.py`는 다른 점만) | #1 #4 #5 | ✅ (10-21) |
| 4 | `agent/mcp_client.py` + `agent/retry.py` | #11 | ✅ (10-21) |
| 5 | `fake_llm.py` · `session_store.py` · `supervisor_v1.py` | #6 | ✅ (10-21) |
| 6 | `mcp_server.py` · `mcp_server_docs.py` | — | ✅ (10-21) |
| 7 | `web_demo_server.py` + `web_chat.html` | #3 #10 | ✅ (10-21) |
| 8 | `bench/run_baseline.py` + `queries.json` | #7 #12 | ✅ (10-21) |

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

### 2. 파일별 워크스루 3~4단계 (완료, 코드 수정 없음)

3단계 `agent/ollama_llm.py`:
- **#1 원인 확인**: `plan()`(171)은 research task가 0개일 때만 `_guess_targets()`로 전체 시스템을 복구한다(205). 모델이 task를 1개만 주면 복구가 일어나지 않는다. 어제 "추정"이던 원인이 코드로 확인됐다.
  - 추가로 찾은 것: 모델이 시스템명을 틀리면 `_guess_target()`이 첫 시스템 하나만 고르고(193), 나머지는 중복으로 버려진다.
  - 고칠 방향: 반복문 뒤에 쿼리에 나온 KNOWN_SYSTEMS 중 `seen`에 없는 것을 항상 보충한다. auth-service 기본값은 보충 대상에서 뺀다.
- **analysis 남발**: `route()`(156)와 `plan()`(178) 프롬프트가 둘 다 모델에게 `needs_analysis`를 정하게 한다. plan은 analysis task 추가도 허용한다. 213줄은 그 값을 그대로 반환한다.
- **#4 원인 확인**: `_chat()`은 동기 `httpx.post`(104)다. 이걸 `async` 노드에서 바로 부른다(`graph.py:78` route, `:113` plan, `:243` analyze). 그래서 LLM을 기다리는 동안 이벤트 루프 전체가 멈춘다. 답변 스트림용 `_chat_stream()`은 AsyncClient라 문제없다.
- **#5**: httpx `timeout=300.0`(104, 132)이 q01 실패 시간 300초와 같다. 어느 단계에서 걸렸는지는 기록이 없어 여전히 모른다(#12가 선행).
- `openai_llm.py`: `plan()` 정규화 로직이 그대로 복사돼 있다(156, 168-174). #1을 고칠 때 두 파일 모두 고치거나 공통 함수로 뺀다.

4단계 `agent/mcp_client.py` + `agent/retry.py`:
- guide.md #11의 ③ 내용이 코드와 일치한다.
  - `ClientSession`에 timeout이 없다(60).
  - 일부러 던지는 가짜 TimeoutError는 74줄 한 곳뿐이다.
  - `read_resource`에는 재시도가 없다(`graph.py:168`).
- **#11 "아직 확인하지 못한 것" 해결**: `.venv`의 mcp SDK는 `read_timeout_seconds`를 넘으면 `MCPError(code=REQUEST_TIMEOUT=-32001)`을 낸다(`mcp/shared/jsonrpc_dispatcher.py:442`). `asyncio.TimeoutError`가 아니다.
  - 그래서 timeout만 추가하면 `with_retry`가 재시도하지 않는다. `with_retry`의 except 조건도 함께 바꿔야 한다.
- 새로 확인한 것: `MCPClient`는 Lock 하나(`self._lock`)로 모든 서버 호출을 직렬화한다. 그래서 research의 `asyncio.gather`도 MCP 호출 부분은 실제로 하나씩 실행된다. #12에서 시간을 잴 때 함께 본다.

5단계 `fake_llm.py` · `session_store.py` · `supervisor_v1.py`:
- `fake_llm.py`는 시연용으로 일부러 "틀리게" 만든 모델이다.
  - `plan()`은 항상 web-01과 analysis task를 끼워 넣는다. gate 시연용이다.
  - `write()`는 1차 초안을 항상 "재시작하면 됩니다."로 내서 validate 반려를 일으킨다.
  - 그래서 #1·#2 같은 실모델 버그는 fake 모드에서 재현되지 않는다. 수치 비교는 Ollama bench로만 한다.
  - 시스템명을 찾는 방식도 다르다. fake는 정규식, Ollama는 KNOWN_SYSTEMS를 쓴다.
- `session_store.py`
  - 동기 sqlite3를 async 핸들러에서 호출한다(guide P15, 영향 작음).
  - `thread_id` 인덱스가 없다.
  - `load()`는 이력을 전부 읽는다. 단, Ollama `chat()`은 그중 최근 10개만 쓴다(`ollama_llm.py:232`).
- `supervisor_v1.py`
  - 조사 대상이 auth-service로 고정돼 있다(P14).
  - 장애 경로로 들어가는 조건이 chat 답변에 "도와드릴까요"라는 글자가 있는지다. fake의 답변 문구에 맞춘 조건이라 Ollama/OpenAI 모드에서는 v1 장애 진단이 거의 실행되지 않는다(추정, 미측정).
  - v1은 v2에 문제가 생겼을 때 돌아가는 롤백 경로인데, 실모델에서는 롤백으로 쓰기 어렵다.
- **guide.md #6 갱신 필요(재확인)**
  - ①의 "tests/ 없음, pytest 없음"은 지난 상태다.
  - ③의 "아직 확인하지 못한 것(@traceable)"은 해결됐다. `tests/conftest.py`가 tracing을 끄고, 키 없이 15 passed가 나온다.
  - 남은 것: research 실패 격리 테스트, 스트림 경로 테스트, v1 경로 테스트.

6단계 `mcp_server.py` · `mcp_server_docs.py` (+ `data/`):
- **#1의 원인이 하나 더 있을 수 있다(가설)**: 표준 절차 MCP Prompt는 `system_name`을 1개만 받는다(`mcp_server.py:66`).
  - graph는 여기에 `_extract_system_name()`이 고른 쿼리의 첫 시스템만 넣는다(`graph.py:110`).
  - 그래서 plan 프롬프트의 "## 표준 절차"에는 "시스템: web-01" 한 줄만 들어간다. 모델이 그 시스템 하나만 계획할 가능성이 있다.
  - q05("web-01 CPU 급증, auth-service 커넥션 풀도…")가 정확히 이 경로로 web-01만 조사했고 db-down으로 오분류됐다. #1·#2가 같은 뿌리일 수 있다.
  - 확인 방법: LangSmith의 `ollama_fast.plan` run 입력과 출력.
- **db-down 폴백 구조**: `data/monitoring.json`에는 DB 시스템도, status=down인 시스템도 없다. 그런데 분류 규칙이 하나도 맞지 않으면 `db-down` runbook을 붙인다(`graph.py:213`).
  - 그래서 정상(healthy, 알림 없음) 시스템만 조사하면 항상 "DB 다운 대응 절차"가 나온다.
  - "이상 없음"으로 처리하는 경로가 없다.
- 없는 시스템을 조회하면 status=`unknown`과 "not found" 알림을 돌려준다. 이 경우도 규칙에 맞지 않아 db-down으로 간다.
- 모니터링 값에 매번 random jitter(-3~+8)가 섞인다(`mcp_server.py:46`). 반복 측정할 때 CPU 수치가 달라지는 이유다. 분류는 alerts 문구로 하므로 영향이 없다.
- 쿼리에서 시스템명을 찾는 함수가 3벌이다: `graph._extract_system_name`, `ollama_llm._guess_target`, `openai_llm._guess_target`. 같은 로직이다(guide #6 "헬퍼 중복").
- `mcp_server_docs.py`는 agent가 쓰지 않는 decoy 서버다. "어느 서버가 resource를 가졌는지 먼저 조회한다"는 시연용이다. 문제 없음.

### 3. 핵심 고장 지점 실증 (코드 수정 없음)

워크스루에서 짚은 고장 지점을 두 가지로 확인했다. 재현 스크립트는 스크래치 폴더에만 두었고 프로젝트에는 넣지 않았다.
- Before 측정 기록(`bench/results/baseline_raw.jsonl`)
- 오프라인 재현 스크립트: Ollama 없이 모델 출력을 고정해서 실제 코드를 실행했다.

| # | 고장 지점 | 증거 | 결과 |
|---|---|---|---|
| #1 | `plan()`이 쿼리 속 시스템을 보충하지 않음 | baseline q04~q06 9회 전부 | `plan_targets`가 쿼리의 **첫 시스템 1개**뿐이다(gateway / web-01 / payments). 모든 회차가 `PlanCreated task_count=2`(research 1 + analysis 1)라서 복구 조건(`if not seen`)에 걸리지 않았다 |
| #1 | 같은 원인 | 재현: 모델이 web-01 task 1개만 반환 | 조사 대상 `['web-01']` |
| #1 | target 오타 처리 | 재현: `web01`, `auth_service` 반환 | 조사 대상 `['web-01']`. 오타 2개가 첫 시스템 1개로 합쳐진다 |
| #1 | 표준 절차 프롬프트 | 재현: q05의 실제 MCP Prompt | `시스템: web-01` 한 줄만 들어간다. 모델이 이 때문에 하나만 고르는지는 LangSmith로 확인해야 한다(가설 유지) |
| #2 | db-down 폴백 | baseline q05 3회 + 재현 | healthy web-01 → `db-down`, 없는 시스템(unknown) → `db-down` |
| 분석 남발 | gate가 모델 값을 그대로 믿음 | baseline q04~q06 9회 | 모든 회차에서 analysis task 생성, `gate_removed=0`, `analysis_ran=true` |
| #4 | 동기 LLM 호출 | 재현: 모델 응답 2초 가정 | `route_node`가 도는 2초 동안 다른 작업 tick이 **1회**(정상이면 약 20회). 이벤트 루프가 멈춘다 |
| #11 | MCP timeout 예외 타입 | 재현: 5초 걸리는 tool + timeout 1초 | `mcp.shared.exceptions.MCPError: Request 'tools/call' timed out`. `asyncio.TimeoutError`가 아니어서 `with_retry`는 **1회만 시도**하고 바로 실패한다 |
| v1 | 롤백 경로 | 재현: chat 답변에 "도와드릴까요"가 없을 때 | 모니터링 조회를 하지 않고 chat 답변을 그대로 반환한다. 실모델 롤백 경로로 쓸 수 없다 |

### 4. 워크스루 7단계 — `web_demo_server.py` + `web_chat.html` (완료, 코드 수정 없음)

fake 백엔드와 임시 session DB로 `/chat/stream`을 직접 호출해 확인했다(FastAPI TestClient). 프로젝트의 `session.db`는 바뀌지 않았다.

| 항목 | 결과 | 관련 |
|---|---|---|
| 처리 중 예외 | 스트림이 예외로 끊긴다. `[DONE]`도 오류 이벤트도 내려가지 않는다. 화면은 `es.onerror`에서 조용히 입력창만 복구한다(`web_chat.html`) | #3 확인 |
| 예외 난 턴의 이력 | 0건. 사용자 메시지도 저장되지 않는다 | #10 확인 |
| 빈 메시지 | 200으로 그대로 처리된다(기대값은 422) | #10 확인 |
| SSE 헤더 | `Cache-Control`, `X-Accel-Buffering` 둘 다 없다 | #10 확인 |
| **v1 + 스트림 이력** | **정상 완료해도 0건 저장(새로 발견).** `server.py`의 `/chat/stream` v1 분기에 `session_store.append`가 없다. `/chat`은 v1도 저장한다 | #10에 추가 |

그 밖에:
- `web_demo_server.py`
  - 스트림 중계가 `timeout=None`이다. 백엔드가 멈추면 브라우저도 끝없이 기다린다.
  - `/health` 중계는 백엔드가 꺼져 있으면 500이 난다. 프런트가 catch하므로 라벨만 안 바뀐다.
- `web_chat.html`
  - Vue CDN 주소가 `vue@3`이라 버전이 고정돼 있지 않다.
  - 헤더 라벨은 fake 모드에서도 "실모델"이라고 표시한다.

### 5. 워크스루 8단계 — `bench/run_baseline.py` + `queries.json` (완료)

- #7 확인
  - `ok = status == 200 and err is None`(120)이라서, 응답만 오면 성공으로 센다.
  - `queries.json`의 `expected_incident_type`이 10건 모두 빈칸이다. 기대 조사 시스템 필드도 없다.
  - 다만 raw에 `monitored_systems`, `incident_type`이 남아 있어서, 기대값만 채우면 **baseline을 다시 측정하지 않고도** 정답률을 다시 계산할 수 있다.
- #5/#12
  - bench 클라이언트의 `TIMEOUT = 300.0`(26)과 서버의 LLM httpx timeout 300초가 같다.
  - q01의 `ReadTimeout`은 **클라이언트 쪽**에서 끊긴 것이다. 서버가 어느 단계에서 멈췄는지는 기록이 없다.

### 6. Before 증거 수집 (코드 수정 전 전처리, 완료)

- 산출물: `outputs/before/`
  - 화면 4장, 코드 13장, 터미널 11장, 원본 텍스트 증거, 재현 스크립트
  - `README.md`: 문제 → 증거 → 교안 기준 개선안 표
  - 묶음: `outputs/before/before_evidence.zip`
- 실행 조건: ollama, `qwen3:0.6b`/`qwen3:8b`, v2(S9만 v1). 에이전트 코드는 `baseline` 태그와 같다.
- 정확도 측정 구축(미션 C4 "검색 정확도", 교안 K15)
  - 정답 세트 `bench/eval_set.json`. `queries.json`은 수정하지 않았다.
  - `bench/rescore.py`: 이미 측정한 raw를 다시 채점한다.
  - `bench/eval_langsmith.py`: LangSmith Dataset + `evaluate()`. heuristic과 LLM-judge(Ollama qwen3:8b, 무료)를 섞었다.
  - Before 결과: runbook 정답률 0.739 / 0.75, 조사 범위 recall 0.775 / 0.786, judge 0.855. LangSmith 실험명은 `baseline-36e5189f`다.
- 새로 확정된 것
  - **#5 원인**: q01 300초 실패는 `ollama_fast.analyze`의 300초 `ReadTimeout`이다(P3+P4+P6+P9).
  - q03 편차는 write 토큰 수에 비례한다(1,863 → 3,537). qwen3 thinking 토큰으로 추정한다.
  - P4 실측: q05 처리 중 `/health` 지연은 최대 1.73초다.
  - `/chat`도 빈 메시지를 200으로 받는다.
  - Ollama를 끄면 화면이 오류 표시 없이 멈춘다(S6).
  - v1은 장애 질문에 모니터링을 조회하지 않는다(S9).
- 직접 다시 실행하는 명령은 `doc/guide.md` 맨 끝 절에 정리했다.
- 캡처 방식: macOS `screencapture`는 화면 기록 권한이 없어 실패했다. 그래서 Playwright(스크래치 가상환경)로 설치된 Chrome을 조종해 캡처했다.

---

## 2026-10-21 (저녁) — 전체 개선 1~7단계 + After 측정

| 단계 | 커밋 | 내용 | 문서 |
|---|---|---|---|
| 0 | `14b218b` | 16:11에 다시 돌린 baseline은 `baseline_rerun1021_*`로 따로 보관하고 원본(0.97)을 복원했다 | — |
| 1 | `0a21f3d` | P1 + #14: `agent/systems.py`, 질문의 시스템을 항상 보충. **실모델 확인: 0.6b가 target에 문장을 넣는 것이 원인**(추정 → 확정) | `outputs/final-report/03_step1_P1.md` |
| 2 | `6e53fd3` | P2: 이상 시스템 우선 분류, db-down 폴백 제거, 감시 대상이 아니면 조사 안 함 | `04_step2_P2.md` |
| 3 | `061ed1b` | P3·P4·P9: AsyncClient, 이중 게이트, 단계별 timeout, think:false(토큰 190 → 9 실측), 노드별 elapsed_ms | `05_step3_P3_P4_P9.md` |
| 4 | `82a08af` | P5·P6: MCP `_call`(timeout + 예외 번역), task 격리, SSE Error 이벤트, 빨간 말풍선 | `06_step4_P5_P6.md` |
| 5 | `f83b27e` | P7: Pydantic 계약 → 422, SSE 헤더, 질문 선저장, v1 이력 | `07_step5_P7.md` |
| 6 | `f3b541d` | P11: 규칙 3개 + LLM judge(0.6b vs 8b 실험 후 8b 채택), 재작성 1회 | `08_step6_P11.md` |
| 7 | `1f8e51d` | E15 비동기 세션 저장소 + 팩토리, P10 v1 롤백(기준 외) | `09_step7_E15_P10.md` |
| 8 | `83125f4` | After 1차 측정에서 q10 라우팅 회귀 발견(think 끔 부작용) → route 권위 보정 → 2차 측정 | `09b_step8_route_regression.md` |

**After 결과 (2차, `outputs/after/README.md`)**

| 지표 | Before | After |
|---|---|---|
| runbook 정답률 | 0.739 | 1.0 |
| recall | 0.775 | 1.0 |
| LLM-judge | 0.855 | 0.955 |
| incident 중앙값 | 36.0초 | 12.8초 |
| 최대 응답 | 300초 | 24.4초 |
| 비용 | $0.1637 | $0.1360 |

- pytest: 15 passed + 1 xfailed → **57 passed**
- 나빠진 것: q04 judge 0.95 → 0.75. q02는 재작성 때문에 22.9초다.
- 캡처: `outputs/after/captures/`(Before와 같은 파일명), 묶음 `outputs/after/after_evidence.zip`
- 최종 발표: `outputs/final-report/10_final_presentation.md`
- 코드 위치 색인: `outputs/final-report/00_code_index.md`
- 코드에서 `[Px BEFORE]`(주석 처리한 원래 코드)와 `[Px AFTER]`(고친 코드)로 검색하면 바뀐 곳이 모두 나온다.

## 2026-10-21 (밤) — 새로 발견된 문제 N1~N8

- **계기**: 화면에서 "장애 질문 → 제 이름은 민수입니다"를 보내자 이전 장애 보고서가 다시 나왔다. 측정 질문 10개는 매번 새 대화라 이 순서를 시험하지 않았다.
- **탐색 스윕**: `outputs/after/scripts/explore_sweep.py`로 12개 상황을 실제 서버에 보냈다. 결과는 `outputs/after/evidence/N_sweep_before_fix.txt`.
- 고친 것:
  - N1 chat 이력에서 장애 보고서 제외
  - N2 별칭(결제 → payments)
  - N3 대소문자
  - N4 증상 단어 확대 (P9 후속 보정의 부작용)
  - N5 route 양방향 보정 ("web-01 상태 괜찮아?"에 지어낸 답)
  - N6 질문에 없는 시스템은 조사하지 않음
- 남긴 한계:
  - N7 동시 요청 (Ollama가 순서대로 처리)
  - N8 장애 직후 후속 질문의 문맥 상실 (N1 수정의 대가)
- 검증:
  - pytest 57 → **69 passed**
  - 스윕 결과: `N_sweep_after_fix.txt`
  - 기존 10개 질문 회귀 확인 `bench/results/after_n_*`: 정답률 1.0, incident 중앙값 12.5초
- 문서: `outputs/final-report/11_new_issues_N1_N8.md`
- 측정 이력(무엇이 최신인지)은 README의 "측정 이력" 표에 정리했다.

## 2026-10-21 (밤 2) — OpenAI(과금) 환경 Before/After

- Before는 `git worktree`로 `before-evidence` 코드를 꺼내 OpenAI로 실행했다. After는 현재 코드다. 질의셋과 채점은 Ollama 측정과 같다.
- 결과 (`outputs/openai/README.md`):

  | 지표 | Before | After |
  |---|---|---|
  | runbook 정답률 | 0.75 | 1.0 |
  | judge | 0.835 | 0.96 |
  | 응답 중앙값 | 5.3초 | 6.5초 |
  | 가상 비용 | $0.074 | $0.147 |

  - gpt-4o-mini는 P1이 없었다.
  - 대신 q04에서 P2 규칙 순서 문제(cpu-spike 오분류)가 드러났다.
- **N9 발견**: After 1차에서 gpt-4o judge가 runbook에 있는 조치를 4건 오반려했다.
  - 원인: `_facts_text`가 runbook 제목만 넘겼다.
  - 수정 후 오반려 0건. pytest 70 passed.
- 캡처: `outputs/openai/{before,after}/captures/` S1~S4. 캡처 스크립트는 백엔드에 상관없이 동작하는 복사본 `outputs/openai/scripts/ui_capture_any.py`를 썼다.
- 측정 후 서버는 Ollama(v2)로 되돌렸다.

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
- 이어서 연 뒤 "workLog 13번 workLog 10-21 5번 수정 순서대로 이어서 하자"라고 말하면 된다.
- 대화를 새로 시작해도 이 파일 13번 표와 `doc/guide.md`(#1~#12)를 보면 어디까지 했는지 알 수 있다.

---

## 다음에 할 작업

- [x] 문제 1~11 개선 + After 측정 (2026-10-21 저녁)
- [x] 새로 발견된 문제 N1~N6, N9 수정 + OpenAI Before/After (2026-10-21 밤)
- [ ] 발표 리허설: `01_problem_recognition.md` → `10_final_presentation.md` 순서로 5분 (트레이드오프는 `12_tradeoffs_summary.md`)
- [ ] 정답 세트 확장: 대화 섞기, 시스템 이름 변형, 상태 질문 (N1~N6 시나리오를 `eval_set.json`에)
- [ ] (선택) N8 후속 질문 문맥, `JUDGE_LLM=fast_llm`으로 OpenAI 비용 측정
