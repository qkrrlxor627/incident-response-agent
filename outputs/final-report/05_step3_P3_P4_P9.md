# 3단계 — P3 불필요한 분석 + P4 동기 LLM 호출 + P9 시간 제한·thinking·관측

| 항목 | 내용 |
|---|---|
| 수준 | L3 |
| 매핑 | P3: C3-a / K7·K11 · P4: C3-d / K12 · P9: C3-e / K9·K10·K15 |
| 사용자 문제 목록 | #6 동기 LLM 호출 병목, #7 응답시간 불안정, #8 불필요한 비교 분석, #10 성능 관측 부족 |
| 커밋 | `git log --oneline -- outputs/final-report/05_step3_P3_P4_P9.md` 맨 위 줄 |

## ① 인식
q01 1회차가 314.9초 만에 실패했다. 그중 `analyze` 단계 하나가 300.07초 동안 멈췄다(S11). 문제 4개가 한 번에 겹친 사례다.

## ② 정의
- **기대**:
  - 비교 분석은 비교할 시스템이 2개 이상일 때만 한다.
  - LLM을 기다리는 동안에도 서버는 다른 요청을 처리한다.
  - 단계마다 적절한 시간 제한이 있다.
- **실제**:
  - 분석이 incident 8종 중 7종에서 실행됐다.
  - 처리 중 `/health`가 최대 1.73초 지연됐다(S5).
  - 모든 호출의 timeout이 300초였다.
  - q03은 같은 질문인데 70.6~152.2초로 흔들렸다.
- **증거**:
  - `outputs/before/evidence/S11`(analyze 300.07초 ReadTimeout), `S5`
  - `S12`(write 1,863~3,537토큰인데 답변은 107~120자)
  - `bench/results/before.md`

## ③ 원인
| 위치 (Before) | 문제 | 문제 번호 |
|---|---|---|
| `agent/graph.py:127` gate | `needs_analysis`(모델 판단)만 믿는다. 0.6b 모델은 거의 항상 true다 | P3 |
| `agent/ollama_llm.py:104` | `async` 노드 안에서 `httpx.post()`(동기)를 호출한다 → 응답이 올 때까지 이벤트 루프가 멈춘다 | P4 |
| `agent/graph.py:78`, `113`, `243` | route·plan·analyze를 `await` 없이 호출한다(동기 함수) | P4 |
| `agent/ollama_llm.py:104`, `127` | timeout이 300초 하나뿐이다 | P9 |
| `agent/ollama_llm.py:95-101` payload | `think` 옵션이 없다 → qwen3가 숨은 사고 토큰을 만든다 | P9 |

**이번에 확정한 것 (Before 때는 추정이었음)**: thinking 토큰이 원인이다. 같은 질문에서 생성 토큰이 다음과 같이 줄었다.
- qwen3:0.6b는 190 → 9개다.
- qwen3:8b는 409 → 38개이고, 시간은 18.9초 → 1.9초다.

근거: `outputs/after/evidence/P9_think_tokens.txt`

## ④ 가설과 대안
| 문제 | 대안 | 선택 | 이유 |
|---|---|---|---|
| P3 | A. 프롬프트로 "필요할 때만"을 강조 / B. analysis를 아예 제거 / **C. 이중 게이트(LLM 판단 + research ≥ 2)** | C | K7 권위 게이트. q06처럼 정말 필요한 비교는 남긴다 |
| P4 | A. `asyncio.to_thread(httpx.post)` / **B. `httpx.AsyncClient` + `await`** / C. 별도 워커 프로세스 | B | K12 블로킹 금지. 스트림 쪽(`_chat_stream`)이 이미 AsyncClient라 일관성이 있다. A는 스레드 수만큼만 동시 처리된다 |
| P9 | A. 300초 유지 / **B. 단계별 timeout(빠른 단계 60초, write 180초) + `think: false` + 노드별 elapsed_ms** | B | 멈춘 단계를 빨리 실패시키고(4단계 재시도·격리와 연결), 병목 위치를 응답에서 바로 본다 |

## ⑤ 실행
| 파일:줄 | 변경 |
|---|---|
| `agent/ollama_llm.py:22-32` | `FAST_TIMEOUT=60`, `WRITE_TIMEOUT=180`, `OLLAMA_THINK=false` (환경변수로 바꿀 수 있다) |
| `agent/ollama_llm.py:110-131` | Before `_chat`을 주석으로 남겼다 → `async def _chat` + `httpx.AsyncClient` + `await client.post` |
| `agent/ollama_llm.py` route/plan/analyze | `def` → `async def`, `self._chat` → `await self._chat` |
| `agent/openai_llm.py`, `agent/fake_llm.py` | 같은 인터페이스(async)로 맞췄다 |
| `agent/graph.py:87-88`, `123-124`, `309-311` | `await deps.fast_llm.route/plan/analyze` |
| `agent/graph.py:137-152` | 이중 게이트. `GateApplied` 이벤트에 `reason`을 넣었다 |
| `agent/graph.py:381` `_timed` | 노드 실행 시간을 `state["timings"]`에 누적하고, JSON 한 줄 로그를 남긴다 |
| `server.py:127` | 응답 `metadata.timings_ms` |
| `server.py:186` | 스트림 이벤트에 `elapsed_ms` |

