# 새로 발견된 문제 N1~N8 — After 이후 실사용 테스트·탐색 스윕

| 항목 | 내용 |
|---|---|
| 계기 | 사용자가 화면에서 "장애 질문 → 제 이름은 민수입니다"를 입력하자 **이전 장애 보고서가 그대로 다시 나왔다**(N1) |
| 방법 | 측정 질문 10개 밖의 상황 12개를 실제 서버에 보내는 탐색 스윕 `outputs/after/scripts/explore_sweep.py` |
| 증거 | 수정 전 `outputs/after/evidence/N_sweep_before_fix.txt` · 수정 후 `N_sweep_after_fix.txt` · N1 실험 `N1_chat_history_copy.txt` |
| 커밋 | `git log --oneline -- outputs/final-report/11_new_issues_N1_N8.md` |

**왜 측정에서 못 찾았나**: 측정 질문 10개는 매번 **새 대화**에서 **시스템 정식 이름을 소문자로** 묻는다. 대화를 섞거나 이름을 바꿔 말하는 상황은 정답 세트에 없었다. → README 한계("정답 세트 과적합")가 실제로 드러난 사례다.

## 요약
| # | 시나리오 (입력) | 수정 전 | 원인 | 수정 후 | 매핑 |
|---|---|---|---|---|---|
| N1 | 장애 질문 → `제 이름은 민수입니다` | 직전 장애 보고서를 그대로 베낌 | chat 이력에 긴 보고서가 들어가고, 0.6b가 그걸 이어 씀(think on/off 모두 3/3) | 베끼지 않음: ⑦ "민수님의 이름입니다." | C3-e / K13 |
| N2 | `결제 서버 응답이 너무 느려요` | auth-service 조사(엉뚱함) | 시스템 정식 이름만 인식 | **payments-service**, cpu-spike | C3-a / K6 |
| N3 | `WEB-01 장애 진단해줘` | auth-service 조사 | 대소문자를 구분해서 매칭 | **web-01** | C3-a / K6 |
| N4 | `payments 서비스 CPU가 높아요` | chat으로 바뀌어 "CPU가 높아지면 데이터 처리가 빠르게 됩니다" | **P9 후속 보정의 부작용**: 증상 단어 목록이 좁았다 | incident, payments-service 조사 | C3-a / K6·K7 |
| N5 | `web-01 상태 괜찮아?` | chat으로 가서 조회 없이 "네, 괜찮아요"라고 **지어냄** | route 보정이 incident → chat 한 방향뿐 | 시스템 이름이 있으면 incident → 실제 조회 후 healthy 답변 | C3-a / K6·K7 |
| N6 | `web-01 장애 로그 로그 …`(긴 입력) | 시스템 6개 모두 조사(30.1초) | P1이 질문에 없는 시스템도 모델이 고르면 조사하게 둠 | web-01만(16.7초) | C3-a / K6 |
| N7 | 동시 요청 3건 | 34~53초 | Ollama가 요청을 순서대로 처리(코드 결함 아님) | **미수정 — 한계** | 기준 외 |
| N8 | 장애 → `그럼 지금 당장 뭐부터 해야 해?` | 보고서를 베껴 그럴듯하게 답함 | N1과 같은 구조 | N1 수정 후 "다시 봐요."(문맥 상실) → **나빠짐, 한계** | 기준 외 |

## N1 — chat이 장애 보고서를 베낌
- **정의**
  - 기대: 일반 대화는 대화 내용에만 답한다.
  - 실제: 장애 질문 다음 턴에 그 보고서를 다시 출력한다.
  - 증거: `session.db` 12번 행, `N1_chat_history_copy.txt`
- **원인**
  - 라우팅은 정상이었다(`route=chat`).
  - `chat_answer_node`가 최근 이력 10개를 그대로 프롬프트에 넣는다(`agent/ollama_llm.py` `chat`). 0.6b 모델은 마지막 assistant 답변을 이어 쓴다.
  - think를 켜도 같았다. **Before부터 있던 문제다.**
- **대안 실험**: 결과는 `N1_chat_history_copy.txt` 4절에 있다.

  | 대안 | 결과 |
  |---|---|
  | 대화 배열로 전달 | 베낌 ✗ |
  | 보고서를 "(생략)"으로 대체 | 그 문구를 베낌 ✗ |
  | '참고' 블록으로 분리 | 의미 없는 답 ✗ |
  | **이력에서 보고서를 뺌** | 베끼지 않음 ✅ |

- **실행**:
  - `agent/graph.py:118` `_chat_history`: assistant 답변 중 `1)`로 시작하는 것을 뺀다.
  - `agent/graph.py:137-142`: chat 노드가 거른 이력을 넘긴다. 세 백엔드에 모두 적용된다.
- **트레이드오프**: 장애 직후의 후속 질문이 문맥을 잃는다 → **N8**. 0.6b의 답변 문장 품질 자체("민수님의 이름입니다.")는 이번 범위 밖이다.

## N2·N3 — 시스템 인식 (별칭, 대소문자)
- `agent/systems.py:36-47` `SYSTEM_ALIASES`:
  - 결제/payments → payments-service
  - 로그인/인증/auth → auth-service
  - 캐시 → cache-service
  - 게이트웨이 → gateway-service
  - 로그 서버 → log-service
  - 웹 서버 → web-01
