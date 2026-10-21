# 2단계 — P2 맞는 규칙이 없으면 무조건 db-down (장애 유형 오분류)

| 항목 | 내용 |
|---|---|
| 수준 | L2 (정의 → 원인 → 가설 → 실험 → 검증) |
| 매핑 | C3-c / K8(근거 기반 판단) |
| 사용자 문제 목록 | #2 장애 유형 오분류 |
| 커밋 | `git log --oneline -- outputs/final-report/04_step2_P2.md` 맨 위 줄 |

## ② 정의
- **기대**: 증상에 맞는 runbook을 고른다. 이상이 없거나 감시 대상이 아니면 runbook을 붙이지 않고 그 사실을 답한다.
- **실제**:
  - q05(web-01 CPU 급증 + auth-service 커넥션 풀)에 **db-down** runbook이 붙었다(3/3).
  - q08(감시하지 않는 billing-service)은 auth-service를 대신 조사해 high-latency를 붙였다(3/3, judge 0.25).
- **증거**:
  - `bench/results/baseline_accuracy.csv` q05·q08 `type_ok=False`
  - `outputs/before/evidence/S13_*.txt` 9줄, 12줄

## ③ 원인
| 위치 (Before) | 문제 |
|---|---|
| `agent/graph.py:205-213` `_classify_incident_type` | 모든 시스템의 알림을 **한 문자열로 합친 뒤** 규칙을 검사한다. 아무것도 안 걸리면 `return "db-down"`이다 |
| q05의 실제 흐름 | P1 때문에 web-01(정상, 알림 0개)만 조사했다 → 합친 문자열이 `"healthy "` → 규칙에 안 걸림 → **db-down** |
| q08의 실제 흐름 | 시스템 이름이 목록에 없다 → 기본값 auth-service를 조사했다 → latency → high-latency |

P1을 고친 뒤에도 남는 위험: 두 시스템의 알림을 합치면 규칙 목록의 **앞쪽 키워드**가 이긴다. 주 시스템의 증상이 아니라 규칙 순서가 결과를 정한다.

## ④ 가설과 대안
가설: 시스템을 하나씩 질문 언급 순서대로 보고, 정상 시스템은 건너뛰고, 근거가 없으면 runbook을 붙이지 않으면 q05·q08이 맞는다.

| 대안 | 장점 | 단점 | 선택 |
|---|---|---|---|
| A. 폴백만 `None`으로 바꾼다 | 1줄 수정 | 합친 문자열 때문에 규칙 순서 문제가 남는다 | ✗ |
| B. LLM에게 runbook을 고르게 한다 | 유연하다 | 0.6b 모델 출력이 흔들린다. 검증할 수 없다(K6 원칙 위반) | ✗ |
| **C. 주 시스템 우선 + 정상 건너뛰기 + 근거 없으면 None** | 결정론이고 테스트할 수 있다. 데이터로 설명할 수 있다 | 키워드 규칙에 없는 증상은 None이 된다 | ✅ |

## ⑤ 실행
| 파일:줄 | 변경 |
|---|---|
| `agent/graph.py:212-222` | Before 분류 함수를 주석으로 남겼다 |
| `agent/graph.py:225-245` | 이상이 있는 시스템 중 먼저 나온 시스템의 알림만으로 분류한다. 없으면 `None` |
| `agent/graph.py:248` `_no_runbook_note` | runbook을 붙이지 않은 이유를 사실로 남긴다("감시 대상 아님" / "모두 정상") |
| `agent/graph.py:268-275` | `None`이면 gap task(runbook 조회)를 만들지 않는다 |
| `agent/ollama_llm.py:231-234`, `agent/openai_llm.py:194-197` | 감시 대상이 아닌 시스템만 나오면 조사하지 않는다(엉뚱한 auth-service를 조사하지 않음) |
| `agent/ollama_llm.py:284`, `openai_llm.py:257`, `fake_llm.py:113` | write 단계가 `note`를 사실로 받는다 |
| `agent/systems.py:45` `unmonitored_systems` | 시스템 이름처럼 생겼지만 목록에 없는 이름을 찾는다 |

