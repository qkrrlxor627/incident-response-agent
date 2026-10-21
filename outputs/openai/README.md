# OpenAI(과금) 환경 Before / After (2026-10-21 밤)

- 모델: fast `gpt-4o-mini`, quality `gpt-4o` (`sh/run_agent_openai.sh` 기본값). LangSmith 프로젝트는 `capstone-all-total-openai`.
- **Before** = git tag `before-evidence` 코드(worktree로 꺼내 실행). **After** = 현재 코드(N9 수정 포함).
- 질의셋, 반복 횟수, 채점 방식은 Ollama 측정과 같다: `bench/queries.json` 10건 × 3회, `rescore.py`, `eval_langsmith.py`.
  - LLM-judge는 Ollama qwen3:8b(무료)다. 같은 심사위원으로 채점해서 Before와 After를 비교할 수 있다.
- 수치 출처는 `bench/results/openai_*`, `outputs/openai/evidence/`이고, 캡처는 `outputs/openai/{before,after}/captures/`(같은 파일명)다.
- **비용**: 아래 "가상 비용"은 Ollama 측정과 같은 잣대로 비교하려고 쓴 **가상 단가 × 실측 토큰**이다. 실제 청구 금액은 OpenAI 사용량 페이지에서 확인해야 한다. 이번 측정 전체(Before + After 2회 + 평가)의 실제 비용은 1달러 안팎으로 추정한다.

## 측정 이력
| 순서 | 결과 파일 (`bench/results/`) | 코드 | 상태 |
|---|---|---|---|
| 1 | `openai_before_*`, `openai-before_langsmith_eval.json` | `before-evidence` | **Before** |
| 2 | `openai_after_run1_*`, `openai-after_run1_langsmith_eval.json` | 현재 코드(N9 수정 전) | **폐기**: judge 오반려 4건 발견 → N9 |
| 3 | `openai_after_*`, `openai-after_langsmith_eval.json` | 현재 코드 + N9 | **최신 After** |

## 결과
| 지표 | Before | After | 변화 |
|---|---|---|---|
| 응답 성공률 | 30/30 | 30/30 | — |
| **runbook 정답률** (검색 정확도) | **0.75** | **1.0** | q04·q08 오분류 해결 |
| 조사 범위 recall | 1.0 | 1.0 | gpt-4o-mini는 원래 시스템을 빠뜨리지 않았다(P1이 나타나지 않음) |
| 조사 정밀도 precision | 0.861 | **1.0** | q04 2회차 auth-service 추가 조사, q08 auth-service 조사가 사라짐 |
| 답변 토픽 포함률 | 0.833 | 0.944 | |
| LLM-judge 품질 | 0.835 | **0.96** | q04 0.5 → 1.0, q08 0.3 → 1.0 |
| 장애 질문 응답 중앙값 | **5.3초** | 6.5초 | **+1.2초 (나빠짐)** |
| 최대 응답 | 7.2초 | 10.1초 | 나빠짐 |
| chat 중앙값 | 1.91초 | 1.77초 | |
| 가상 비용 (33호출) | **$0.0739** | $0.1465 | **약 2배 (나빠짐)** |
| 재작성(validate 반려) | 0 | 0 (N9 수정 전 1차는 4) | |

### 화면 (같은 파일명)
| 파일 | Before | After |
|---|---|---|
| `S1_q05_multi_system.png` | 두 시스템 조사, high-latency | 같음 + "검수 통과 (근거 확인됨)" |
| `S2_q06_two_systems.png` | 두 시스템 조사, cpu-spike | 같음 |
| `S3_q04_gateway_timeout.png` | **cpu-spike**(오분류: 두 시스템 알림을 합쳐 CPU 규칙이 먼저 걸림) | **network-timeout** |
| `S4_q08_unmonitored.png` | 엉뚱한 auth-service를 조사하고 high-latency를 붙임 | 조사 없이 "모니터링 대상 아님" |

