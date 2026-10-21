# 97% → 74%: 어느 파일, 어느 코드에서 나온 숫자인가

- 아래 줄 번호는 흐름 주석을 넣은 **현재 코드** 기준이다. 코드 안의 `# [97% 흐름 ①]` … `# ▶ 다음: 파일:줄` 주석을 따라가면 같은 순서로 읽을 수 있다.
- 주석만 추가했고 동작은 그대로다(AST 비교, `rescore.py` 재실행 결과 동일, pytest 15 passed / 1 xfailed).
- Before 캡처(`outputs/before/captures/code/C09_...png`)의 줄 번호(120 등)는 주석을 넣기 전 코드(`git tag before-evidence`) 기준이다.

---

## 1부. 기존 지표 97% — "응답이 왔는가"

> 기존에는 응답이 반환됐는지만으로 성공을 판단해 97%의 성공률을 기록했습니다.

### 실행한 명령 (어제 14:14, 백엔드 :8100 필요, 약 25분)

```bash
./.venv/bin/python3 bench/run_baseline.py --repeat 3 --tag baseline
```

### ▶ 이 명령을 치면 실행되는 순서

명령의 각 부분이 뜻하는 것:

| 부분 | 뜻 |
|---|---|
| `./.venv/bin/python3` | 이 프로젝트 전용 파이썬(가상환경)으로 실행한다. 그냥 `python3`로 치면 `httpx` 같은 패키지가 없는 다른 파이썬이 잡힐 수 있다 |
| `bench/run_baseline.py` | 실행할 파일 |
| `--repeat 3` | 82줄 `args = ap.parse_args()`에서 `args.repeat = 3`이 된다(80줄에서 정의) |
| `--tag baseline` | `args.tag = "baseline"`이 된다(81줄). 결과 파일 이름 `baseline_raw.jsonl`의 앞부분이 된다 |

파이썬은 파일을 위에서 아래로 읽는다:

```
[클라이언트: bench/run_baseline.py]
 12~22줄   import argparse, json, httpx ...        도구를 불러온다
 24~26줄   ROOT, BASE="http://localhost:8100", TIMEOUT=300.0   상수를 정한다
 29·62·73·78줄   def extract / post / p95 / main    함수를 "정의만" 한다 (아직 실행하지 않음)
 186~187줄 if __name__ == "__main__": main()       ← 직접 실행했을 때만 여기서 main()이 시작된다
   ↓
 main() 78줄
   82줄   args = ap.parse_args()                     --repeat 3 --tag baseline을 읽는다
   86줄   queries = json.loads(...queries.json)      [97% 흐름 ①]
   90줄   with httpx.Client(timeout=300) as client:  HTTP 클라이언트를 연다
   91줄   client.get(".../health")                   서버 조건(모델 이름 등)을 기록한다
   105줄  post(client, "web-01 CPU 급증 ...")         워밍업 1회 (기록에는 넣지 않음)
   113줄  raw_path.open("w")                         baseline_raw.jsonl을 새로 쓴다(덮어쓰기)
   117~149줄  반복: post() → extract() → ok 판정 → 한 줄 저장   [97% 흐름 ②~⑥]
   153줄  summary_path.open("w")                     baseline_summary.csv를 쓴다 [⑦]
   180~182줄  print(... 성공률 0.97)                 터미널에 출력한다 [⑧]
```

`post()`(62줄)가 `/chat`을 부르면 **서버 쪽**에서 실행되는 코드:

```
[서버: server.py, 터미널 2에서 떠 있는 프로세스]
 141~142줄  @app.post("/chat") async def chat(req)      요청을 받는다
 126줄      _handle_chat(message, thread_id)
 128줄        session_store.load(thread_id)             이전 대화를 불러온다
 130줄        app.state.graph.ainvoke({...})            LangGraph 에이전트 실행
                └ agent/graph.py:310 build_graph()가 만든 흐름:
                  route → plan → gate → research → replan_check → analysis → write → validate → finalize
                  research(graph.py:162~169)가 MCP로 모니터링·runbook을 가져오고 TaskCompleted 이벤트를 남긴다
 135~136줄    session_store.append(...)                 대화를 저장한다
 143~144줄  return {"reply", "events", "metadata"}       응답 JSON
   ↓
[다시 클라이언트] 127줄 extract(body)가 이 "events"에서 조사한 시스템(source=monitoring)과
                  runbook(source=runbook)을 꺼낸다
```

### 코드 흐름 — `bench/run_baseline.py`의 `main()`

