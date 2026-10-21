# After 증거 묶음 (코드 수정 후, 2026-10-21)

- 대상 코드: `main` HEAD. Before는 git tag `before-evidence`다(에이전트 코드는 tag `baseline`과 같다).
- 실행 조건은 Before와 같다: `LLM_BACKEND=ollama`, fast=`qwen3:0.6b`, quality=`qwen3:8b`, `SUPERVISOR_VERSION=v2`(S9만 v1), 질의셋 `bench/queries.json` 10건 × 3회.
- 수치는 모두 아래 파일에서 인용했다. 직접 다시 계산하는 명령은 맨 아래에 있다.
  - Before: `bench/results/baseline_*`, `outputs/before/evidence/`
  - After: `bench/results/after_*`, `outputs/after/evidence/`
- After 측정은 2번 했다.
  - **1차**(`after_run1_*`)에서 q10 라우팅 회귀를 발견했다 → 보정 → **2차**(`after_*`)가 최종이다.
  - 경위는 `outputs/final-report/09b_step8_route_regression.md`에 있다.

## 0. 측정 이력 — 어느 결과가 최신인가

| 순서 | 결과 파일 (`bench/results/`) | 측정 시각 | 코드 | 상태 |
|---|---|---|---|---|
| 1 | `baseline_*` | 10-20 14:14 | tag `baseline` (원본) | **Before 기준** |
| 2 | `baseline_rerun1021_*` | 10-21 16:11 | 원본 | 참고용 재실행. 같은 코드도 회차마다 흔들린다는 근거(이번 회차는 q01 타임아웃 없음) |
| 3 | `after_run1_*` | 10-21 21:25 | `1f8e51d` (1~7단계) | **폐기**: q10 라우팅 회귀 발견 → `09b` 문서 |
| 4 | `after_*` + `after_langsmith_eval.json` | 10-21 21:33 | `83125f4` (+route 보정) | **발표 기준 After**. 화면 캡처·LangSmith judge가 이 회차다 |
| 5 | `after_n_*` | 10-21 22:20 | N1~N6 수정 후 (`11` 문서) | **최신 코드 회귀 확인**. 4번과 같은 수준인지 확인했다 (judge는 다시 돌리지 않음) |

- 아래 1~2절의 After 값은 **4번(`after_*`, 발표 기준)**이다.
- 최신 코드(5번)와의 비교는 [`11_new_issues_N1_N8.md`](../final-report/11_new_issues_N1_N8.md)에 있다.

| 지표 | Before (`baseline`) | After (`after`, 발표 기준) | 최신 (`after_n`) |
|---|---|---|---|
| runbook 정답률 / recall / precision | 0.739 / 0.775 / 0.87 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| incident 중앙값 | 36.0초 | 12.8초 | 12.5초 |
| 최대 응답 | 300초 | 24.4초 | 24.7초 |
| chat 중앙값 | 1.28초 | 0.26초 | 0.26초 |
| 가상 비용 | $0.1637 | $0.1360 | $0.1368 |
| validate 재작성 | 0 | 3 (q02) | 3 (q02) |

## 1. Before → After (미션 C4: 지연시간·비용·검색 정확도·retry)

### 정확도 (`rescore.py` 정답 세트 재채점 / LangSmith evaluate)
| 지표 | Before | After | 출처 |
|---|---|---|---|
| 응답 성공률 (기존 지표) | 29/30 = 0.97 | **30/30 = 1.0** | `baseline_summary.csv` / `after_summary.csv` |
| **장애 유형(runbook) 정답률** = 검색 정확도 | 0.739 / 0.75 | **1.0 / 1.0** | `evidence/S10`, `S13` |
| **조사 범위 recall** | 0.775 / 0.786 | **1.0 / 1.0** | 같음 |
| 조사 정밀도 precision | 0.87 / 0.875 | **1.0 / 1.0** | 같음 |
| 답변 토픽 포함률 | 0.718 / 0.778 | **0.944 / 0.944** | 같음 |
| LLM-judge 품질 (qwen3:8b, 4기준) | 0.855 | **0.955** | `after_langsmith_eval.json` (실험 `after-6f8a05ac`) |

### 지연시간 (`bench/results/*_raw.jsonl`, counted 30건 + 다턴 앞 턴 포함 33호출)
| 지표 | Before | After |
|---|---|---|
| 전체 평균 / 중앙값 / 최대 | 45.5초 / 32.4초 / **300초(타임아웃)** | **10.2초 / 11.8초 / 24.4초** |
| incident 중앙값 | 36.0초 | **12.8초** |
| chat 중앙값 | 1.28초 | **0.26초** |
| q01 3회 | 27.2 / 47.6 / **300.0**초 | 12.4 / 12.6 / 12.7초 |
| q03 3회 (편차) | 70.6 / 92.7 / 152.2초 | 11.2 / 11.4 / 11.8초 |
| 처리 중 `/health` 최대 지연 | 1.73초 (S5) | **0.03초** (`evidence/S5_health_during_q05.txt`) |