## 해석 — Ollama와 무엇이 달랐나
| 개선 | Ollama(0.6b/8b)에서 | OpenAI(4o-mini/4o)에서 |
|---|---|---|
| P1 시스템 보충 | **핵심 효과**(recall 0.775 → 1.0) | 효과 없음: 모델이 원래 잘 했다 |
| P2 분류 | q05 db-down 해결 | **q04 cpu-spike → network-timeout 해결**. Ollama Before에서는 P1 때문에 시스템 1개만 봐서 드러나지 않던 문제다 |
| P3·P4·P9 속도 | **핵심 효과**(36초 → 13초, 300초 정지 해결) | 거의 없음: OpenAI 호출은 원래 빨랐다. think 옵션은 Ollama 전용이다 |
| P11 judge | 답변 품질 0.855 → 0.955 | 답변 품질 0.835 → 0.96. 대신 **gpt-4o 호출이 1번 늘어 지연 +1.2초, 비용 약 2배** |

→ **같은 개선도 모델에 따라 효과가 다르다.**
- 작은 로컬 모델에서는 코드의 권위 보정(P1, P2, gate)과 비동기 처리가 정확도와 속도를 모두 올렸다.
- 큰 API 모델에서는 정확도는 분류 규칙(P2)으로 올랐지만, 속도와 비용은 검증 비용(P11)만큼 나빠졌다.

## 이번에 새로 발견해 고친 문제: N9 (judge가 runbook 제목만 봄)
- **증상**: After 1차에서 gpt-4o judge가 runbook에 있는 조치(인스턴스 추가, 커넥션 풀 확장, DNS 확인)를 "수집된 사실에 없다"며 4건 반려했다(`evidence/N9_judge_runbook_title_only.txt`).
- **원인**: P11에서 만든 `_facts_text`가 runbook을 **제목 한 줄**로 줄여 judge에게 넘겼다. Ollama 8b judge는 관대해서 드러나지 않았다.
- **수정**:
  - `agent/graph.py`의 `[N9 AFTER]`: runbook 본문을 최대 1500자까지 넘긴다.
  - judge 프롬프트에 "runbook 본문의 조치는 근거가 있는 것"을 명시하고, 이유를 한국어로 쓰게 했다.
- **결과**: 재작성 4 → 0, 지연 6.7 → 6.5초, judge 품질 0.945 → 0.96.
- **테스트**: `test_n9_judge_facts_include_runbook_body`

## 남은 트레이드오프와 다음 실험 후보
- **judge 비용**: `JUDGE_LLM=fast_llm`으로 바꾸면 judge가 gpt-4o-mini가 된다. 비용과 지연을 줄일 수 있지만 **측정하지 않았다.** Ollama에서는 작은 judge가 오반려를 냈으므로, 같은 측정으로 확인한 뒤 결정해야 한다.
- OpenAI 경로는 답변을 토큰 단위로 스트리밍하지 않는다(완성된 답을 한 번에 표시한다).

## 직접 재현
```bash
# After (현재 코드) — 과금
bash sh/run_agent_openai.sh                        # y 입력
./.venv/bin/python3 bench/run_baseline.py --repeat 3 --tag openai_after
./.venv/bin/python3 bench/rescore.py --tag openai_after
set -a; source .env; set +a; cd bench && ../.venv/bin/python3 eval_langsmith.py --prefix openai-after; cd ..
/tmp/capvenv/bin/python outputs/openai/scripts/ui_capture_any.py outputs/openai/after/captures/S3_q04_gateway_timeout.png \
  "gateway-service에서 payments-service로 가는 요청이 타임아웃 나고 있어요"

# Before (원본 코드) — 별도 폴더에서 실행
git worktree add /tmp/before_wt before-evidence
cd /tmp/before_wt && (set -a; source ~/subject/1020/all_total_vue_student/.env; set +a; \
  LLM_BACKEND=openai ~/subject/1020/all_total_vue_student/.venv/bin/python3 server.py &)
# … 위와 같은 명령, --tag openai_before …
git worktree remove --force /tmp/before_wt
```
- `ui_capture_any.py`는 Before 캡처 스크립트와 같고, 헤더 대기 조건만 'ollama' → '실모델'(백엔드 무관)으로 바꿨다.
