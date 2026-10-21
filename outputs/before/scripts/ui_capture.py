"""Vue 채팅 화면에 질문을 보내고 응답이 끝난 상태를 캡처한다.

사용: python ui_capture.py <out.png> "<질문>" [--probe-health <log.txt>] [--timeout 400]
--probe-health: 질문 처리 중 /health 응답 시간을 1초 간격으로 재서 기록(P4 증거).
--during "<셸 명령>" --during-delay N: 질문을 보내고 N초 뒤 명령 실행(예: Ollama 종료 → P6 증거).
"""
import subprocess
import argparse
import json
import threading
import time
from datetime import datetime

import urllib.request
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("question")
ap.add_argument("--probe-health")
ap.add_argument("--timeout", type=int, default=400)
ap.add_argument("--url", default="http://localhost:8600/")
ap.add_argument("--during")
ap.add_argument("--during-delay", type=float, default=5.0)
a = ap.parse_args()

probe_rows, stop = [], threading.Event()


def probe():
    while not stop.is_set():
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen("http://127.0.0.1:8100/health", timeout=120) as r:
                r.read()
            status = "200"
        except Exception as e:  # noqa: BLE001
            status = type(e).__name__
        dt = time.perf_counter() - t0
        probe_rows.append((datetime.now().strftime("%H:%M:%S"), status, dt))
        time.sleep(max(0.0, 1.0 - dt))


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1100, "height": 900}, device_scale_factor=2)
    pg.goto(a.url)
    pg.wait_for_function("document.querySelector('header span').textContent.includes('ollama')",
                         timeout=15000)
    pg.fill("form input", a.question)
    t0 = time.perf_counter()
    pg.click("form button")
    if a.probe_health:
        threading.Thread(target=probe, daemon=True).start()
    pg.wait_for_function("document.querySelector('form button').disabled === true", timeout=5000)
    if a.during:
        time.sleep(a.during_delay)
        print("during:", a.during, subprocess.run(a.during, shell=True).returncode)
    pg.wait_for_function("document.querySelector('form button').disabled === false",
                         timeout=a.timeout * 1000, polling=500)
    elapsed = time.perf_counter() - t0
    stop.set()
    time.sleep(0.5)
    # 스크롤 영역을 펼쳐서 대화 전체가 한 장에 담기게 한다(화면 내용은 그대로).
    pg.add_style_tag(content="#log{overflow:visible!important;height:auto!important;"
                             "max-height:none!important;flex:none!important}"
                             "html,body,#app{height:auto!important;min-height:0!important;overflow:visible!important}")
    pg.locator("#app").screenshot(path=a.out)
    texts = pg.eval_on_selector_all(".step, .row .bubble", "els => els.map(e => e.textContent)")
    b.close()

print(json.dumps({"elapsed_s": round(elapsed, 1), "texts": texts}, ensure_ascii=False, indent=1))
if a.probe_health:
    with open(a.probe_health, "w") as f:
        f.write(f"# 질문 처리 중 /health 응답 시간 (질문: {a.question})\n")
        for ts, st, dt in probe_rows:
            f.write(f"{ts}  /health {st}  {dt:6.2f}s\n")
    worst = max((r[2] for r in probe_rows), default=0)
    print(f"health probes={len(probe_rows)} max={worst:.2f}s")