### 비용·retry·파이프라인
| 지표 | Before | After | 비고 |
|---|---|---|---|
| 가상 비용 합계 (33호출) | $0.1637 | **$0.1360** (−17%) | judge 호출이 늘었지만 think 끔과 분석 생략으로 상쇄됐다 |
| 비교 분석(analysis) 실행 | 20/23건 (8종 중 7종) | **9/24건** (q04·q05·q06, 시스템 2개인 질문만) | P3 이중 게이트 |
| retry로 복구 | 0회 (재시도가 실제 예외를 못 잡음) | warmup에서 1회 복구(`after_raw.jsonl` run_meta), S6·S9 화면 "(재시도 성공)" | 측정 30건 안에서는 장애가 없어 retry 0 |
| 재작성(validate 반려) | 0/23 | 3/24 (q02 3회: "조사한 시스템 cache-service 누락") | P11 규칙이 실제로 동작했다 |
| 타임아웃 | 1건 (q01, 300초) | 0건 | |

## 2. 화면·터미널 캡처 (Before와 같은 파일명)
| 파일 | Before | After |
|---|---|---|
| `captures/S1_q05_multi_system_db_down.png` | web-01만 조사, db-down | **web-01·auth-service 조사, high-latency, "검수 통과 (근거 확인됨)"** |
| `captures/S2_q06_only_one_system.png` | payments만 조사 | payments·cache 모두 조사 + 비교 분석 |
| `captures/S6_ollama_down_silent_failure.png` | 답변 중 Ollama 끊김 → 아무 표시 없음 | **빨간 말풍선, `LLM_STREAM_BROKEN`, [다시 시도] 버튼** |
| `captures/S9_v1_no_monitoring.png` | v1에서 모니터링 조회 없음 | v1에서도 web-01 조회 |
| `captures/terminal/S7_stream_empty_message.png` | 빈 메시지 200 | **422**, SSE 헤더 |
| `captures/terminal/S4`, `S11`, `S12` | q05 write 86%, q01 300초, q03 편차 | 노드별 ms, q01 analyze 생략, q03 11초대 |
| `captures/code/C01~C13` (C09 제외) | 빨간 줄 = 문제 지점 | 빨간 줄 = 고친 지점 |

S6 재현 방법: Before는 `pkill ollama`로 Ollama를 껐다. After는 사용자의 Ollama를 건드리지 않으려고, 프록시(`scripts/cut_proxy.py`)를 6초 뒤 끊었다. 서버 입장에서는 같은 "스트림 도중 연결 끊김"이다.

## 3. 나빠졌거나 남은 것 (숨기지 않음)
- **q02가 Before보다 덜 빨라졌다**: 33.2초 → 22.9초. 규칙 ② 반려로 매번 재작성해서 write가 두 번 돈다.
- **q04 judge 0.95 → 0.75**, q01 1.0 → 0.95. 평균은 올랐지만 질문별로는 떨어진 것도 있다. LangSmith 1회 실행이라 표본이 작다.
- **q07 topic_coverage 0.5**: Before와 같다. 기대 토픽 일부가 답변에 없다.
- 1차 After 측정에서 think 끔이 **라우팅 회귀**(q10 14초)를 만들었다 → 보정 후 재측정했다.
- incident 응답의 60~70%가 아직 8b write 단계다(`evidence/S4_q05_node_timing.txt`).

## 4. 파일
| 폴더 | 내용 |
|---|---|
| `captures/` | 실제 Vue 화면(Playwright + 설치된 Chrome): S1 S2 S6 S9 |
| `captures/code/` | 고친 코드 C01~C13 (`scripts/code_capture_after.py`) |
| `captures/terminal/` | `evidence/*.txt`를 터미널 스타일로 렌더링한 것 |
| `evidence/` | 원본 텍스트. P1~P11은 단계별 검증, S4~S15는 Before와 짝을 이루는 After 증거 |
| `scripts/` | `realserver.sh`(:8199 실모델 서버), `probe_p4.py`, `ask.py`, `cut_proxy.py`, `p6_repro.sh`, `code_capture_after.py` |

## 5. 다시 계산하는 명령
```bash
./.venv/bin/python3 bench/rescore.py --tag baseline     # 0.739 / 0.775
./.venv/bin/python3 bench/rescore.py --tag after        # 1.0 / 1.0
tail -3 bench/results/after_run_log.txt                 # 평균 10162ms, 성공률 1.00
diff <(cut -d, -f1,3,4 bench/results/baseline_summary.csv) <(cut -d, -f1,3,4 bench/results/after_summary.csv)
```
