# 8단계 중 발견 — P9 후속: think를 끈 라우터의 오분류 회귀

| 항목 | 내용 |
|---|---|
| 수준 | L2 (측정이 찾아낸 회귀 → 원인 → 보정 → 재측정) |
| 매핑 | C3-a / K6(권위 정규화)·K15(평가로 회귀 발견) |
| 커밋 | `git log --oneline -- outputs/final-report/09b_step8_route_regression.md` 맨 위 줄 |

## ① 인식
1차 After 측정(`bench/results/after_run1_summary.csv`)에서 q10(이름 기억 2턴)의 중앙값이 **2.5초 → 14.2초**로 오히려 느려졌다.

## ② 정의
- **기대**: "제 이름은 민수입니다"는 일반 대화(chat)로 0.3초 안에 답한다.
- **실제**: 3/3회 `route=incident`로 분류돼 plan → research(auth-service) → write → validate 전체를 탔다(13.8~14.6초).
- **증거**: `outputs/after/evidence/S15_route_regression_q10.txt`
  ```
  1차(보정 전) rep 1 | RouteDecided: {'route': 'incident'} | 13779 ms | 노드: route, plan, ..., write, validate
  ```

## ③ 원인
- 3단계(P9)에서 `think: false`로 바꾼 뒤, qwen3:0.6b 라우터가 짧은 자기소개를 장애로 분류했다. Before(think 켬)에는 3/3 chat이었다.
- **(추정)** 사고 토큰 없이 바로 JSON을 내면 0.6b 모델의 분류 정확도가 떨어진다. 같은 질문에서 think on/off를 반복 비교하지는 않았다.
- 코드 쪽 원인: route는 모델 판단을 **그대로** 썼다(`agent/graph.py` `route_node`). P1(plan)과 P3(gate)에는 있는 코드 권위 보정이 route에만 없었다.

## ④ 대안
| 대안 | 장점 | 단점 | 선택 |
|---|---|---|---|
| A. route만 think를 다시 켠다 | 원래 분류 품질 | route가 1초 → 수 초. P9의 지연 개선을 일부 되돌린다 | ✗ |
| **B. 코드 권위 보정: 모델이 incident라고 해도 증상 단어도 시스템 이름도 없으면 chat** | 결정론. 벤치 10개 질문 전부를 테스트로 고정할 수 있다 | 키워드 목록 밖의 장애 표현은 chat으로 갈 수 있다 | ✅ |
| C. 키워드만으로 route(모델 없음) | 가장 빠르다 | 모델의 일반화 능력을 버린다 | ✗ |

보정은 **incident → chat 한 방향**만 한다. 모델이 chat이라고 했는데 실제 장애인 경우는 모델 판단을 존중한다.

## ⑤ 실행
| 파일 | 변경 |
|---|---|
| `agent/systems.py` `INCIDENT_PATTERN`, `looks_like_incident` | 증상 단어, 감시 대상 시스템 이름, 감시하지 않는 시스템 이름 중 하나라도 있으면 장애로 본다. v1 롤백(P10)도 같은 함수를 쓰도록 옮겼다 |
| `agent/graph.py` `route_node` | `[P9 후속 AFTER]` 보정. 이벤트에 `corrected_from: "incident"`를 남긴다 |
| `agent/supervisor_v1.py` | 자체 패턴을 지우고 `looks_like_incident`를 쓴다 |

## ⑥ 검증
| | 1차(보정 전) | 2차(보정 후) |
|---|---|---|
| q10 1턴 route | incident 3/3 | **chat 3/3** (`corrected_from: incident`) |
| q10 중앙값 (2턴 합) | 14.2초 | **0.52초** |
| 나머지 incident 질문 | 정답률 1.0 | 정답률 1.0 (보정이 장애 질문을 chat으로 바꾸지 않았다) |

pytest는 57 passed다.

## ⑦ 재발 방지
- `test_looks_like_incident_matches_every_benchmark_query[q01~q10]`: 벤치 질문 10개 전체를 고정했다
- `test_route_corrects_self_introduction_to_chat`

## 교훈 (발표용)
- 지연을 줄이려는 변경(think 끔)이 **다른 단계의 정확도**를 떨어뜨렸다.
- 정답 세트로 다시 측정했기 때문에 바로 발견했다. 응답 성공률만 셌다면 이 회귀는 **"성공"으로 집계됐을 것**이다(1차도 30/30).

## 직접 확인하는 방법
```bash
cut -d, -f1-4 bench/results/after_run1_summary.csv | grep q10    # 1차: 14248ms
cut -d, -f1-4 bench/results/after_summary.csv | grep q10         # 2차: 522ms
./.venv/bin/python3 -m pytest tests -q -k "looks_like or corrects"
curl -s -X POST localhost:8100/chat -H 'content-type: application/json' \
  -d '{"message":"제 이름은 민수입니다","thread_id":"t-rt"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['events'][0])"
```
- 기대 출력: `{'type': 'RouteDecided', 'route': 'chat', 'corrected_from': 'incident', ...}`

**화면**: :8600에서 `제 이름은 민수입니다`를 입력하면 진행 단계 없이 바로 답한다. 이어서 `제 이름이 뭐였죠?`를 입력하면 "민수"라고 답한다.
