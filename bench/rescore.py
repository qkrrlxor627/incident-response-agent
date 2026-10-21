"""이미 측정한 raw(jsonl)를 정답 세트로 다시 채점한다 — 서버·모델 없이 실행된다.

실행:
    ./.venv/bin/python3 bench/rescore.py [--tag baseline]
출력: 쿼리별 표 + 전체 요약, bench/results/<tag>_accuracy.csv
"""
import argparse
import csv
import json
from pathlib import Path

from eval_metrics import load_expected, mean, score

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="baseline")
    a = ap.parse_args()
    exp = load_expected()
    rows = []
    for line in (ROOT / "results" / f"{a.tag}_raw.jsonl").read_text().splitlines():
        r = json.loads(line)
        if "query_id" not in r or not r.get("counted"):
            continue
        reply = (r.get("response") or {}).get("reply")
        s = score(exp[r["query_id"]], r.get("route"), r.get("runbook"), r.get("monitored_systems"), reply)
        rows.append({"id": r["query_id"], "rep": r["rep"], "ok": r["ok"],
                     "monitored": ",".join(r.get("monitored_systems") or []),
                     "runbook": r.get("runbook"), **s})

    print(f"# {a.tag} 정확도 재채점 (정답: bench/eval_set.json)\n")
    print(f"{'id':4s} {'rep':3s} {'조사한 시스템':34s} {'runbook':16s} route type recall prec topic")
    for x in rows:
        f = lambda v: "-" if v is None else ("O" if v is True else ("X" if v is False else f"{v:.2f}"))
        print(f"{x['id']:4s} {x['rep']:<3d} {x['monitored'] or '-':34s} {str(x['runbook']):16s} "
              f"{f(x['route_ok']):5s} {f(x['type_ok']):4s} {f(x['system_recall']):6s} "
              f"{f(x['system_precision']):4s} {f(x['topic_coverage'])}")
    ok_rows = [x for x in rows if x["ok"]]
    summary = {
        "응답 성공률(기존 지표)": f"{sum(x['ok'] for x in rows)}/{len(rows)}",
        "route 정답률": mean(x["route_ok"] for x in ok_rows),
        "장애 유형(runbook) 정답률": mean(x["type_ok"] for x in ok_rows),
        "조사 범위 recall": mean(x["system_recall"] for x in ok_rows),
        "조사 정밀도 precision": mean(x["system_precision"] for x in ok_rows),
        "답변 토픽 포함률": mean(x["topic_coverage"] for x in ok_rows),
    }
    print("\n## 요약 (응답 성공 건 기준)")
    for k, v in summary.items():
        print(f"- {k}: {v}")
    out = ROOT / "results" / f"{a.tag}_accuracy.csv"
    with out.open("w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
