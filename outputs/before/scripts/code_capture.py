"""문제 코드 캡처 — 실제 소스 파일에서 줄 범위를 읽어 줄 번호·강조와 함께 PNG로 저장한다.

사용: python code_capture.py <project_root> <out_dir>
"""
import html
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

# (파일명, 제목, 문제 정의, [(경로, 시작, 끝, {강조 줄})])
ITEMS = [
    ("C01_P1_plan_supplement_only_when_empty", "P1 · 여러 시스템을 물어도 1개만 조사",
     "모델이 research task를 1개라도 주면 205줄의 '전체 복구'가 실행되지 않는다. 193줄은 오타 target을 첫 시스템 하나로 바꾼다.",
     [("agent/ollama_llm.py", 186, 215, {193, 205})]),
    ("C02_P1_prompt_single_system", "P1 · 표준 절차 프롬프트에 시스템 1개만 전달",
     "MCP Prompt는 system_name 하나만 받고, graph는 쿼리의 첫 시스템만 넣는다 → plan 입력에 '시스템: web-01' 한 줄.",
     [("agent/graph.py", 104, 113, {110}), ("mcp_server.py", 64, 72, {66, 71})]),
    ("C03_P2_db_down_fallback", "P2 · 규칙이 안 맞으면 무조건 db-down",
     "모든 monitoring alerts를 이어 붙여 규칙 순서대로 매칭하고, 하나도 안 맞으면 db-down. 정상(healthy)·미존재 시스템도 DB 다운 runbook이 붙는다.",
     [("agent/graph.py", 190, 213, {206, 207, 208, 213})]),
    ("C04_P3_gate_trusts_model", "P3 · gate가 모델의 needs_analysis를 그대로 믿음",
     "plan 프롬프트가 analysis 추가를 허용하고, gate는 모델이 낸 needs_analysis가 True면 아무것도 걸러내지 않는다(Before 9/9건 gate_removed=0).",
     [("agent/ollama_llm.py", 171, 179, {178}), ("agent/graph.py", 123, 135, {127})]),
    ("C05_P4_sync_llm_call_in_async_node", "P4 · async 노드 안의 동기 LLM 호출",
     "_chat()은 동기 httpx.post(104)인데 async 노드가 그대로 호출(78) → 응답을 기다리는 동안 이벤트 루프 전체 정지. q01은 analyze에서 300초 정지.",
     [("agent/ollama_llm.py", 94, 111, {104}), ("agent/graph.py", 76, 80, {78})]),
    ("C06_P5_retry_and_mcp_timeout", "P5 · MCP 호출에 timeout 없음 + 재시도가 실제 예외를 못 잡음",
     "ClientSession에 timeout이 없고(60), SDK timeout은 MCPError로 오는데 with_retry는 asyncio.TimeoutError만 잡는다(18). 그 예외를 내는 곳은 일부러 던지는 74줄뿐.",
     [("agent/mcp_client.py", 56, 77, {60, 72, 73, 74, 76}), ("agent/retry.py", 10, 22, {18})]),
    ("C07_P6_no_isolation_no_error_event", "P6 · task 하나 실패 = 요청 전체 실패, 화면은 조용히 멈춤",
     "read_resource는 재시도 없음(168), gather에 예외 격리 없음(172). 스트림 gen()에 try/except가 없고, 화면 onerror는 입력창만 다시 연다(203).",
     [("agent/graph.py", 160, 173, {168, 172}), ("web_chat.html", 200, 204, {203})]),
    ("C08_P7_stream_endpoint_unprotected", "P7 · 입력 검증·스트림 헤더·이력 저장 누락",
     "ChatRequest에 길이 조건이 없고(36), /chat/stream은 GET 쿼리 그대로(149). v1 분기는 이력 저장 없음(159-163), v2는 끝까지 가야 저장(188-189), 헤더 없음(192).",
     [("server.py", 35, 37, {36}), ("server.py", 148, 163, {149, 159, 160}), ("server.py", 186, 192, {188, 189, 192})]),
    ("C09_P8_bench_counts_response_only", "P8 · bench 성공률 = '응답이 왔는가'",
     "ok는 HTTP 200 여부만 본다(120). 그래서 q05 오분류도 성공으로 집계(0.97). 클라이언트 timeout 300초(26)가 서버 LLM timeout과 같다.",
     [("bench/run_baseline.py", 24, 26, {26}), ("bench/run_baseline.py", 115, 125, {120})]),
    ("C10_P9_timeout_and_think", "P9 · 단계별 timeout 없음, qwen3 thinking 옵션 없음",
     "모든 LLM 호출이 timeout=300 하나(104, 127). payload에 think 옵션이 없어 qwen3가 숨은 사고 토큰을 생성(추정) → q03 write 65~147초 편차.",
     [("agent/ollama_llm.py", 94, 104, {99, 100, 104}), ("agent/ollama_llm.py", 118, 128, {127})]),
    ("C11_P10_v1_rollback_condition", "P10 · v1 롤백 경로가 fake 응답 문구에 의존",
     "'도와드릴까요'가 답변에 있어야 장애 경로를 탄다(19) — fake 전용 문구. 조사 대상도 auth-service 고정(21).",
     [("agent/supervisor_v1.py", 14, 25, {19, 21})]),
    ("C12_P11_validate_format_only", "P11 · validate가 형식만 검사",
     "30자 이상 + '1)' 포함이면 합격(279). 조사 누락·근거 없는 수치도 통과. 3회째는 강제 통과(281).",
     [("agent/graph.py", 275, 290, {279, 281})]),
    ("C13_E15_sync_sqlite_session", "E15 · 동기 sqlite 세션 저장소",
     "async 핸들러에서 동기 sqlite3를 호출하고, 한 연결을 공유한다(check_same_thread=False). thread_id 인덱스 없음, 이력 전체 로드.",
     [("agent/session_store.py", 13, 28, {15, 16, 17, 23, 24})]),
]