- `agent/systems.py:49-73` `mentioned_systems`:
  - 소문자로 바꿔 비교한다(N3).
  - 정식 이름을 먼저 찾고, 그다음 **긴 별칭부터** 찾는다.
  - 매칭된 구간은 지운다. 그래서 "로그인"이 "로그"로 다시 잡히지 않는다.
- 대안:
  - LLM에게 시스템을 추출하게 하는 방법은 0.6b가 문장을 내는 문제(P1 원인)와 같아서 제외했다.
  - 별칭 사전은 결정론이고 테스트로 고정할 수 있다.
- 트레이드오프: 사전에 없는 표현("돈 나가는 서버")은 여전히 기본값(auth-service)으로 간다. "로그"만 단독으로 쓰면 log-service로 보지 않는다("로그를 보니…" 같은 오탐을 막기 위해서).

## N4·N5 — route 보정을 양방향으로
- `agent/graph.py:99-112`:
  - ① 질문에 모니터링 시스템이 나오면 **incident**(N5)
  - ② 증상 단어도 시스템도 없으면 **chat**(P9 후속 유지)
  - 보정했으면 이벤트에 `corrected_from`을 남긴다.
- `agent/systems.py:100-106` `INCIDENT_PATTERN`(N4):
  - cpu·메모리·디스크·응답·커넥션, 높아/안 돼/실패, 5xx, 영어 down/slow/error를 더했다.
  - 대소문자를 무시한다.
- **교훈**: P9 후속 보정은 q10 회귀를 고쳤지만, 증상 단어 목록이 좁아서 **새 회귀(N4)를 만들었다**. 측정 질문 10개만 테스트로 고정했기 때문이다. 이번에는 탐색 시나리오도 테스트로 고정했다.
- 트레이드오프: "auth-service가 뭐야?" 같은 설명 질문도 이제 장애 조회를 한다(조회 비용 약 10초).

## N6 — 질문에 없는 시스템은 조사하지 않음
- `agent/ollama_llm.py:279-282`, `agent/openai_llm.py:213-216`: `ordered = wanted or 모델 선택 or 기본값`
- **P1 설계를 일부 되돌린 것이다.** P1에서는 "모델이 질문에 없는 시스템을 골라도 추가 조사"를 장점으로 봤다. 실제로는 긴 입력에서 6개를 모두 조사해 지연(30초)과 노이즈를 만들었다.

## 검증
| 확인 | 결과 |
|---|---|
| pytest | 57 → **69 passed** (N1~N6 테스트 12개 추가) |
| 탐색 스윕 | N2~N6 해결, N1 베끼기 사라짐, N8 나빠짐 (`N_sweep_after_fix.txt`) |
| 기존 측정 질문 10개 회귀 확인 | `bench/results/after_n_*` → 아래 표 |

| 지표 | Before (`baseline`) | After (`after`, 발표 기준) | 최신 (`after_n`) |
|---|---|---|---|
| runbook 정답률 / recall / precision | 0.739 / 0.775 / 0.87 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| incident 중앙값 | 36.0초 | 12.8초 | 12.5초 |
| 최대 응답 | 300초 | 24.4초 | 24.7초 |
| chat 중앙값 | 1.28초 | 0.26초 | 0.26초 |
| 가상 비용 | $0.1637 | $0.1360 | $0.1368 |
| validate 재작성 | 0 | 3 (q02) | 3 (q02) |

→ 기존 질문 10개는 나빠지지 않았다. 차이는 회차 간 흔들림 수준이다.

## 재발 방지 (테스트)
`tests/test_agent_units.py` 맨 아래 "새로 발견된 문제 N1~N6":
- `test_n1_chat_history_drops_incident_reports`
- `test_n2_n3_system_aliases_and_case[6]`
- `test_n4_n5_route_correction_both_ways[4]`
- `test_n6_plan_ignores_model_systems_not_in_query`

## 남은 한계 (N7·N8)
- **N7 동시 요청**: 로컬 Ollama가 순서대로 처리한다. `OLLAMA_NUM_PARALLEL` 설정이나 GPU 여유가 필요하다. 코드 범위 밖이다.
- **N8 후속 질문 문맥**: 장애 직후 "그럼 뭐부터 해?"는 이전 진단을 이어받아야 한다. 0.6b chat으로는 베끼거나 문맥을 잃는다. 후속 질문을 감지해 **직전 장애의 시스템으로 incident 파이프라인을 다시 타는 방법**이 필요하다(다음 과제).
- 0.6b chat의 답변 품질(어색한 문장, 프롬프트 주입 문장을 그대로 따라 말함)은 모델 크기의 한계다. 시스템 프롬프트는 유출되지 않았다(S10).

## 직접 확인하는 방법
```bash
grep -n "\[N[1-6] " agent/*.py
./.venv/bin/python3 -m pytest tests -q -k "n1_ or n2_ or n4_ or n6_"
./.venv/bin/python3 outputs/after/scripts/explore_sweep.py          # 서버(:8100) 필요, 약 3분
```

**화면** (:8600, 같은 창에서 순서대로)
1. `payments-service 결제 응답이 느려지고 CPU가 치솟았어요, 원인 확인해주세요`
2. `제 이름은 민수입니다` → 장애 보고서가 **다시 나오지 않는다**(N1)
3. `결제 서버 응답이 너무 느려요` → "모니터링 지표 확인 (시스템: payments-service)"(N2)
4. `WEB-01 장애 진단해줘` → 시스템: web-01(N3)
5. `web-01 상태 괜찮아?` → 진행 단계에 모니터링 조회가 나오고, 실제 수치로 답한다(N5)