| 순서 | 줄 | 코드 | 하는 일 |
|---|---|---|---|
| ① | 86 | `queries = json.loads((ROOT / "queries.json").read_text())` | 질문 10개를 읽는다(원본 `doc/regression_test_queries.md`) |
| ② | 117~120 | `for q in queries:` / `for rep in range(...)` / `for turn_idx, message in ...` | 질문 10개 × 3회 × 턴 수만큼 반복한다 |
| ③ | 123 | `status, ms, body, err = post(client, message, thread_id)` | 실제 서버 `/chat`을 호출한다(함수 본체 62줄) |
| ④ | 127 | `info = extract(body) if body else {}` | 응답에서 조사한 시스템과 runbook을 꺼낸다(함수 본체 29줄) |
| **⑤** | **133** | **`ok = status == 200 and err is None`** | **성공 판정. 답변 내용은 보지 않는다** |
| ⑤-예외 | 134~135 | `if ok and is_last and q.get("expect_in_last_reply"):` | q10만 해당한다. 마지막 답변에 "민수"가 있어야 성공이다 |
| ⑥ | 139~143 | `row = {..., "ok": ok, "counted": is_last, **info}` → `raw.write(...)` | 한 건을 `baseline_raw.jsonl`에 저장한다 |
| ⑦ | 165~166 | `round(sum(r["ok"] for r in last) / len(last), 2)` | 질문별 성공률을 `baseline_summary.csv`에 쓴다 |
| **⑧** | **180~182** | **`counted = [r for r in rows if r["counted"]]`**<br>**`성공률 {sum(r['ok'] for r in counted) / len(counted):.2f}`** | **전체 성공률 = 29 / 30 = 0.97** |

- ⑧에서 `counted`는 "마지막 턴인가"를 뜻한다. 다턴(q10)은 마지막 턴만 세므로, 호출은 33건이고 채점 대상은 30건이다.
- 실패 1건은 q01 1회차다. 300초 타임아웃으로 `status=None`이 되어 ⑤에서 `ok=False`가 됐다.

### 결과 파일

```
bench/results/
├── baseline_raw.jsonl     ← ⑥ 응답 한 건 = 한 줄 (ok, counted, 조사한 시스템, runbook, 답변 원문)
├── baseline_summary.csv   ← ⑦ 질문별 성공률 (q01만 0.67)
└── before.md              ← 사람이 정리한 결과. 21번째 줄 "성공률: 29/30 = 0.97"
```

### 직접 확인하는 명령 (서버 필요 없음)

```bash
cd ~/subject/1020/all_total_vue_student

# 코드 보기: 성공 판정(⑤)과 전체 성공률(⑧)
sed -n 129,135p bench/run_baseline.py
sed -n 176,182p bench/run_baseline.py

# 채점 대상 건수 → 30
grep '"counted": true' bench/results/baseline_raw.jsonl | wc -l
# 그중 성공 건수 → 29
grep '"counted": true' bench/results/baseline_raw.jsonl | grep -c '"ok": true'
# 실패한 1건 → q01 1회차
grep '"counted": true' bench/results/baseline_raw.jsonl | grep '"ok": false' | grep -o '"query_id": "[^"]*", "rep": [0-9]'
# 핵심: q05는 db-down(틀린 매뉴얼)인데 ok=true로 셌다
grep '"query_id": "q05"' bench/results/baseline_raw.jsonl | grep -o '"runbook": "[^"]*"\|"ok": [a-z]*'

# 질문별 성공률
cut -d, -f1,3 bench/results/baseline_summary.csv
```

---

## 2부. 실제 정확도 74% — "맞는 매뉴얼을 골랐는가"

> 그러나 정답 데이터셋(Ground Truth)을 만들어 매뉴얼 선택 정확도를 다시 평가한 결과, 실제 정확도는 74%로 확인됐습니다.

| 지표 | 값 |
|---|---|
| 응답 성공률 (기존) | 97% (29/30) |
| 매뉴얼 선택 정확도 (새 지표) | **74%** (17/23 = 0.739) |

### 실행한 명령 (오늘, 서버 필요 없음, 1초)

```bash
./.venv/bin/python3 bench/rescore.py --tag baseline
```

### ▶ 이 명령을 치면 실행되는 순서

| 부분 | 뜻 |
|---|---|
| `bench/rescore.py` | 실행할 파일. 서버를 부르지 않는다 |
| `--tag baseline` | 20줄 `a = ap.parse_args()`에서 `a.tag = "baseline"`이 된다 → `baseline_raw.jsonl`을 읽고 `baseline_accuracy.csv`를 쓴다 |