## ⑥ 검증
| 방법 | 결과 |
|---|---|
| pytest | 24 passed |
| 실모델 q05 | 조사 `web-01, auth-service` → **high-latency** runbook (Before db-down) |
| 실모델 q08 | 조사 0개, runbook 없음. 답변: "billing-service는 모니터링 대상에 등록되지 않아 상태 조회가 불가능합니다" |
| 증거 파일 | `outputs/after/evidence/P2_real_q05_q08.txt` |
| 전체 30건 | 8단계 After 측정(`type_ok`)에서 확인한다 |

q08에서 비교 분석(`AnalysisCompleted`)이 아직 실행된다. 조사한 시스템이 0개인데도 실행되는 것은 P3 문제이고, 3단계에서 고친다.

## ⑦ 재발 방지 (테스트)
- `test_classify_returns_none_when_every_system_is_healthy`: Before는 db-down
- `test_classify_uses_first_abnormal_system_in_mention_order`: Before 테스트는 "규칙 순서가 이긴다"를 고정했었다. 의도된 동작이 바뀐 것이다
- `test_classify_q05_skips_healthy_primary_system`
- `test_replan_check_adds_no_runbook_when_nothing_is_wrong`
- `test_plan_skips_unmonitored_system`

## 트레이드오프
- 키워드 규칙(`_INCIDENT_TYPE_RULES`)에 없는 증상이면 runbook이 없다. 틀린 runbook보다는 낫다고 판단했다. 규칙 확장은 한계로 남긴다.
- 주 시스템을 "먼저 언급된 이상 시스템"으로 정의했다. 사용자가 원인 시스템을 뒤에 말하면 다른 runbook이 나올 수 있다.
- `db-down` runbook은 이제 status가 `down`인 시스템에서만 선택된다. 현재 데이터에는 down 시스템이 없다.

---

## 직접 확인하는 방법 (수동)
```bash
git show HEAD -- agent/graph.py | less                 # 분류 함수 Before(주석) / After
grep -n "P2 BEFORE\|P2 AFTER" agent/*.py
./.venv/bin/python3 -m pytest tests -q -k "classify or replan or unmonitored"
```

분류 함수만 직접 실행해 보기(서버와 LLM이 필요 없다):
```bash
./.venv/bin/python3 -c "
from agent.graph import _classify_incident_type as f
web = {'source':'monitoring','data':{'status':'healthy','alerts':[]}}
auth = {'source':'monitoring','data':{'status':'degraded','alerts':['p95 latency 2.4s','connection pool 92% used']}}
print('q05 →', f([web, auth]))   # high-latency (Before: db-down)
print('정상만 →', f([web]))      # None (Before: db-down)"
```

**화면** (서버를 재시작한 뒤 :8600)
- `web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘` → 진행 단계에 **"매뉴얼: high-latency"**가 나오면 성공이다(Before S1: db-down).
- `billing-service 응답이 느려요` → 모니터링 조회 단계가 없고, 답변에 "모니터링 대상에 없다"는 문장이 나오면 성공이다.

## 커밋 보고 7항목
1. **커밋**: 위 표
2. **Before 증거**: `outputs/before/captures/S1_q05_multi_system_db_down.png`, `code/C03_P2_db_down_fallback.png`, `evidence/S13`(q05 0.6, q08 0.25)
3. **After 비교**: 8단계 `outputs/after/captures/S1_...png`의 "매뉴얼" 줄을 본다. `after_accuracy.csv`의 q05·q08 `type_ok`를 Before와 비교한다.
4. **선택**: C. K8 근거 기반, 결정론
5. **트레이드오프**: 위 절
6. **핵심 변경**: `agent/graph.py:228`, `agent/graph.py:270`, `agent/ollama_llm.py:231`
7. **화면**: 위 "화면"
