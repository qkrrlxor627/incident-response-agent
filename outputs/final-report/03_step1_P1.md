# 1단계 — P1 여러 시스템을 물어도 1개만 조사 (+ #14 공통 로직 중복)

| 항목 | 내용 |
|---|---|
| 수준 | L3 (7단계 전부 + 기록) |
| 매핑 | C3-a·C3-b·C3-f / K6(권위 정규화)·K7·K3(MCP Prompt)·K14(모듈화) |
| 사용자 문제 목록 | #1 다중 시스템 조사 누락, #14 공통 로직 중복 |
| 커밋 | `git log --oneline -- outputs/final-report/03_step1_P1.md` 맨 위 줄 |

## ① 인식
q05 "web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘"에 web-01만 조사했다(S1 화면).

## ② 정의 (3문장)
- **기대**: 질문에 나온 시스템을 모두 조사한다.
- **실제**: q04·q05·q06은 3회 반복 9/9건 모두 첫 번째 시스템만 조사했다. recall은 0.5다(`bench/results/baseline_accuracy.csv` 11~19줄).
- **증거**:
  - plan 입력의 표준 절차에 `- 시스템: web-01` 한 줄만 들어간다(`outputs/before/evidence/S3_q05_plan_trace.txt` 8줄).
  - 코드 보정은 research가 0개일 때만 동작했다(Before `agent/ollama_llm.py:205`).

## ③ 원인 분석
| 위치 (Before, tag `before-evidence`) | 하는 일 | 문제 |
|---|---|---|
| `agent/graph.py:40-47` `_extract_system_name` | MCP Prompt에 넘길 시스템명 | 첫 시스템 **1개만** 넘긴다 |
| `agent/ollama_llm.py:193` | 목록에 없는 target 처리 | **질문의 첫 시스템으로 바꿔 버린다** → 중복으로 제거된다 |
| `agent/ollama_llm.py:205` | 누락 보충 | research가 **0개일 때만** 보충한다 |
| `agent/ollama_llm.py:54` `_guess_targets` | 복구 목록 | `sorted()`로 언급 순서를 잃는다 |

**이번 단계에서 확정한 것 (Before 때는 추정이었음)**: 실모델 qwen3:0.6b는 target에 시스템 이름 대신 문장을 넣는다.

```
"target": "get_monitoring_status Tool for web-01"
"target": "gateway-service monitoring status"
```

이 값이 목록에 없으니 193줄이 "질문의 첫 시스템"으로 바꾸고, 두 번째 research도 같은 첫 시스템으로 바뀌어 중복으로 제거된다.
→ 결과: 시스템 1개만 남는다(원인 분석 때의 stub 실험 경우 C). 증거: `outputs/after/evidence/P1_real_model_plan.txt`

## ④ 가설과 대안
가설: 모델 출력과 상관없이 **질문에 나온 시스템을 코드가 항상 보충**하면 9/9 누락이 사라진다.

| 대안 | 내용 | 장점 | 단점 | 선택 |
|---|---|---|---|---|
| A. 프롬프트 개선 | "시스템마다 task를 만들어라"를 더 강하게 쓴다 | 코드 변경이 적다 | 0.6b 모델은 이미 이 지시를 무시했다. 보장되지 않는다 | ✗ |
| B. 더 큰 모델로 plan | qwen3:8b로 계획한다 | 출력 품질이 오른다 | 지연과 비용이 늘고, 그래도 보장되지 않는다 | ✗ |
| **C. 코드 권위 정규화** | 질문의 KNOWN_SYSTEMS를 항상 보충하고, 모르는 target은 버린다 | 결정론이고 테스트할 수 있다. K6 원칙과 같다 | 질문에 이름이 없는 시스템은 모델이 찾아도 버려질 수 있다 | ✅ |

선택 이유: 교안 K6(모델 출력을 믿지 않고 코드가 보정)과 K7(gate)과 같은 설계 원칙이다. 실측으로 확인할 수 있는 결정은 코드가 내린다.

## ⑤ 실행 (바꾼 코드)
| 파일:줄 | 변경 |
|---|---|
| `agent/systems.py` (새 파일) | `KNOWN_SYSTEMS`(30), `mentioned_systems`(36, **언급 순서 유지**), `unmonitored_systems`(45), `research_targets`(58), `primary_system`(70). 45·58은 2단계(P2)에서 쓴다 |
| `agent/graph.py:25-44` | 중복 로직과 Before `_extract_system_name`을 주석으로 남기고, 공통 모듈을 import한다 |
| `agent/graph.py:47` | `_extract_system_name`이 `"web-01, auth-service"`처럼 **전부** 넘긴다 |
| `agent/ollama_llm.py:23-58` | 중복 로직 Before 주석 + import |
| `agent/ollama_llm.py:202` | 목록에 없는 target은 버린다(Before: 첫 시스템으로 바꿈) |
| `agent/ollama_llm.py:227-235` | **항상** 보충한다. 순서는 질문 언급 순서가 먼저다 |
| `agent/openai_llm.py:165`, `190-198` | 같은 수정(백엔드 간 동작을 맞춤) |