```
[bench/rescore.py]
 7~10줄   import argparse, csv, json ...
 12줄     from eval_metrics import load_expected, mean, score
            └ 이 순간 bench/eval_metrics.py 파일 전체가 한 번 실행된다:
              13줄 EVAL_SET = .../eval_set.json 경로를 정하고
              17·22·43줄 load_expected / score / mean 함수를 "정의만" 한다
 14줄     ROOT = bench 폴더 경로
 17줄     def main(): (정의만)
 74~75줄  if __name__ == "__main__": main()            ← 여기서 시작
   ↓
 main()
   20줄   a = ap.parse_args()                          --tag baseline
   23줄   load_expected()  → eval_metrics.py:17~18     eval_set.json을 읽는다 [74% 흐름 ①]
   28~40줄 raw 파일 한 줄씩:
            32줄 counted가 아니면 건너뛴다              [③]
            37줄 score(...) → eval_metrics.py:22~39     한 건 채점 [④]
                   33줄 type_ok = runbook == 정답        ★
   42~48줄 표를 터미널에 출력한다                       (S10 캡처 화면)
   53~61줄 ok_rows, mean(...) → eval_metrics.py:43~45   평균 [⑤]
   62~64줄 요약을 출력한다: "장애 유형(runbook) 정답률: 0.739"
   66~70줄 baseline_accuracy.csv에 쓴다                 [⑥]
```

### 어떤 파일을 조합했나

```
① bench/results/baseline_raw.jsonl   ← 1부 ⑥에서 저장한 기록 (에이전트가 고른 매뉴얼, 조사한 시스템)
        +
② bench/eval_set.json                ← 질문별 정답 (정답 매뉴얼, 정답 시스템, 근거)
        ↓
③ bench/eval_metrics.py  score()     ← 기록과 정답을 비교하는 채점 함수
        ↓
④ bench/rescore.py  main()           ← 기록을 읽고 건마다 ③을 호출한 뒤 평균을 낸다
        ↓
bench/results/baseline_accuracy.csv  → 매뉴얼 선택 정확도 0.739
```

### 코드 흐름 — `bench/rescore.py`의 `main()` → `bench/eval_metrics.py`

| 순서 | 위치 | 코드 | 하는 일 |
|---|---|---|---|
| ① | `rescore.py:23` → `eval_metrics.py:17` | `exp = load_expected()` | 정답 세트 `eval_set.json`을 읽는다 |
| ② | `rescore.py:28` | `for line in (ROOT / "results" / f"{a.tag}_raw.jsonl")...` | 97% 때 저장한 기록을 그대로 읽는다. 서버를 다시 부르지 않는다 |
| ③ | `rescore.py:32` | `if "query_id" not in r or not r.get("counted"): continue` | 97%와 같은 30건만 남긴다 |
| ④ | `rescore.py:37` → `eval_metrics.py:22` | `s = score(exp[...], route, runbook, monitored_systems, reply)` | 한 건을 채점한다 |
| **④-핵심** | **`eval_metrics.py:33`** | **`"type_ok": (runbook == exp["expected_incident_type"])`** | **고른 매뉴얼이 정답과 같은가** |
| ⑤ | `rescore.py:53` | `ok_rows = [x for x in rows if x["ok"]]` | 응답이 온 29건만 대상으로 한다 |
| **⑤-핵심** | **`rescore.py:57` → `eval_metrics.py:43`** | **`mean(x["type_ok"] for x in ok_rows)`** | **평균 = 0.739.** q09·q10은 장애 질문이 아니라 None이고 제외되므로 분모는 23건이다 |
| ⑥ | `rescore.py:66` | `out = ROOT / "results" / f"{a.tag}_accuracy.csv"` | 건별 결과를 저장한다 |

### 0.739 = 17 / 23 계산

| 구분 | 건수 |
|---|---|
| 응답이 온 장애 질문 | 23건 (q01 2건 + q02~q08 7개 × 3회) |
| 정답 | 17건 |
| 오답 | 6건: **q05 × 3** (정답 high-latency인데 db-down), **q08 × 3** (감시하지 않는 billing-service인데 runbook을 붙임) |

### 직접 확인하는 명령 (서버 필요 없음)

```bash
cd ~/subject/1020/all_total_vue_student

# 재채점 실행 → 표와 요약이 나온다 (S10 캡처와 같은 화면)
./.venv/bin/python3 bench/rescore.py --tag baseline

# 코드 보기: 채점 대상 고르기, 평균
sed -n 25,37p bench/rescore.py
sed -n 49,57p bench/rescore.py
# 코드 보기: 매뉴얼 정답 판정
sed -n 22,40p bench/eval_metrics.py

# q05의 정답 (expected_incident_type: high-latency)
grep -A3 '"id": "q05"' bench/eval_set.json

# 17/23을 직접 세기
./.venv/bin/python3 -c "
import csv
r=[x for x in csv.DictReader(open('bench/results/baseline_accuracy.csv')) if x['ok']=='True' and x['type_ok']!='']
print('분모', len(r), '정답', sum(x['type_ok']=='True' for x in r))"
```

---

## 발표용 한 줄

> "같은 30건의 응답 기록을, 기준만 '응답이 왔는가'(`run_baseline.py:133`)에서 '맞는 매뉴얼을 골랐는가'(`eval_metrics.py:33`)로 바꿔 다시 채점했더니 97%가 74%가 됐습니다."

- 캡처: `outputs/before/captures/terminal/S10_baseline_accuracy.png`, `outputs/before/captures/code/C09_P8_bench_counts_response_only.png`
