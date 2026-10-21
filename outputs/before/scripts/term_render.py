"""증거 텍스트(실제 명령 출력)를 터미널 화면 스타일 PNG로 렌더링한다.

사용: python term_render.py <out_dir> <txt> [<txt> ...]
"""
import html
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CSS = """
body{margin:0;background:#0f1117}
.term{width:1180px;margin:20px;border-radius:10px;overflow:hidden;border:1px solid #2a2f3a;background:#1b1e26}
.bar{background:#2a2e38;padding:8px 12px;font:12px -apple-system,sans-serif;color:#9aa4b2}
.bar i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}
pre{margin:0;padding:14px 18px;font:13px/1.5 Menlo,'Apple SD Gothic Neo',monospace;color:#d7dae0;white-space:pre-wrap;word-break:break-all}
.c{color:#7ee787}.h{color:#f2c97d}.e{color:#ff7b72}
"""


def colorize(line: str) -> str:
    s = html.escape(line)
    if line.startswith("$ "):
        return f"<span class='c'>{s}</span>"
    if line.startswith("#") or line.startswith("==="):
        return f"<span class='h'>{s}</span>"
    if any(k in line for k in ("error", "Error", "timed out", "db-down", "False", "X ")):
        return f"<span class='e'>{s}</span>"
    return s


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1240, "height": 800}, device_scale_factor=2)
    for t in sys.argv[2:]:
        path = Path(t)
        body = "\n".join(colorize(l) for l in path.read_text().splitlines())
        pg.set_content(f"<!doctype html><meta charset='utf-8'><style>{CSS}</style>"
                       f"<div class='term'><div class='bar'><i style='background:#ff5f57'></i>"
                       f"<i style='background:#febc2e'></i><i style='background:#28c840'></i>"
                       f"&nbsp; {html.escape(path.name)}</div><pre>{body}</pre></div>")
        pg.locator(".term").screenshot(path=str(OUT / (path.stem + ".png")))
        print("saved", path.stem)
    b.close()