## ⑥ 검증 (실모델 1회, `outputs/after/evidence/P3_P4_P9_real_probe.txt`)
| 질문 | Before | After | 분석 |
|---|---|---|---|
| q01 payments CPU | 중앙값 47.6초, 1회 300초 실패 | **11.0초** | `GateApplied[research 1개 < 2]` → 생략 |
| q06 payments + cache 공통 원인 | 중앙값 62.5초 | **9.7초** | `allowed` → 실행(155ms) |
| q03 log 디스크 | 중앙값 92.7초 (70.6~152.2) | **9.1초** | 생략 |
| 처리 중 `/health` | 최대 1,730ms | **최대 11ms** | — |

- pytest: 28 passed
- 노드별 시간: 이제 write가 전체의 약 80%다(q01: 11.0초 중 8.9초). 남은 병목은 8b 모델의 답변 생성이다.
- 1회 측정이다. 30건 통계(중앙값, p95)는 8단계 After 측정에서 확인한다.

## ⑦ 재발 방지 (테스트)
- `test_gate_removes_analysis_for_single_system_even_if_model_wants_it`
- `test_gate_keeps_analysis_when_needed_and_two_systems`
- `test_fast_llm_methods_are_coroutines`: 3개 백엔드의 route·plan·analyze가 async인지 검사한다
- `test_ollama_payload_disables_thinking_and_uses_stage_timeout`: httpx를 가짜로 바꿔 `think: false`와 timeout을 확인한다
- `test_timed_wrapper_records_elapsed_ms`

## 트레이드오프
- **think 끔**: 답변이 짧아질 수 있다(8b 실험에서 173자 → 59자). 품질은 8단계 LLM-judge 점수로 같이 확인한다. 떨어지면 `OLLAMA_THINK=true`로 되돌릴 수 있다.
- **60초 timeout**: 느린 PC에서는 정상 호출도 실패할 수 있다. 환경변수 `OLLAMA_FAST_TIMEOUT`으로 조정한다. 실패 처리는 4단계(재시도·격리)에서 보완한다.
- **gate 2차 조건**: 시스템 1개 안에서의 "패턴 분석"(시간대별 비교 등)은 더 이상 하지 않는다.
- 요청마다 `AsyncClient`를 새로 만든다. 연결을 재사용하지 않는 비용이 있지만, 로컬 호출이라 무시할 수 있는 수준이다(측정값 route 181~257ms).

---

## 직접 확인하는 방법 (수동)
```bash
grep -n "P3 \|P4 \|P9 " agent/graph.py agent/ollama_llm.py server.py | head -40
./.venv/bin/python3 -m pytest tests -q -k "gate or coroutine or think or timed"
```

**thinking 토큰 직접 재기** (Ollama만 있으면 된다)
```bash
curl -s localhost:11434/api/chat -d '{"model":"qwen3:0.6b","messages":[{"role":"user","content":"1+1?"}],"stream":false}' | python3 -c "import sys,json;print(json.load(sys.stdin)['eval_count'])"
curl -s localhost:11434/api/chat -d '{"model":"qwen3:0.6b","messages":[{"role":"user","content":"1+1?"}],"stream":false,"think":false}' | python3 -c "import sys,json;print(json.load(sys.stdin)['eval_count'])"
```

**P4 증명 — 질문 처리 중에도 /health가 바로 응답하는가**
```bash
bash outputs/after/scripts/realserver.sh ./.venv/bin/python3 outputs/after/scripts/probe_p4.py "payments-service 결제 응답이 느려지고 CPU가 치솟았어요, 원인 확인해주세요"
```
- `realserver.sh`가 실모델 서버를 :8199에 따로 띄운다. :8100에서 사용자가 띄운 서버는 건드리지 않는다.
- 그다음 `probe_p4.py`가 `/chat` 1건을 보내면서 `/health`를 0.5초마다 잰다.

**노드별 시간 보기**
```bash
curl -s -X POST localhost:8100/chat -H 'content-type: application/json' \
  -d '{"message":"log-service 디스크 공간이 부족하다는 알림이 왔어요","thread_id":"t1"}' | python3 -m json.tool | grep -A12 timings_ms
```
- 서버 터미널(터미널 2)에도 `agent.graph {"event": "node_done", "node": "write", "elapsed_ms": ...}`가 한 줄씩 찍힌다.

**화면** (서버 재시작 후 :8600)
- `payments-service 결제 응답이 느려지고 CPU가 치솟았어요, 원인 확인해주세요`를 입력한다.
- 성공하면 진행 단계에 "비교 분석"이 **없고**, 답변이 10초 안팎에 끝난다. Before는 30~300초였다.
- `payments-service랑 cache-service 둘 다 저하됐는데 공통 원인이 있는지 분석해줘`에서는 "비교 분석"이 **나온다**.

## 커밋 보고 7항목
1. **커밋**: 위 표
2. **Before 증거**:
   - `outputs/before/captures/terminal/S11_q01_timeout_trace.png`, `S12_q03_write_tokens.png`, `S4_q05_node_timing.png`
   - `code/C04`, `C05`, `C10`
3. **After 비교**: 8단계 `bench/results/after_summary.csv`의 ms_median과 ms_p95를 `baseline_summary.csv`와 비교한다. `outputs/after/captures/terminal/`에 같은 이름의 After 캡처를 둔다.
4. **선택**: P3 이중 게이트(K7), P4 AsyncClient(K12), P9 단계별 timeout + think 끔 + elapsed_ms(K15)
5. **트레이드오프**: 위 절
6. **핵심 변경**: `agent/ollama_llm.py:116`, `agent/graph.py:148`, `agent/graph.py:381`, `server.py:127`
7. **화면**: 위 "화면"