코드에서 `[P1 BEFORE]` / `[P1 AFTER]` / `[#14 ...]`로 검색하면 바뀐 곳이 모두 나온다.

## ⑥ 검증
| 방법 | 결과 |
|---|---|
| pytest | 21 passed (Before 15 passed, 1 xfailed) |
| P1 재현 테스트 | xfail 마커를 지웠고 통과한다 |
| 실모델 plan 3건 (q05·q04·q06) | 모두 2개 시스템을 언급 순서대로 조사한다 (`outputs/after/evidence/P1_real_model_plan.txt`) |
| fake 서버 `/chat` | `PlanCreated targets: ['web-01', 'auth-service']`, TaskCompleted 2건 |
| 전체 30건 After 측정 | 8단계에서 측정한다 → `outputs/after/README.md` |

## ⑦ 재발 방지 (테스트)
- `tests/test_agent_units.py`
  - `test_plan_recovers_every_system_in_mention_order`: 원인 분석 때의 stub 실험 A~D 4경우를 그대로 고정했다
  - `test_mentioned_systems_keeps_mention_order`
  - `test_extract_system_name_passes_every_mentioned_system`
  - `test_plan_keeps_default_system_when_nothing_mentioned`

## 트레이드오프
- 질문에 이름이 없는 시스템(예: "결제 서버")은 보충되지 않는다. 별칭 사전이 필요하다 → 한계로 남긴다.
- 모델이 질문에 없는 시스템을 정확히 골라도 그대로 둔다(추가 조사). 다만 모델이 낸 문장형 target은 버려진다.
- MCP Prompt의 `system_name` 타입을 list로 바꾸지 않고 쉼표 문자열로 넘긴다. 서버 호환을 위한 선택이다.

---

## 직접 확인하는 방법 (수동)
**1. 바뀐 코드 보기**
```bash
git log --oneline -3
git show --stat HEAD                                  # 이 단계에서 바뀐 파일 목록
git diff before-evidence -- agent/graph.py agent/ollama_llm.py agent/systems.py
grep -n "P1 BEFORE\|P1 AFTER\|#14" agent/*.py        # 주석으로 남긴 Before/After 위치
```

**2. 단위 테스트**
```bash
./.venv/bin/python3 -m pytest tests -q -k "plan or mentioned or extract"
```
- 이 명령은 `tests/conftest.py`(import 경로와 LangSmith 끄기) → `tests/test_agent_units.py`의 함수들을 실행한다.
- `test_plan_recovers_...`는 `OllamaFastLLM._chat`을 가짜 함수로 바꾸고(monkeypatch), `plan()`의 정규화 코드(`agent/ollama_llm.py:186-238`)만 실행한다. Ollama를 부르지 않는다.

**3. 실모델 plan만 따로 돌려 보기** (Ollama가 떠 있어야 함, 서버는 필요 없음)
```bash
LANGCHAIN_TRACING_V2=false ./.venv/bin/python3 -c "
from agent.ollama_llm import OllamaFastLLM
r,_ = OllamaFastLLM('qwen3:0.6b', 0).plan('web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘', '절차')
print([t['target'] for t in r['tasks'] if t['agent']=='research'])"
```
- 기대 출력: `['web-01', 'auth-service']`

**4. 화면에서 보기**
1. 서버를 다시 시작한다. 터미널 2에서 Ctrl+C를 누른 뒤 `bash sh/run_agent_ollma.sh`를 실행한다. 터미널 3은 그대로 둔다.
2. http://localhost:8600 에서 `web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘`를 입력한다.
3. 성공하면 진행 단계에 **"모니터링 조회: web-01"과 "모니터링 조회: auth-service" 2줄**이 나온다. Before(S1)는 web-01 1줄이었다.
4. 이 단계에서는 runbook이 아직 db-down일 수 있다. 이것은 2단계(P2)에서 고친다.

## 커밋 보고 7항목
1. **커밋**: 이 문서와 같은 커밋(위 표)
2. **Before 증거**:
   - `outputs/before/captures/S1_q05_multi_system_db_down.png`, `S2_q06_only_one_system.png`
   - `terminal/S3_q05_plan_trace.png`
   - `code/C01`, `code/C02`
3. **After 캡처와 비교**: 8단계에서 같은 파일명으로 `outputs/after/captures/S1_...png`, `S2_...png`를 찍는다. 나란히 놓고 "모니터링 조회" 줄 수를 비교한다.
4. **선택한 대안**: C 코드 권위 정규화. 이유는 K6 원칙과 결정론이다.
5. **트레이드오프**: 위 절
6. **핵심 변경**: `agent/systems.py:36`, `agent/ollama_llm.py:202`, `agent/ollama_llm.py:227-235`, `agent/graph.py:47`
7. **화면**: 위 "4. 화면에서 보기"