CSS = """
body{margin:0;background:#0f1117;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;color:#e6e6e6}
.wrap{padding:28px 32px;width:1180px}
h1{font-size:22px;margin:0 0 8px;color:#fff}
p.def{font-size:15px;line-height:1.55;margin:0 0 18px;color:#f2c97d;background:#2a2416;border-left:4px solid #f2c97d;padding:10px 14px;border-radius:4px}
.file{font:600 13px Menlo,monospace;color:#8ab4f8;margin:14px 0 4px}
pre{margin:0;background:#161922;border:1px solid #2a2f3a;border-radius:6px;padding:8px 0;font:13px/1.55 Menlo,monospace;overflow:hidden}
.l{display:block;padding:0 14px;white-space:pre}
.l.hl{background:#4a1f24;border-left:4px solid #ff6b6b;padding-left:10px}
.n{display:inline-block;width:42px;color:#5c6370;text-align:right;margin-right:14px;user-select:none}
.foot{margin-top:14px;font-size:12px;color:#7d8590}
"""


def render(title, definition, snippets):
    parts = [f"<h1>{html.escape(title)}</h1><p class='def'>{html.escape(definition)}</p>"]
    for path, s, e, hl in snippets:
        lines = (ROOT / path).read_text().splitlines()
        body = "".join(
            f"<span class='l{' hl' if i in hl else ''}'><span class='n'>{i}</span>{html.escape(lines[i - 1])}</span>"
            for i in range(s, min(e, len(lines)) + 1))
        parts.append(f"<div class='file'>{path}:{s}-{e}</div><pre>{body}</pre>")
    parts.append("<div class='foot'>Before 코드 (git tag baseline과 에이전트 코드 동일) · 빨간 줄 = 문제 지점</div>")
    return f"<!doctype html><meta charset='utf-8'><style>{CSS}</style><div class='wrap'>{''.join(parts)}</div>"


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1250, "height": 800}, device_scale_factor=2)
    for name, title, definition, snippets in ITEMS:
        pg.set_content(render(title, definition, snippets))
        pg.locator(".wrap").screenshot(path=str(OUT / f"{name}.png"))
        print("saved", name)
    b.close()
